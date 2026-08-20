#!/usr/bin/env bash
#
# NoteLLM 一键安装向导
#
#   仓库内运行：
#   bash install.sh               交互式安装（本地 / 生产二选一）
#   bash install.sh --local       本地开发（localhost，快速体验）
#   bash install.sh --prod        生产部署（公网域名 + HTTPS）
#   bash install.sh --yes         全自动：所有问题取默认值、密钥自动生成
#   bash install.sh --force       已有 .env 时也重新生成（旧文件备份为 .env.bak.*）
#   bash install.sh --dry-run     只生成 .env 并打印将要执行的命令，不启动服务
#   bash install.sh --low-mem     低内存模式：前端 SPA 不在服务器上构建（注入预构建 dist）
#   bash install.sh --no-low-mem  强制镜像内构建前端（覆盖低内存自动检测）
#
#   远程一键（3x-ui 风格，无需先克隆仓库）：
#   bash <(curl -Ls https://raw.githubusercontent.com/au1bhi/NoteLLM/master/install.sh)
#   自动克隆/更新到 $NOTELLM_DIR（默认 ~/NoteLLM）后继续；重复运行即升级。
#
# 首次运行会交互式收集配置并生成 .env，然后构建并启动整套服务。
# 已有 .env 时默认保留并直接启动，不会覆盖你的配置。
# =============================================================================
# shellcheck disable=SC1111  # 中文全角引号“ ”是界面文案，不是 shell 引号
set -euo pipefail

# ---------- 输出样式 ----------
if [[ -t 1 ]]; then
  C_OK="\033[0;32m"; C_WARN="\033[0;33m"; C_ERR="\033[0;31m"
  C_BOLD="\033[1m"; C_DIM="\033[2m"; C_RESET="\033[0m"
else
  C_OK=""; C_WARN=""; C_ERR=""; C_BOLD=""; C_DIM=""; C_RESET=""
fi

info() { printf '%b\n' "${C_DIM}${1}${C_RESET}" "${@:2}"; }
ok()   { printf '%b\n' "${C_OK}✔ ${1}${C_RESET}" "${@:2}"; }
warn() { printf '%b\n' "${C_WARN}⚠ ${1}${C_RESET}" "${@:2}"; }
err()  { printf '%b\n' "${C_ERR}✘ ${1}${C_RESET}" "${@:2}" >&2; }
step() { printf '\n%b\n' "${C_BOLD}==> ${1}${C_RESET}"; }

trap 'printf "\n${C_ERR}安装已取消。${C_RESET}\n" >&2; exit 130' INT

