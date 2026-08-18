# NoteLLM 生产部署

生产部署以仓库根目录的 `install.sh` 为唯一入口。脚本生成 `.env`、组合
`compose.yml` 与 `compose.traefik.yml`、运行数据库迁移并等待健康检查；低内存
主机会额外启用 `compose.lowmem.yml`，使用预构建前端产物。

## 前置条件

- Linux 主机、Docker Engine 和 Docker Compose v2。
- 一个已指向主机公网 IP 的域名；Traefik 部署还需要
  `api.<域名>`、`adminer.<域名>`、`traefik.<域名>` 的 DNS 记录。
- 对公网开放 80/443，数据库与应用管理端口不得直接暴露。
- 生产 `SECRET_KEY`、数据库密码、管理员密码均使用独立随机值。

## 安装

克隆仓库后运行交互式安装：

```bash
bash install.sh --prod
```

无人值守安装需先提供域名并接受自动生成或已有的 `.env` 配置：

```bash
DOMAIN=example.com bash install.sh --prod --yes
```

先检查将执行的操作而不启动服务：

```bash
DOMAIN=example.com bash install.sh --prod --yes --dry-run
```

内存不足 2 GiB 时脚本会自动选择低内存模式，也可显式传入 `--low-mem`。
预构建 SPA 的来源顺序为 `FRONTEND_DIST_URL`、仓库内
`frontend-dist.tar.gz`、GitHub Release；本地生成命令为
`bash scripts/build-frontend-dist.sh`。

## 必要配置

完整变量及注释见 [`.env.example`](.env.example)。生产环境至少确认：

- `ENVIRONMENT=production`，`FRONTEND_HOST=https://<域名>`。
- `SECRET_KEY` 不少于 32 个字符且不是示例值。
- `POSTGRES_PASSWORD`、`FIRST_SUPERUSER_PASSWORD` 为强随机密码。
- `BACKEND_CORS_ORIGINS` 只列真实前端来源。
- 登录、注册和找回密码需要人机验证时，同时配置 `TURNSTILE_SITE_KEY` 与
  `TURNSTILE_SECRET_KEY`；不能只配一项。`RATE_LIMIT_MAX_ACTIVE_BUCKETS` 默认
  10000，达到上限时新客户端身份失败关闭。
- 需要注册验证、找回密码和学习提醒时配置 SMTP；未配置 SMTP 的部署会把
  新账户自动视为已验证，只适合本地试用。
- 服务端默认模型密钥可留空，但用户必须在设置页配置自己的兼容 API 后才能
  上传向量资料或提问。

`.env` 包含密钥，不得提交到 Git、Release 或问题附件。

## 上线检查

```bash
docker compose ps
docker compose logs --tail=200 backend scheduler
curl -fsS https://api.example.com/api/v1/utils/health-check/
curl -fsS https://api.example.com/api/v1/utils/readiness-check/
```

还应确认：

- `docker compose run --rm prestart` 能把 Alembic 升级到当前 `head`。
- `docker compose exec -T backend alembic current --check-heads` 返回成功，且
  `rate_limit_bucket` 等当前版本数据表已存在。API 与 scheduler 的容器启动命令
  也会幂等执行该迁移门禁；镜像落后于数据库时容器会明确启动失败，不会带着
  不完整 schema 对外提供登录接口。所有启动路径使用 PostgreSQL advisory lock
  串行迁移，避免 DB 重启时多个服务竞跑同一 DDL。
- `/api/v1/utils/health-check/` 返回 200 表示 API 进程存活；
  `/api/v1/utils/readiness-check/` 返回 200 才表示 PostgreSQL 和认证限流 schema
  均可用。监控应同时记录二者，但不要因短暂数据库抖动反复重启仍存活的 API。
- 生产 `/docs` 与 `/redoc` 返回 404。
- Adminer 与 Traefik Dashboard 受 HTTP Basic Auth 保护。
- HTTPS、HSTS、CSP 等安全响应头存在，CSP 的 `script-src` 未加入
  `unsafe-inline` 或 `unsafe-eval`。
- Cloudflare Tunnel 只回源到 `http://localhost:8080`。该宿主机环回端口映射到
  nginx 专用的 8081 监听，由 nginx 将 Cloudflare 验证的客户端头转换为 XFF
  并清除原头；Traefik 继续使用普通 80 监听。不要把 8080、后端 8000、
  PostgreSQL 或管理端口暴露到公网。

## 更新与回滚准备

普通模式更新：

```bash
git pull
bash install.sh --prod --yes
```

安装器会删除并重建无状态的 `prestart` one-shot 容器，强制新镜像中的 Alembic
迁移图运行；数据库和上传 volume 不受影响。远程安装模式下若 `git pull` 失败，
升级会停止并保留当前服务，而不会继续构建旧源码并误报升级成功。

低内存模式同样重跑安装脚本，它会重新获取或注入前端产物。更新前备份数据库
与上传 volume，并记录当前 Git 提交和镜像标签；Alembic 迁移默认只向前执行，
不要把 `docker compose down -v` 用作普通停止命令。

本地开发、独立测试数据库和 lint 命令见 [development.md](development.md)。