# Refuse archive entries that could escape the destination or create special
# files. GNU tar's escaped listing makes control characters/backslashes visible
# so they can be rejected before extraction.
validate_tar_archive() {
  local archive="$1" max_bytes="$2" require_index="${3:-0}"
  local check_dir names verbose member_count
  check_dir="$(mktemp -d "${TMPDIR:-/tmp}/notellm-archive-check.XXXXXX")"
  names="$check_dir/names"
  verbose="$check_dir/verbose"

  if ! LC_ALL=C tar -tzf "$archive" --quoting-style=escape > "$names" \
    || ! LC_ALL=C tar -tvzf "$archive" --quoting-style=escape --numeric-owner > "$verbose"; then
    rm -rf -- "$check_dir"
    err "归档格式无效或已损坏：$archive"
    return 1
  fi

  member_count="$(wc -l < "$names")"
  if (( member_count == 0 || member_count > 20000 )); then
    rm -rf -- "$check_dir"
    err "归档成员数量异常：${member_count}（允许 1–20000）。"
    return 1
  fi

  local name normalized found_index=0
  while IFS= read -r name; do
    normalized="$name"
    while [[ "$normalized" == ./* ]]; do normalized="${normalized#./}"; done
    [[ -n "$normalized" ]] || continue
    case "$normalized" in
      /*|*\\*|..|../*|*/../*|*/..)
        rm -rf -- "$check_dir"
        err "归档包含不安全路径：$name"
        return 1
        ;;
    esac
    [[ "$normalized" == "index.html" ]] && found_index=1
  done < "$names"

  local line entry_type
  while IFS= read -r line; do
    entry_type="${line:0:1}"
    if [[ "$entry_type" != "-" && "$entry_type" != "d" ]]; then
      rm -rf -- "$check_dir"
      err "归档包含链接、设备或其他特殊文件，已拒绝。"
      return 1
    fi
  done < "$verbose"

  if ! awk -v limit="$max_bytes" '
      $1 ~ /^-/ {
        if ($3 !~ /^[0-9]+$/) exit 2
        total += $3
        if (total > limit) exit 1
      }
      END { if (total <= 0) exit 3 }
    ' "$verbose"; then
    rm -rf -- "$check_dir"
    err "归档解压后大小无效或超过安全上限。"
    return 1
  fi

  if [[ "$require_index" == "1" && "$found_index" != "1" ]]; then
    rm -rf -- "$check_dir"
    err "前端归档缺少根目录 index.html。"
    return 1
  fi

  rm -rf -- "$check_dir"
}

verify_sha256() {
  local archive="$1" expected="${2,,}" actual
  if [[ ! "$expected" =~ ^[0-9a-f]{64}$ ]]; then
    err "SHA-256 格式无效（应为 64 位十六进制）。"
    return 1
  fi
  actual="$(sha256sum "$archive" | awk '{print $1}')"
  if [[ "$actual" != "$expected" ]]; then
    err "SHA-256 校验失败：期望 $expected，实际 $actual"
    return 1
  fi
}

extract_source_archive() {
  local archive="$1" destination="$2"
  validate_tar_archive "$archive" 209715200
  tar -xzf "$archive" --strip-components=1 --unlink-first \
    --no-same-owner --no-same-permissions --delay-directory-restore \
    -C "$destination"
}

banner() {
  cat <<'EOF'
==============================================================================
   NoteLLM · 一键安装向导
   本地开发 / 生产部署 二合一，交互式配置，自动生成安全密钥
   支持远程执行：bash <(curl -Ls https://raw.githubusercontent.com/au1bhi/NoteLLM/master/install.sh)
==============================================================================
EOF
  echo
}

# ---------- 远程一键安装引导（3x-ui 风格） ----------
# 支持 `bash <(curl -Ls https://raw.githubusercontent.com/au1bhi/NoteLLM/master/install.sh)`
# 直接运行：当脚本不在 NoteLLM 仓库内时，把仓库克隆到 $NOTELLM_DIR（默认
# ~/NoteLLM），已存在则先 git pull 更新，然后重新执行磁盘上的 install.sh
# （此时 $PWD/compose.yml 存在，会跳过本引导段直接进入主流程）。
# 因此同一命令即可“安装”，重复运行即为“更新 + 重装”。
if [[ "${BASH_SOURCE[0]}" == "$0" && ! -f "$PWD/compose.yml" ]]; then
  INSTALL_DIR="${NOTELLM_DIR:-$HOME/NoteLLM}"
  REPO_URL="${NOTELLM_REPO:-https://github.com/au1bhi/NoteLLM.git}"
  BRANCH="${NOTELLM_BRANCH:-master}"
  # 大陆服务器常无法直连 github.com / raw.githubusercontent.com，但
  # codeload.github.com 的源码包通常可达——git 克隆失败时用源码包兜底。
  TARBALL_URL="${NOTELLM_TARBALL:-}"
  TARBALL_SHA256="${NOTELLM_TARBALL_SHA256:-}"
  if [[ -z "$TARBALL_URL" ]]; then
    SOURCE_COMMIT="${NOTELLM_COMMIT:-}"
    if [[ -z "$SOURCE_COMMIT" ]]; then
      SOURCE_COMMIT="$(curl -fsSL --max-time 30 \
        "https://api.github.com/repos/au1bhi/NoteLLM/commits/$BRANCH" 2>/dev/null \
        | sed -nE 's/.*"sha"[[:space:]]*:[[:space:]]*"([0-9a-f]{40})".*/\1/p' \
        | head -n 1 || true)"
    fi
    if [[ ! "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
      err "无法把源码包绑定到不可变 Git 提交；请恢复 Git 网络后重试。"
      exit 1
    fi
    TARBALL_URL="https://codeload.github.com/au1bhi/NoteLLM/tar.gz/$SOURCE_COMMIT"
  elif [[ ! "$TARBALL_SHA256" =~ ^[0-9A-Fa-f]{64}$ ]]; then
    err "自定义 NOTELLM_TARBALL 必须同时提供 NOTELLM_TARBALL_SHA256。"
    exit 1
  fi
  # 禁止 git 弹交互式凭据提示（网络受限时挂起/等待输入）。
  export GIT_TERMINAL_PROMPT=0

  if [[ -f "$INSTALL_DIR/compose.yml" ]]; then
    if [[ -d "$INSTALL_DIR/.git" ]] && command -v git >/dev/null 2>&1; then
      echo "==> 更新 $INSTALL_DIR ..."
      # timeout 防止被墙网络让 git pull 无限挂起。
      if ! timeout 60 git -C "$INSTALL_DIR" pull --ff-only >/dev/null 2>&1; then
        err "git pull 失败或超时，已停止升级，避免用旧代码/镜像冒充最新版本。"
        err "请处理本地改动或网络问题后重试；现有服务不会被本次操作修改。"
        exit 1
      fi
    else
      # 源码包安装（无 .git）：重新下载源码包即是最新代码，直接覆盖更新。
      echo "==> 更新 $INSTALL_DIR（源码包安装，重新下载最新代码）..."
      source_tmp="$(mktemp -d "${TMPDIR:-/tmp}/notellm-source.XXXXXX")"
      curl -fLsS --max-time 300 --max-filesize 104857600 \
        "$TARBALL_URL" -o "$source_tmp/source.tar.gz"
      [[ -z "$TARBALL_SHA256" ]] || verify_sha256 "$source_tmp/source.tar.gz" "$TARBALL_SHA256"
      extract_source_archive "$source_tmp/source.tar.gz" "$INSTALL_DIR"
      rm -rf -- "$source_tmp"
    fi
    cd "$INSTALL_DIR"
  else
    if [[ -d "$INSTALL_DIR" ]]; then
      err "$INSTALL_DIR 已存在但不是有效的 NoteLLM 仓库（缺少 compose.yml）。"
      err "请删除该目录，或设置 NOTELLM_DIR 指向正确位置后重试。"
      exit 1
    fi
    command -v git >/dev/null 2>&1 || {
      err "需要 git 来获取 NoteLLM（将克隆到 $INSTALL_DIR）。"
      info "安装 git：sudo apt-get update && sudo apt-get install -y git"
      exit 1
    }
    echo "==> 克隆 NoteLLM 到 $INSTALL_DIR ..."
    if ! timeout 120 git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR" 2>/dev/null; then
      # git 克隆失败（github.com 被墙/不可达）→ 改用 codeload 源码包。
      warn "git clone 失败（可能无法访问 github.com），改用源码包下载 ..."
      mkdir -p "$INSTALL_DIR"
      source_tmp="$(mktemp -d "${TMPDIR:-/tmp}/notellm-source.XXXXXX")"
      curl -fLsS --max-time 300 --max-filesize 104857600 \
        "$TARBALL_URL" -o "$source_tmp/source.tar.gz"
      [[ -z "$TARBALL_SHA256" ]] || verify_sha256 "$source_tmp/source.tar.gz" "$TARBALL_SHA256"
      extract_source_archive "$source_tmp/source.tar.gz" "$INSTALL_DIR"
      rm -rf -- "$source_tmp"
    fi
    cd "$INSTALL_DIR"
  fi
  exec bash install.sh "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE="$SCRIPT_DIR/.env"

# ---------- 参数 ----------
ASSUME_YES=0
FORCE=0
DRY_RUN=0
PROFILE=""
ARGS_DOMAIN="${DOMAIN:-}"
LOW_MEM_FORCED=""

usage() {
  sed -n '3,18p' "$0"
  exit 0
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --local) PROFILE="local" ;;
      --prod) PROFILE="prod" ;;
      --yes) ASSUME_YES=1 ;;
      --force) FORCE=1 ;;
      --dry-run) DRY_RUN=1 ;;
      --low-mem) LOW_MEM_FORCED=1 ;;
      --no-low-mem) LOW_MEM_FORCED=0 ;;
      --help|-h) usage ;;
      *) echo "✘ 未知参数: $1"; usage ;;
    esac
    shift
  done
}

# ---------- 交互工具 ----------
# 提问并读入答案；回车取默认值。非交互环境 / --yes 时直接取默认值。
# 若目标变量已由调用者通过环境变量提供（非空），则保留该值不再提问。
ask_var() {
  local var="$1" prompt="$2" default="$3" input=""
  [[ -z "${!var:-}" ]] || return 0
  if [[ "$ASSUME_YES" != "1" ]] && [[ -t 0 ]]; then
    printf '%s [%s] ' "$prompt" "$default" >&2
    IFS= read -r input || true
  fi
  printf -v "$var" '%s' "${input:-$default}"
}

# 同 ask_var，但提示用“回车接受已生成的值”，用于密钥输入。
ask_secret_var() {
  local var="$1" prompt="$2" default="$3" input=""
  [[ -z "${!var:-}" ]] || return 0
  local hint="回车接受 ${default}"
  [[ -n "$default" ]] || hint="回车留空"
  if [[ "$ASSUME_YES" != "1" ]] && [[ -t 0 ]]; then
    printf '%s [%s] ' "$prompt" "$hint" >&2
    IFS= read -r input || true
  fi
  printf -v "$var" '%s' "${input:-$default}"
}

# 是/否 确认。默认 n → y/N；默认 y → Y/n。
confirm() {
  local prompt="$1" default="${2:-n}" input=""
  local hint="y/N"; [[ "$default" == "y" ]] && hint="Y/n"
  if [[ "$ASSUME_YES" != "1" ]] && [[ -t 0 ]]; then
    printf '%s [%s] ' "$prompt" "$hint" >&2
    IFS= read -r input || true
    case "${input,,}" in
      y|yes) return 0 ;;
      "") [[ "$default" == "y" ]] ;;
      *) return 1 ;;
    esac
  else
    [[ "$default" == "y" ]]
  fi
}

# ---------- 工具 ----------
gen_secret() {
  local n="${1:-48}" s
  if command -v python3 >/dev/null 2>&1; then
    s="$(python3 -c "import secrets,sys; print(secrets.token_urlsafe(int(sys.argv[1])))" "$n")"
  else
    s="$(openssl rand -base64 "$n" | tr -d '\n')"
  fi
  printf '%s' "$s"
}

# 读取已有 .env 中某个键的值（用于重新生成时保留旧配置）。不存在则输出空。
env_get() {
  local key="$1" line
  line="$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -n 1 || true)"
  printf '%s' "${line#*=}"
}

env_header() { printf '\n# %s\n' "$1" >> "$ENV_FILE"; }
env_put()    { printf '%s=%s\n' "$1" "$2" >> "$ENV_FILE"; }

# ---------- 预检 ----------
check_prereqs() {
  local missing=() ok_docker=0
  command -v docker >/dev/null 2>&1 || missing+=("docker")
  command -v openssl >/dev/null 2>&1 || missing+=("openssl")
  command -v curl >/dev/null 2>&1 || warn "未找到 curl，安装后将跳过健康检查（可后续补装）。"

  if [[ "${#missing[@]}" -gt 0 ]]; then
    err "缺少必要工具: ${missing[*]}"
    case "$(command -v apt-get >/dev/null 2>&1 && echo apt || true)" in
      apt) info "  安装命令: sudo apt-get update && sudo apt-get install -y ${missing[*]}" ;;
      *)   info "  请先安装: ${missing[*]}" ;;
    esac
    exit 1
  fi

  if docker compose version >/dev/null 2>&1; then
    ok_docker=1
  elif command -v docker-compose >/dev/null 2>&1; then
    warn "检测到旧版 docker-compose，建议升级为 Docker Compose 插件（docker compose）。"
    ok_docker=1
  else
    missing+=("docker compose 插件")
  fi

  if [[ "$DRY_RUN" == "1" ]]; then
    [[ "$ok_docker" == "1" ]] || warn "未检测到 docker/docker compose（dry-run 模式跳过）。"
    return 0
  fi
  if [[ "$ok_docker" != "1" ]]; then
    err "未检测到 Docker Compose（docker compose）。安装 Docker 后重试。"
    exit 1
  fi

  if ! docker info >/dev/null 2>&1; then
    err "无法连接 Docker daemon。"
    info "  常见原因：daemon 未启动，或当前用户不在 docker 组。"
    info "  修复：sudo systemctl start docker 或 sudo usermod -aG docker \$USER（然后重新登录）。"
    exit 1
  fi
  ok "Docker 环境就绪。"
}

# ---------- 模式选择 ----------
profile_select() {
  if [[ -z "$PROFILE" ]]; then
    step "选择安装模式"
    info "  1) 本地开发 —— localhost，快速体验，无需域名/证书"
    info "  2) 生产部署 —— 公网域名 + HTTPS（Let's Encrypt 自动证书）"
    local choice=""
    while [[ -z "$choice" ]]; do
      printf '请输入 [1/2] [1] ' >&2
      IFS= read -r choice || true
      case "${choice:-1}" in
        1) choice="local" ;;
        2) choice="prod" ;;
        *) warn "无效输入，请输入 1 或 2"; choice="" ;;
      esac
    done
    PROFILE="$choice"
  fi
  if [[ "$PROFILE" == "prod" ]] && [[ -n "$ARGS_DOMAIN" ]]; then
    DOMAIN="$ARGS_DOMAIN"
  fi
  ok "安装模式：$( [[ "$PROFILE" == "prod" ]] && echo 生产部署 || echo 本地开发 )"
}

# ---------- 低内存模式（前端不在服务器上构建） ----------
# 前端 SPA 的构建（bun install + vite build）需要约 2GB 内存，在 1–2GB 的
# 小服务器上会被 OOM 杀掉。低内存模式下 `frontend` 服务改用纯 nginx 镜像
# （frontend/Dockerfile.nginx + compose.lowmem.yml），并把预构建的 dist 注入
# `frontend-dist` 卷——dist 来源依次为：FRONTEND_DIST_URL → 仓库内
# frontend-dist.tar.gz → GitHub Release 的 frontend-dist-* 资产。
LOW_MEM_MB="${LOW_MEM_MB:-2048}"

mem_mb() {
  awk '/MemTotal/{printf "%.0f", $2 / 1024}' /proc/meminfo 2>/dev/null || echo 0
}

select_low_mem() {
  if [[ "$LOW_MEM_FORCED" == "1" ]]; then
    LOW_MEM=1
    ok "已启用低内存模式（--low-mem）：前端 SPA 不在服务器上构建。"
    return 0
  fi
  if [[ "$LOW_MEM_FORCED" == "0" ]]; then
    LOW_MEM=0
    ok "已强制使用镜像内构建（--no-low-mem）。"
    return 0
  fi
  local mem
  mem="$(mem_mb)"
  LOW_MEM=0
  if (( mem > 0 && mem < LOW_MEM_MB )); then
    warn "检测到内存不足（${mem}MB < ${LOW_MEM_MB}MB）：前端 SPA 若在服务器上构建可能 OOM。"
    if [[ "$ASSUME_YES" == "1" ]] || [[ ! -t 0 ]] || confirm "启用低内存模式（前端改用预构建 dist）？" "y"; then
      LOW_MEM=1
      ok "已启用低内存模式。"
    else
      warn "继续使用镜像内构建（若构建 OOM，请改用 --low-mem）。"
    fi
  fi
}

# ---------- 网络与镜像加速 ----------
# 候选 Docker Hub 代理镜像（国内服务器直连 Docker Hub 通常不通）。
# 这些是完整 Hub 代理，能拉取 pgvector/pgvector、traefik/traefik 等非
# library/ 命名空间镜像（仅代理 library 的镜像源对此类镜像无能为力）。
# 镜像源可能随时间失效，安装时会对每个候选做连通性校验并自动跳过失效者。
MIRRORS=(
  "docker.1ms.run"
  "docker.m.daocloud.io"
  "docker.1panel.live"
  "dockerproxy.net"
  "docker.xuanyuan.me"
)

# 测试一个注册表路径是否可达：拉取一个不存在的 tag（alpine:notellm-probe）。
# 可达时 daemon 立即返回“not found”（exit≠124）；被墙/挂起时由 timeout 杀掉
# （exit=124）。不下载任何字节、不命中任何缓存、每次都是真实注册表往返。
# 不能用 `docker manifest inspect`——部分镜像源/部分 docker 版本对它会挂起。
probe_registry() {
  timeout -k 3 20 docker pull "${1}library/alpine:notellm-probe" >/dev/null 2>&1
  [[ $? != 124 ]]
}

# 直连 Docker Hub 是否可用（含 daemon 级 registry-mirror 的效果——compose 用
# 普通镜像名时走的就是这条路径）。
check_dockerhub_direct() {
  probe_registry ""
}

# 测试镜像代理是否可用。
check_mirror() {
  probe_registry "$1"
}

# 选择镜像加速。已有 .env 配置时保留；交互模式让用户选择；--yes 非交互模式
# 先测直连，不通则自动挑选第一个可用的代理镜像。镜像地址统一带尾部斜杠。
select_registry_mirror() {
  step "网络与镜像加速"
  # 优先级：环境变量显式指定 > 已有 .env 配置 > 交互选择 / 自动探测。
  local env_mirror="${REGISTRY_MIRROR:-}"
  if [[ -n "$env_mirror" ]]; then
    REGISTRY_MIRROR="$env_mirror"
    ok "使用环境变量指定的镜像加速：$REGISTRY_MIRROR"
  else
    local existing; existing="$(env_get REGISTRY_MIRROR || true)"
    if [[ -n "$existing" ]]; then
      REGISTRY_MIRROR="$existing"
      ok "保留已有镜像加速：$REGISTRY_MIRROR"
    else
      local direct=0
      if check_dockerhub_direct; then
        direct=1
        info "可直连 Docker Hub。"
      else
        info "无法直连 Docker Hub，将使用代理镜像。"
      fi
      REGISTRY_MIRROR=""
      if [[ "$direct" == "1" ]] && { [[ "$ASSUME_YES" == "1" ]] || [[ ! -t 0 ]]; }; then
        : # 非交互 + 可直连 → 不加速
      elif [[ "$ASSUME_YES" != "1" ]] && [[ -t 0 ]]; then
        info "选择 Docker Hub 代理镜像（用于拉取 pgvector/traefik 等非官方命名空间镜像）："
        info "  0) 直连 Docker Hub（不加速）"
        local i=1 m
        for m in "${MIRRORS[@]}"; do
          info "  $i) $m"
          i=$((i + 1))
        done
        info "  $i) 自定义地址"
        local choice=""
        while true; do
          printf '请输入 [0-%d] [0] ' "$i" >&2
          IFS= read -r choice || true
          if [[ "$choice" == "" ]] || [[ "$choice" == "0" ]]; then
            REGISTRY_MIRROR=""; break
          fi
          if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#MIRRORS[@]} )); then
            REGISTRY_MIRROR="${MIRRORS[$((choice - 1))]}/"; break
          fi
          if [[ "$choice" == "$i" ]]; then
            local custom=""
            printf '请输入镜像地址（例如 docker.1ms.run）: ' >&2
            IFS= read -r custom || true
            REGISTRY_MIRROR="${custom%/}/"; break
          fi
          warn "无效输入，请输入 0-$i"
        done
      else
        for m in "${MIRRORS[@]}"; do
          if check_mirror "$m/"; then
            REGISTRY_MIRROR="$m/"
            break
          fi
        done
      fi
    fi
  fi

  # pip / npm 镜像：环境变量 > 已有 .env > 默认（有镜像时默认国内源，否则官方源）。
  PYPI_INDEX_URL="${PYPI_INDEX_URL:-$(env_get PYPI_INDEX_URL || true)}"
  NPM_REGISTRY="${NPM_REGISTRY:-$(env_get NPM_REGISTRY || true)}"
  if [[ -n "$REGISTRY_MIRROR" ]]; then
    if ! check_mirror "$REGISTRY_MIRROR"; then
      warn "镜像 $REGISTRY_MIRROR 当前不可用（连通性测试失败）。"
      warn "  已写入配置；部署失败时可编辑 .env 更换 REGISTRY_MIRROR，或留空直连。"
    else
      ok "Docker Hub 镜像加速：$REGISTRY_MIRROR"
    fi
    PYPI_INDEX_URL="${PYPI_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}"
    NPM_REGISTRY="${NPM_REGISTRY:-https://registry.npmmirror.com}"
  else
    ok "直连 Docker Hub。"
  fi
}

# ---------- 配置收集 ----------
collect_config() {
  step "收集配置"
  select_registry_mirror

  if [[ "$PROFILE" == "prod" ]]; then
    local def
    def="$(env_get DOMAIN)"; [[ -n "$def" ]] || def="$ARGS_DOMAIN"
    ask_var DOMAIN "你的域名（例如 example.com）" "$def"
    while [[ -z "$DOMAIN" ]] || [[ "$DOMAIN" == "localhost" ]]; do
      if [[ "$ASSUME_YES" == "1" ]] || [[ ! -t 0 ]]; then
        err "生产部署需要一个公网域名。请用环境变量指定后再运行："
        info "  DOMAIN=example.com bash install.sh --prod --yes"
        exit 1
      fi
      warn "生产部署需要一个公网域名，且 DNS 需已指向本服务器。"
      DOMAIN=""
      ask_var DOMAIN "你的域名（例如 example.com）" ""
    done
    FRONTEND_HOST="https://${DOMAIN}"
    ENVIRONMENT="production"
    info "  前端地址将使用 ${FRONTEND_HOST}"
    ask_var STACK_NAME "栈名称（同一服务器多个部署时需唯一）" "$(env_get STACK_NAME || true)"
    STACK_NAME="${STACK_NAME:-notellm}"
    # EMAIL 是常见环境变量，用内部变量 LE_EMAIL 提问，避免意外继承。
    # Let's Encrypt 邮箱仅用于证书到期提醒，不验证邮箱是否存在——
    # 未提供时自动用 admin@域名 兜底，无需任何前置准备。
    LE_EMAIL="${EMAIL:-}"
    local le_default; le_default="$(env_get EMAIL || true)"
    [[ -n "$le_default" ]] || le_default="admin@${DOMAIN}"
    ask_var LE_EMAIL "Let's Encrypt 证书通知邮箱（用于证书续期提醒）" "$le_default"
    LE_AUTO=0
    if [[ -z "$LE_EMAIL" ]]; then
      LE_EMAIL="admin@${DOMAIN}"
      LE_AUTO=1
    elif [[ "$LE_EMAIL" == "admin@${DOMAIN}" ]] && [[ -z "${EMAIL:-}" ]]; then
      LE_AUTO=1
    fi
    EMAIL="$LE_EMAIL"
  else
    DOMAIN="localhost"
    FRONTEND_HOST="http://localhost:5173"
    ENVIRONMENT="local"
    STACK_NAME="$(env_get STACK_NAME || true)"; STACK_NAME="${STACK_NAME:-notellm}"
    EMAIL=""
  fi

  PROJECT_NAME="NoteLLM"
  if [[ "$PROFILE" == "prod" ]]; then
    BACKEND_CORS_ORIGINS=""
  else
    BACKEND_CORS_ORIGINS="http://localhost,http://localhost:5173"
  fi

  # 管理员账户
  ask_var FIRST_SUPERUSER "管理员邮箱（用于首次登录）" "$(env_get FIRST_SUPERUSER || true)"
  FIRST_SUPERUSER="${FIRST_SUPERUSER:-admin@example.com}"
  local def_pass; def_pass="$(env_get FIRST_SUPERUSER_PASSWORD || true)"
  [[ -n "$def_pass" ]] || def_pass="$(gen_secret 24)"
  ask_secret_var FIRST_SUPERUSER_PASSWORD "管理员登录密码" "$def_pass"

  # 数据库
  local def_db; def_db="$(env_get POSTGRES_PASSWORD || true)"
  [[ -n "$def_db" ]] || def_db="$(gen_secret 32)"
  ask_secret_var POSTGRES_PASSWORD "数据库密码" "$def_db"
  POSTGRES_USER="$(env_get POSTGRES_USER || true)"; POSTGRES_USER="${POSTGRES_USER:-postgres}"
  POSTGRES_DB="$(env_get POSTGRES_DB || true)"; POSTGRES_DB="${POSTGRES_DB:-app}"

  # SECRET_KEY（签名 JWT + 派生加密用户密钥，必须 ≥32 字符）
  local def_sk; def_sk="$(env_get SECRET_KEY || true)"
  [[ -n "$def_sk" ]] || def_sk="$(gen_secret 48)"
  ask_secret_var SECRET_KEY "SECRET_KEY（JWT/密钥加密）" "$def_sk"

  # 邮箱验证
  echo
  info "邮箱验证：注册后需点击邮件链接，服务端免费额度只对已验证账户开放。"
  local smtp_default="n"; [[ "$PROFILE" == "prod" ]] && smtp_default="y"
  SMTP_HOST="$(env_get SMTP_HOST || true)"
  if [[ -n "$SMTP_HOST" ]] || confirm "配置邮箱验证（SMTP）？生产环境建议配置" "$smtp_default"; then
    local d_host; d_host="$(env_get SMTP_HOST || true)"
    if [[ -z "$d_host" ]] && confirm "使用 Resend 推荐的 SMTP 参数（smtp.resend.com）？" "y"; then
      SMTP_HOST="smtp.resend.com"; SMTP_PORT="587"; SMTP_TLS="True"; SMTP_SSL="False"; SMTP_USER="resend"
      # 兼容常见约定：已设置 RESEND_API_KEY 环境变量时直接复用。
      if [[ -z "${SMTP_PASSWORD:-}" ]] && [[ -n "${RESEND_API_KEY:-}" ]]; then
        SMTP_PASSWORD="$RESEND_API_KEY"
        ok "检测到 RESEND_API_KEY，已自动用作 SMTP 密钥。"
      fi
      ask_secret_var SMTP_PASSWORD "Resend API Key（免费注册 resend.com → API Keys 创建；回车留空跳过）" "$(env_get SMTP_PASSWORD || true)"
      local def_from; def_from="$(env_get EMAILS_FROM_EMAIL || true)"
      [[ -n "$def_from" ]] || def_from="no-reply@${DOMAIN}"
      ask_var EMAILS_FROM_EMAIL "发件人地址（发送域名需在 Resend 完成 SPF/DKIM 验证）" "$def_from"
    else
      ask_var SMTP_HOST "SMTP 服务器地址" "$d_host"
      ask_var SMTP_PORT "SMTP 端口" "$(env_get SMTP_PORT || true)"; SMTP_PORT="${SMTP_PORT:-587}"
      if confirm "SMTP 使用 TLS？" "y"; then
        SMTP_TLS="True"; SMTP_SSL="False"
      else
        SMTP_TLS="False"; SMTP_SSL="False"
      fi
      ask_var SMTP_USER "SMTP 用户名" "$(env_get SMTP_USER || true)"
      ask_secret_var SMTP_PASSWORD "SMTP 密码" "$(env_get SMTP_PASSWORD || true)"
      ask_var EMAILS_FROM_EMAIL "发件人地址" "$(env_get EMAILS_FROM_EMAIL || true)"
    fi
  else
    SMTP_HOST=""; SMTP_USER=""; SMTP_PASSWORD=""; EMAILS_FROM_EMAIL=""
    SMTP_PORT="587"; SMTP_TLS="True"; SMTP_SSL="False"
  fi

  # SMTP 密码为空时避免半成品：验证邮件会发不出去、新用户卡在未验证。
  # 非交互直接关闭；交互则确认一次（默认跳过），用户也可明确选择保留。
  if [[ -n "$SMTP_HOST" ]] && [[ -z "${SMTP_PASSWORD:-}" ]]; then
    if [[ "$ASSUME_YES" == "1" ]] || [[ ! -t 0 ]]; then
      warn "非交互模式未提供 SMTP_PASSWORD，已暂时关闭邮箱验证。"
      info "  之后可在 .env 补填 SMTP_PASSWORD 后重启： docker compose up -d"
      SMTP_HOST=""; SMTP_USER=""; SMTP_PASSWORD=""; EMAILS_FROM_EMAIL=""
    elif confirm "SMTP 密码为空，验证邮件将无法发送。本次跳过邮箱验证？" "y"; then
      warn "已跳过邮箱验证（可稍后在 .env 补填 SMTP_PASSWORD 后重启）。"
      SMTP_HOST=""; SMTP_USER=""; SMTP_PASSWORD=""; EMAILS_FROM_EMAIL=""
    fi
  fi

  # 模型
  echo
  info "模型：可在“设置 → 模型配置”中由用户自带 Key（BYOK），也可配置服务端默认密钥。"
  LLM_BASE_URL="$(env_get LLM_BASE_URL || true)"
  if [[ -n "$LLM_BASE_URL" ]] || confirm "配置服务端默认模型密钥（聊天 + 嵌入）？" "n"; then
    info "  对话模型（OpenAI 兼容，例如 DeepSeek）："
    local d_chat; d_chat="$(env_get LLM_BASE_URL || true)"; [[ -n "$d_chat" ]] || d_chat="https://api.deepseek.com/v1"
    ask_var LLM_BASE_URL "Base URL" "$d_chat"
    ask_secret_var LLM_API_KEY "API Key" "$(env_get LLM_API_KEY || true)"
    local d_model; d_model="$(env_get LLM_MODEL || true)"; [[ -n "$d_model" ]] || d_model="deepseek-chat"
    ask_var LLM_MODEL "模型名" "$d_model"
    info "  嵌入模型（例如智谱 embedding-3，1024 维）："
    local d_emb; d_emb="$(env_get EMBEDDING_BASE_URL || true)"; [[ -n "$d_emb" ]] || d_emb="https://open.bigmodel.cn/api/paas/v4"
    ask_var EMBEDDING_BASE_URL "Base URL" "$d_emb"
    ask_secret_var EMBEDDING_API_KEY "API Key" "$(env_get EMBEDDING_API_KEY || true)"
    local d_embm; d_embm="$(env_get EMBEDDING_MODEL || true)"; [[ -n "$d_embm" ]] || d_embm="embedding-3"
    ask_var EMBEDDING_MODEL "模型名" "$d_embm"
    local d_dim; d_dim="$(env_get EMBEDDING_DIMENSIONS || true)"; [[ -n "$d_dim" ]] || d_dim="1024"
    ask_var EMBEDDING_DIMENSIONS "向量维度" "$d_dim"
    if [[ -z "$LLM_API_KEY" || -z "$EMBEDDING_API_KEY" ]]; then
      warn "API Key 留空会导致服务端默认模型不可用；用户可登录后在“设置 → 模型配置”自带 Key。"
    fi
  else
    LLM_BASE_URL=""; LLM_API_KEY=""; LLM_MODEL=""
    EMBEDDING_BASE_URL=""; EMBEDDING_API_KEY=""; EMBEDDING_MODEL=""; EMBEDDING_DIMENSIONS="1024"
  fi
}

# ---------- 写 .env ----------
write_env() {
  step "生成 .env"
  if [[ -f "$ENV_FILE" ]] && [[ "$FORCE" != "1" ]]; then
    ok "已存在 .env，保留现有配置（如需重新生成：rm .env && bash install.sh，或 --force）。"
    return 0
  fi
  if [[ -f "$ENV_FILE" ]]; then
    local bak
    bak="${ENV_FILE}.bak.$(date +%s)"
    cp "$ENV_FILE" "$bak"
    warn "已备份旧配置到 $bak"
  fi

  : > "$ENV_FILE"

  env_header "Generated by install.sh — 请勿提交本文件到版本库"
  env_put DOMAIN "$DOMAIN"
  env_put FRONTEND_HOST "$FRONTEND_HOST"
  env_put ENVIRONMENT "$ENVIRONMENT"
  env_put PROJECT_NAME "$PROJECT_NAME"
  env_put STACK_NAME "$STACK_NAME"
  # 全屏截图水印文字（前端从 /meta/watermark 读取）。
  env_put WATERMARK_TEXT "${WATERMARK_TEXT:-$DOMAIN}"
  # 水印总开关（false 则完全关闭）。
  env_put WATERMARK_ENABLED "${WATERMARK_ENABLED:-true}"
  env_put BACKEND_CORS_ORIGINS "$BACKEND_CORS_ORIGINS"
  # 国内服务器镜像加速：REGISTRY_MIRROR 留空 = 直连 Docker Hub；否则为代理
  # 镜像地址（末尾带 /）。PYPI_INDEX_URL / NPM_REGISTRY 为空 = 用默认源。
  env_put REGISTRY_MIRROR "$REGISTRY_MIRROR"
  env_put PYPI_INDEX_URL "$PYPI_INDEX_URL"
  env_put NPM_REGISTRY "$NPM_REGISTRY"
  # 显式 URL 必须配套 SHA-256 值或校验文件 URL。本地产物读取同名
  # .sha256；Release 仅下载与当前精确 Git tag 匹配的版本。
  env_put FRONTEND_DIST_URL "${FRONTEND_DIST_URL:-}"
  env_put FRONTEND_DIST_SHA256 "${FRONTEND_DIST_SHA256:-}"
  env_put FRONTEND_DIST_SHA256_URL "${FRONTEND_DIST_SHA256_URL:-}"
  env_put NOTELLM_RELEASE_TAG "${NOTELLM_RELEASE_TAG:-}"
  if [[ "$PROFILE" == "prod" ]]; then
    env_header "Let's Encrypt / Traefik（生产）"
    env_put EMAIL "$EMAIL"
  fi

  env_header "安全密钥（自动生成）"
  env_put SECRET_KEY "$SECRET_KEY"
  env_put FIRST_SUPERUSER "$FIRST_SUPERUSER"
  env_put FIRST_SUPERUSER_PASSWORD "$FIRST_SUPERUSER_PASSWORD"

  env_header "数据库"
  env_put POSTGRES_SERVER "localhost"
  env_put POSTGRES_HOST_PORT "5433"
  env_put POSTGRES_PORT "5432"
  env_put POSTGRES_DB "$POSTGRES_DB"
  env_put POSTGRES_USER "$POSTGRES_USER"
  env_put POSTGRES_PASSWORD "$POSTGRES_PASSWORD"

  env_header "邮箱验证（留空 SMTP_HOST 则关闭，注册自动视为已验证）"
  env_put SMTP_HOST "$SMTP_HOST"
  env_put SMTP_USER "$SMTP_USER"
  env_put SMTP_PASSWORD "$SMTP_PASSWORD"
  env_put SMTP_PORT "${SMTP_PORT:-587}"
  env_put SMTP_TLS "${SMTP_TLS:-True}"
  env_put SMTP_SSL "${SMTP_SSL:-False}"
  env_put EMAILS_FROM_EMAIL "${EMAILS_FROM_EMAIL:-info@example.com}"
  env_put EMAILS_FROM_NAME "$PROJECT_NAME"
  # 注册/改密邮箱域名白名单（逗号分隔）；设为 * 放行任意域名。
  env_put ALLOWED_EMAIL_DOMAINS "${ALLOWED_EMAIL_DOMAINS:-163.com,qq.com,gmail.com,126.com,outlook.com,hotmail.com,foxmail.com,139.com,sina.com,icloud.com}"

  env_header "模型（留空则仅支持用户自带 Key）"
  env_put LLM_BASE_URL "$LLM_BASE_URL"
  env_put LLM_API_KEY "$LLM_API_KEY"
  env_put LLM_MODEL "$LLM_MODEL"
  env_put EMBEDDING_BASE_URL "$EMBEDDING_BASE_URL"
  env_put EMBEDDING_API_KEY "$EMBEDDING_API_KEY"
  env_put EMBEDDING_MODEL "$EMBEDDING_MODEL"
  env_put EMBEDDING_DIMENSIONS "${EMBEDDING_DIMENSIONS:-1024}"

  env_header "其他"
  env_put SENTRY_DSN ""
  env_put DOCKER_IMAGE_BACKEND "backend"
  env_put DOCKER_IMAGE_FRONTEND "frontend"
  chmod 600 "$ENV_FILE"
  ok "已生成 .env（权限 600，仅当前用户可读）。"
}

# ---------- 准备网络（生产） ----------
prepare_network() {
  if [[ "$PROFILE" != "prod" ]] || [[ "$DRY_RUN" == "1" ]]; then
    return 0
  fi
  step "准备 Traefik 公共网络"
  if docker network inspect traefik-public >/dev/null 2>&1; then
    ok "traefik-public 网络已存在。"
  else
    docker network create traefik-public
    ok "已创建 traefik-public 网络。"
  fi
}

# ---------- 低内存模式：注入预构建的前端 dist ----------
# 从 FRONTEND_DIST_URL / 仓库内 frontend-dist.tar.gz / GitHub Release 资产
# 获取预构建的 SPA，解包进 frontend 容器挂载的 frontend-dist 卷（nginx 直接
# 从这个目录提供服务，无需重启容器）。
sync_frontend_dist() {
  [[ "$LOW_MEM" == "1" ]] || return 0
  if [[ "$DRY_RUN" == "1" ]]; then
    info "  [dry-run] 将把前端 dist 注入 frontend-dist 卷（来源见 --low-mem 说明）"
    return 0
  fi

  local archive="" expected_hash="" checksum_file=""
  local dist_url dist_sha dist_sha_url release_tag asset_name release_base
  local dist_tmp
  dist_tmp="$(mktemp -d "${TMPDIR:-/tmp}/notellm-dist.XXXXXX")"
  dist_url="${FRONTEND_DIST_URL:-$(env_get FRONTEND_DIST_URL || true)}"
  dist_sha="${FRONTEND_DIST_SHA256:-$(env_get FRONTEND_DIST_SHA256 || true)}"
  dist_sha_url="${FRONTEND_DIST_SHA256_URL:-$(env_get FRONTEND_DIST_SHA256_URL || true)}"

  # 1) Explicit URL: fail closed instead of silently switching artifacts.
  if [[ -n "$dist_url" ]]; then
    info "下载前端 dist：$dist_url"
    archive="$dist_tmp/frontend-dist.tar.gz"
    if ! curl -fLsS --max-time 300 --max-filesize 52428800 "$dist_url" -o "$archive"; then
      rm -rf -- "$dist_tmp"
      err "FRONTEND_DIST_URL 下载失败。"
      return 1
    fi
    if [[ -n "$dist_sha_url" ]]; then
      checksum_file="$dist_tmp/frontend-dist.sha256"
      if ! curl -fLsS --max-time 60 --max-filesize 4096 "$dist_sha_url" -o "$checksum_file"; then
        rm -rf -- "$dist_tmp"
        err "FRONTEND_DIST_SHA256_URL 下载失败。"
        return 1
      fi
      expected_hash="$(sed -nE 's/^([0-9A-Fa-f]{64})([[:space:]].*)?$/\1/p' "$checksum_file" | head -n 1)"
    else
      expected_hash="$dist_sha"
    fi
    if [[ -z "$expected_hash" ]]; then
      rm -rf -- "$dist_tmp"
      err "FRONTEND_DIST_URL 必须同时提供 FRONTEND_DIST_SHA256 或 FRONTEND_DIST_SHA256_URL。"
      return 1
    fi
  # 2) Local artifact: require the build script's sibling checksum file.
  elif [[ -f "$SCRIPT_DIR/frontend-dist.tar.gz" ]]; then
    archive="$SCRIPT_DIR/frontend-dist.tar.gz"
    checksum_file="$SCRIPT_DIR/frontend-dist.tar.gz.sha256"
    info "使用本地产物：$archive"
    if [[ ! -f "$checksum_file" ]]; then
      rm -rf -- "$dist_tmp"
      err "本地产物缺少校验文件：$checksum_file"
      return 1
    fi
    expected_hash="$(sed -nE 's/^([0-9A-Fa-f]{64})([[:space:]].*)?$/\1/p' "$checksum_file" | head -n 1)"
  # 3) Release artifact: bind it to the exact checked-out source tag.
  else
    release_tag="${NOTELLM_RELEASE_TAG:-$(env_get NOTELLM_RELEASE_TAG || true)}"
    if [[ -z "$release_tag" ]] && [[ -d "$SCRIPT_DIR/.git" ]]; then
      release_tag="$(git -C "$SCRIPT_DIR" describe --tags --exact-match --match 'v*' HEAD 2>/dev/null || true)"
    fi
    if [[ ! "$release_tag" =~ ^v[0-9A-Za-z._-]+$ ]]; then
      rm -rf -- "$dist_tmp"
      err "当前源码不在精确发布 tag；为避免前后端版本错配，不下载 latest 产物。"
      info "  请 checkout 发布 tag，或提供 FRONTEND_DIST_URL + SHA-256。"
      return 1
    fi
    asset_name="frontend-dist-${release_tag}.tar.gz"
    release_base="https://github.com/au1bhi/NoteLLM/releases/download/${release_tag}"
    archive="$dist_tmp/$asset_name"
    checksum_file="$dist_tmp/$asset_name.sha256"
    info "下载匹配源码版本的前端产物：$release_tag"
    if ! curl -fLsS --max-time 300 --max-filesize 52428800 \
      "$release_base/$asset_name" -o "$archive" \
      || ! curl -fLsS --max-time 60 --max-filesize 4096 \
      "$release_base/$asset_name.sha256" -o "$checksum_file"; then
      rm -rf -- "$dist_tmp"
      err "发布产物或校验文件下载失败：$release_tag"
      return 1
    fi
    expected_hash="$(sed -nE 's/^([0-9A-Fa-f]{64})([[:space:]].*)?$/\1/p' "$checksum_file" | head -n 1)"
  fi

  if [[ -z "$archive" ]]; then
    rm -rf -- "$dist_tmp"
    err "低内存模式需要预构建的前端产物，但未找到任何来源。"
    info "  在内存充足的机器上运行：bash scripts/build-frontend-dist.sh"
    info "  然后上传产物（frontend-dist.tar.gz 放到仓库根目录，或设置 FRONTEND_DIST_URL），"
    info "  再重新运行 install.sh。"
    return 1
  fi

  if ! verify_sha256 "$archive" "$expected_hash" \
    || ! validate_tar_archive "$archive" 104857600 1; then
    rm -rf -- "$dist_tmp"
    return 1
  fi
  ok "前端产物 SHA-256 与归档结构校验通过。"

  step "注入前端静态资源到 frontend-dist 卷"
  "${compose_cmd[@]}" cp "$archive" "frontend:/tmp/notellm-dist.tar.gz"
  [[ "$archive" == "$SCRIPT_DIR/frontend-dist.tar.gz" ]] || rm -rf -- "$dist_tmp"
  "${compose_cmd[@]}" exec frontend sh -c \
    'find /usr/share/nginx/html -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + && tar -xzf /tmp/notellm-dist.tar.gz --no-same-owner --no-same-permissions -C /usr/share/nginx/html && rm -f /tmp/notellm-dist.tar.gz'
  [[ "$archive" != "$SCRIPT_DIR/frontend-dist.tar.gz" ]] || rm -rf -- "$dist_tmp"
  ok "前端静态资源已注入（低内存模式，未在服务器上构建）。"
}

# ---------- 构建并启动 ----------
build_and_start() {
  local compose_cmd
  # Compose v2 may default to Bake when a buildx plugin is present. A broken or
  # non-executable plugin then crashes Compose before the Dockerfile runs. The
  # backend Dockerfile intentionally supports the standard builder; callers
  # can still opt back into Bake with COMPOSE_BAKE=true.
  export COMPOSE_BAKE="${COMPOSE_BAKE:-false}"
  if [[ "$PROFILE" == "prod" ]]; then
    # 生产：显式指定文件，跳过 compose.override.yml 的本地端口映射。
    compose_cmd=(docker compose -f compose.yml -f compose.traefik.yml)
  else
    # 本地：显式列出 override，避免与低内存文件合并时顺序混乱。
    compose_cmd=(docker compose -f compose.yml -f compose.override.yml)
  fi
  if [[ "$LOW_MEM" == "1" ]]; then
    # 低内存：frontend 改用纯 nginx 镜像 + frontend-dist 卷（SPA 不在此构建）。
    compose_cmd+=(-f compose.lowmem.yml)
  fi

  if [[ "$DRY_RUN" == "1" ]]; then
    info "  [dry-run] 将执行: ${compose_cmd[*]} up -d --build"
    sync_frontend_dist
    return 0
  fi

  step "构建并启动服务（首次构建需要几分钟）"
  # A completed one-shot container may otherwise be reused across an upgrade
  # when its mutable image tag did not change as expected. Removing only this
  # stateless container guarantees the freshly built migration graph runs; the
  # database and upload volumes are untouched.
  "${compose_cmd[@]}" rm -sf prestart >/dev/null
  "${compose_cmd[@]}" up -d --build

  # 低内存模式：前端 dist 由外部注入（构建时已跳过 SPA）。
  sync_frontend_dist

  # 健康检查
  local health_url
  if [[ "$PROFILE" == "prod" ]]; then
    # DOMAIN 在保留已有 .env（SKIP_CONFIG）路径下不会由 collect_config 赋值，
    # 这里从 .env 兜底读取，避免 set -u 下 unbound variable。
    health_url="https://api.${DOMAIN:-$(env_get DOMAIN || true)}/api/v1/utils/health-check/"
  else
    health_url="http://localhost:8000/api/v1/utils/health-check/"
  fi
  if ! command -v curl >/dev/null 2>&1; then
    warn "跳过健康检查（未安装 curl）。可稍后执行: docker compose ps"
    return 0
  fi

  local waited=0
  info "等待服务就绪（最长 120 秒）..."
  while (( waited < 120 )); do
    if curl -fsS --max-time 5 "$health_url" >/dev/null 2>&1; then
      ok "服务已就绪。"
      return 0
    fi
    sleep 3; waited=$((waited + 3))
  done
  warn "等待超时。请检查日志：${compose_cmd[*]} logs -f"
  if [[ "$PROFILE" == "prod" ]]; then
    warn "如果 https 一直无法访问，通常是 DNS 尚未指向本服务器，或 Let's Encrypt 证书签发失败。"
  fi
}

# ---------- 总结 ----------
print_summary() {
  # 展示信息以 .env 为准：收集模式刚写入，保留模式读已有值，两者都一致。
  # 无条件赋值（包括空值），避免 set -u 下出现未定义变量。
  local k
  for k in DOMAIN FRONTEND_HOST FIRST_SUPERUSER FIRST_SUPERUSER_PASSWORD \
           SMTP_HOST SMTP_PASSWORD LLM_API_KEY EMAIL; do
    printf -v "$k" '%s' "$(env_get "$k" || true)"
  done
  echo
  echo "=============================================================================="
  local mode_label="本地开发"; [[ "$PROFILE" == "prod" ]] && mode_label="生产部署"
  local run_suffix=""; [[ "$DRY_RUN" == "1" ]] && run_suffix="（dry-run，未实际启动）"
  ok "NoteLLM ${mode_label} 配置完成${run_suffix}"
  echo "=============================================================================="
  if [[ "$PROFILE" == "prod" ]]; then
    info "  前端:       https://${DOMAIN}"
    info "  API 健康检查: https://api.${DOMAIN}/api/v1/utils/health-check/"
    info "  管理员:     ${FIRST_SUPERUSER}"
    info "  管理员密码已写入权限为 600 的 .env，本摘要不回显。"
    info "  Let's Encrypt 邮箱: ${EMAIL}（仅用于证书到期提醒）"
    echo
    warn "部署前请确认 DNS 已全部指向本服务器公网 IP："
    info "    A  ${DOMAIN}          → <本机公网 IP>"
    info "    A  api.${DOMAIN}      → <本机公网 IP>"
    if [[ "${LE_AUTO:-0}" == "1" ]]; then
      info "  Let's Encrypt 邮箱自动使用了 ${EMAIL}（未配置时兜底）。"
      info "  如需接收证书到期提醒，编辑 .env 的 EMAIL 后重启即可。"
    fi
  else
    info "  前端:       http://localhost:5173"
    info "  API 文档:   http://localhost:8000/docs"
    echo
    info "  管理员:     ${FIRST_SUPERUSER}"
    info "  管理员密码已写入权限为 600 的 .env，本摘要不回显。"
  fi
  if [[ -n "$SMTP_HOST" ]]; then
    echo
    info "  邮件验证已启用（${SMTP_HOST}）。发送域名的 SPF/DKIM/DMARC 记录见 README“邮件发送与部署”。"
    if [[ -z "${SMTP_PASSWORD:-}" ]]; then
      warn "  SMTP 密码为空：请编辑 .env 中的 SMTP_PASSWORD，否则发信会失败。"
    fi
  else
    echo
    warn "  未配置邮箱验证：新注册账户自动视为已验证（仅适合试用）。"
    info "  启用：注册 resend.com 拿到 API Key → 编辑 .env 填 SMTP_HOST/SMTP_PASSWORD/EMAILS_FROM_EMAIL → docker compose up -d"
  fi
  if [[ -z "$LLM_API_KEY" ]]; then
    echo
    warn "  未配置服务端默认模型：登录后请在“设置 → 模型配置”填入自己的 API Key 再提问/上传。"
  fi
  echo
  info "  常用命令："
  info "    查看日志    docker compose logs -f"
  info "    停止        docker compose down"
  info "    重启        docker compose up -d"
  if [[ "$LOW_MEM" == "1" ]]; then
    info "    更新前端    在内存充足的机器上运行 scripts/build-frontend-dist.sh，"
    info "                上传 frontend-dist.tar.gz 后重跑本脚本"
    info "    升级        重新运行 install.sh（保留 .env，只重新构建/注入）"
    echo
    warn "  低内存模式：前端 SPA 不在服务器上构建。"
    info "    dist 来源优先级：FRONTEND_DIST_URL > 仓库内 frontend-dist.tar.gz > GitHub Release。"
    info "    想回到镜像内构建：--no-low-mem（需内存 ≥ ${LOW_MEM_MB}MB，可用 LOW_MEM_MB 调整阈值）。"
  else
    info "    升级        git pull && bash install.sh   （保留 .env，只重新构建）"
  fi
  echo
  warn ".env 含有真实密钥，请勿提交到版本库。"
}

main() {
  banner
  [[ -f "$SCRIPT_DIR/compose.yml" ]] || {
    err "未找到 compose.yml，请在 NoteLLM 仓库目录下运行 install.sh。"
    exit 1
  }
  check_prereqs
  profile_select
  select_low_mem
  local SKIP_CONFIG=0
  if [[ -f "$ENV_FILE" ]] && [[ "$FORCE" != "1" ]]; then
    if confirm "检测到已有 .env。保留现有配置并直接启动？" "y"; then
      ok "保留现有 .env。"
      SKIP_CONFIG=1
    else
      FORCE=1
    fi
  fi
  if [[ "$SKIP_CONFIG" != "1" ]]; then
    collect_config
    write_env
  fi
  prepare_network
  build_and_start
  print_summary
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  parse_args "$@"
  main
fi
