# NoteLLM

> 面向个人学习与研究的、带可追溯引用的文档问答系统。

NoteLLM 是一个参考 Google NotebookLM 核心体验实现的毕业设计原型：用户将课程讲义、研究资料或笔记放入笔记本，在限定资料范围内提问，系统通过检索增强生成（RAG）给出答案，并展示答案所依据的来源、PDF 页码（适用时）和原文摘录。

它的重点不是成为通用聊天机器人，而是证明一条可演示、可验证、可评估的本地 RAG 闭环。

## 产品能力

| 能力 | 说明 |
| --- | --- |
| 用户与数据隔离 | JWT 登录；笔记本、来源和会话均按 `owner_id` 隔离，跨用户访问返回 `404`。 |
| 笔记本管理 | 创建、浏览、修改与删除个人笔记本；每个笔记本管理独立的资料与会话。 |
| 文档摄取 | 支持 UTF-8 TXT、Markdown 与 PDF；校验文件类型和大小，保存处理状态与失败原因。 |
| 文本解析与分块 | TXT/Markdown 读取文本；PDF 以 PyMuPDF 提取并保留页码。默认按 1,000 字符分块，150 字符重叠。 |
| 向量检索 | 使用 PostgreSQL + pgvector；问题与分块向量以余弦距离在当前笔记本范围内检索 Top-5 证据。 |
| 受控问答 | chat provider 只能依据本轮检索到的分块回答，并且只能引用本轮候选的 chunk ID。 |
| 可验证引用 | 后端过滤未知引用 ID；界面展示来源名、页码（适用时）和稳定摘录。无有效证据时固定回复“资料不足”。 |
| 流式会话 | 通过 Server-Sent Events（SSE）流式呈现答案、引用与完成事件；消息和引用会持久化，刷新后仍可恢复。 |
| 安全删除 | 删除来源时同步删除上传文件、分块和向量；删除笔记本时级联清理其来源与会话。 |
| 演示体验 | 工作区提供会话历史、来源处理状态、错误提示和始终可见的退出登录按钮。 |
| 新手引导 | 首页“快速上手”四步引导（配置模型 → 创建笔记本 → 上传资料 → 提问），完成状态实时打勾、可关闭；设置页支持 `?tab=model` 深链。 |
| 自备密钥（BYOK） | 每个用户可在“设置 → 模型配置”填入自己的对话/嵌入 API Key（OpenAI 兼容），加密存储、只回传掩码；支持选择 API 格式（已含路径 / 根域名自动补 `/v1`），模型列表可自动探测 `/v1`。 |
| 免费额度 | 服务端计费用量按自然月统计：对话 10 万 token、嵌入 30 万字符；自备 Key 的维度不限额。额度以原子化“预留—结算”拦截并发与单次超大上传，超额返回友好提示。 |
| 会话管理 | 会话支持重命名、置顶与删除（删除带确认框，级联清理消息与引用）。 |

## 安全加固

- 认证接口（登录/注册/找回与重置密码/改密/模型探测）按 IP 限流，429 响应携带 `Retry-After`。
- 邮箱验证采用**用途隔离**的签名 token（验证与密码重置分开 `purpose`，互不可复用）；注册即发送验证链接，重发按 IP 限流；公开注册接口返回**不含账户信息的最小响应**，新注册与已存在邮箱返回完全相同的 body，无法枚举已注册地址（已存在分支还会跑一次密码哈希以均衡响应时序）。
- **注册域名白名单**：注册与修改邮箱仅限常见邮箱域名（默认 `ALLOWED_EMAIL_DOMAINS=163.com,qq.com,gmail.com,…`，可配置，设为 `*` 放行任意域名），且在排队发信前即拦截——注册、管理员建号、改邮箱三条入口统一校验，任何新地址都无法向白名单外投递。白名单是**写时强制**：既有账户保留其地址（避免改策略导致无法找回密码），恢复/重发不再复查。找回密码对**未注册**邮箱返回明确的“该邮箱未注册”（404）而非虚报已发送；这是刻意的诚实取舍，配合域名白名单与按收件人冷却，可探测面被限制在允许注册的域名内。
- **密码变更即吊销既有令牌**：JWT 与密码重置 token 都携带 `password_changed_at` 快照（微秒精度），改密、重置后所有已签发令牌立即失效；重置 token 因此天然单次使用。
- 用户提供的模型 Base URL 在**每次出站请求时**重新解析并校验（私有/回环/链路本地/保留/组播/云元数据/RFC 6598 CGNAT 地址，含十进制/十六进制/简写 IP 等绕过形式），随后把连接**固定到已校验的公网 IP**（`Host` 头 + TLS SNI 保持原主机名），阻断 DNS rebinding 绕过；出站请求不读取代理环境变量。
- 生产环境默认关闭 `/docs`、`/redoc` 与 OpenAPI 契约（`ENVIRONMENT=production`）；Adminer 数据库面板与 Traefik 面板同受 HTTP Basic Auth 保护，不再裸奔公网。
- 前端生产部署（nginx）附带 CSP（`connect-src 'self'`）、HSTS、`X-Content-Type-Options` / `X-Frame-Options` 等安全响应头；提示词以 `system` 角色承载系统规则、上传资料作为不可信 `user` 输入，且模型回答输出有 token 上限。
- 每个用户上传总量上限 100 MiB（超出返回 413 并清理文件）；删除笔记本/账户时同步清理磁盘上的上传文件，不残留孤儿文件。
- `SECRET_KEY` 生产环境强制 ≥32 字符（它既签 JWT 又派生加密用户密钥的 Fernet key）；`.env` 不允许提交。
- 密钥只在后端读取与加密存储；自定义端点永不携带服务端密钥。
- 已移除模板遗留的未鉴权 `/private` 用户创建路由；SSE 会话越权改为请求前依赖校验，返回干净的 404。

> 已知取舍：生产以 4 个 worker 运行，认证限流与**按收件人的发信冷却**都是**进程内**状态（各 worker 独立、按反代解析出的真实客户端 IP 计数；收件人冷却在 4 worker 下约为 4 封/分钟/收件人）。单机部署下已足够；若需跨进程的全局强一致限流，可把 `rate_limit` 的存储换成 Redis（接口不变）。

## 用户流程

```mermaid
flowchart LR
    A[注册或登录] --> B[创建笔记本]
    B --> C[上传 TXT / Markdown / PDF]
    C --> D[提取文本、分块、向量化]
    D --> E{来源是否 ready}
    E -->|是| F[在笔记本内提问]
    E -->|否| G[显示失败原因或重试]
    F --> H[Top-5 pgvector 检索]
    H --> I[流式生成受控答案]
    I --> J[展示来源、页码与摘录]
    J --> K[持久化并重开会话]
```

## 工作原理

```mermaid
flowchart TB
    Browser[React / Vite 浏览器] -->|API + SSE| API[FastAPI]
    API --> Auth[JWT 与所有权校验]
    API --> Ingest[解析、分块、摄取]
    API --> Retrieval[pgvector 检索]
    API --> Answer[提示词与引用校验]
    Ingest --> Files[本地上传 Volume]
    Ingest --> Embedding[Embedding Provider]
    Retrieval --> DB[(PostgreSQL + pgvector)]
    Answer --> DB
    Answer --> Chat[Chat Provider]
```

### 可信回答约束

1. 后端只检索当前用户当前笔记本中 `ready` 的来源分块。
2. 上传文本被视为不可信输入，不能覆盖系统的问答规则。
3. 模型只接收本轮检索证据，并以 JSON 返回答案和引用的 chunk ID。
4. 后端只接受属于本轮候选集的引用；未知 ID 会被移除。
5. 没有检索证据或没有有效引用时，系统不输出无依据的正常答案，而是明确说明资料不足。

完整架构与安全边界见 [架构说明](docs/project/ARCHITECTURE.md)。

## 技术栈

- 前端：React 19、TypeScript、Vite、TanStack Router/Query、Tailwind CSS、shadcn/ui
- 后端：Python ≥ 3.12、FastAPI、SQLModel、Pydantic、Alembic、PyMuPDF
- 数据库与检索：PostgreSQL 18、pgvector、余弦距离 Top-K
- 模型：可独立配置的 OpenAI-compatible chat provider 与 embedding provider
- 工程化：Docker Compose、Bun、uv、pytest、Ruff、mypy、ty

当前示例配置使用 DeepSeek 作为聊天模型接口、智谱 Embedding-3 作为 1024 维 embedding 接口；两者都可通过环境变量替换。密钥永远只由后端读取。

## 快速开始（推荐）

### 一键安装向导

前置条件：已安装 Docker 与 Docker Compose。在终端里复制粘贴并运行：

```bash
git clone https://github.com/au1bhi/NoteLLM.git
cd NoteLLM
bash install.sh
```

`install.sh` 是交互式安装向导，自动完成全部配置——本地开发与生产部署二合一：

- **本地开发**：选择 `1`（本地）后一路回车即可。向导自动生成安全密钥并构建启动，完成后打开 <http://localhost:5173>，用输出中的管理员邮箱/密码登录。
- **生产部署**：选择 `2`（生产）后按提示填写域名并逐项确认。向导自动生成 `.env`（权限 600）、创建 `traefik-public` 网络、签发 HTTPS 证书并启动。所有密钥都是**自动生成**的，只有两样需要你提供或跳过：
  - **Let's Encrypt 通知邮箱**：任意你能收信的邮箱，仅用于证书到期提醒，**不填就自动用 `admin@域名`**。
  - **SMTP 密钥**：用于发送验证邮件。它由邮件服务商（推荐 [Resend](https://resend.com)，免费）在注册后签发，向导无法替你在对方平台生成——不填则本次跳过邮箱验证（注册即时生效），之后随时可补。
  - 此外需把**域名 A 记录**指向本服务器：`@`、`api`、`adminer`、`traefik` 四个子域（安装结尾会打印完整清单，详情见下方”邮件发送与部署”一节）。`adminer` 与 `traefik` 面板都受 HTTP Basic Auth 保护（安装结尾打印同一组用户名/密码）。

向导重复运行不会覆盖已有 `.env`（直接重启现有栈；`--force` 重新生成并备份旧文件）。常用选项：

```bash
bash install.sh --local --yes                                # 本地全自动：默认值 + 自动生成密钥
DOMAIN=notellm.au1bhi.com bash install.sh --prod --yes       # 生产全自动：只填域名，其余自动/跳过
bash install.sh --dry-run                                    # 只生成 .env 并预览命令，不实际启动
bash install.sh --help                                       # 查看全部选项
```

**没有配置过邮箱的新用户也能零准备完成部署**：`--prod --yes` 只需提供域名——Let's Encrypt 邮箱自动用 `admin@域名`，邮箱验证本次跳过（注册即时生效，适合试用）。想一并启用邮箱验证，加上 Resend 密钥（`RESEND_API_KEY` 或 `SMTP_PASSWORD` 二选一）：`DOMAIN=notellm.au1bhi.com RESEND_API_KEY=<你的Resend密钥> bash install.sh --prod --yes`。SMTP / 模型随时可在 `.env` 里补填后 `docker compose up -d`，无需重装。

### 备选：Makefile（仅本地）

```bash
make up        # 首次自动把 .env.example 复制为 .env，然后构建并启动
```

打开 <http://localhost:5173>，用 `.env` 里的 `FIRST_SUPERUSER` / `FIRST_SUPERUSER_PASSWORD` 登录（`.env.example` 默认是 `admin@example.com` / `replace-with-a-strong-password`，首次登录后请尽快在“设置 → 密码”中修改）。

### 安装后说明

- **模型默认未配置**：开箱可注册、创建笔记本，但问答/上传需要模型。两种方式任选：
  1. 编辑 `.env` 填入 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` 与 `EMBEDDING_*`（推荐服务端自用）；
  2. 登录后在 **“设置 → 模型配置”** 填入你自己的 OpenAI 兼容 API Key（浏览器内完成，密钥加密只存后端，更推荐）。
- 常用命令：`docker compose logs -f`（日志）、`docker compose down`（停止）；`make down` / `make logs` / `make ps` 等价。
- 反代客户端 IP：生产后端开启 `--proxy-headers`，默认只信任 Docker 私有网段（`FORWARDED_ALLOW_IPS=172.16.0.0/12`）中的代理；若你的 Docker 网络使用其它网段，在 `.env` 里设置 `FORWARDED_ALLOW_IPS` 为代理所在 CIDR 后重启。切勿把后端 `8000` 端口暴露到公网。
- 前端与 API 同源代理：浏览器访问 `/api/v1/...`，由 nginx 转发到后端服务，无需配置 CORS。
- 免费额度：服务端计费用量每月对话 10 万 token、嵌入 30 万字符；**使用服务端免费额度需先验证邮箱**（配置自己的 Key 的维度不限额、也无需验证）。

## 邮件发送与部署（邮箱验证 / 找回密码）

应用会发送两类邮件：**注册后的邮箱验证**（点击链接确认邮箱归属）与**找回密码**。未配置邮件后端时（`SMTP_HOST` 为空），新注册账户自动视为已验证，仅适合本地开发。

### 1. 选择邮件服务商

推荐 [Resend](https://resend.com)（免费额度 3000 封/月），也可用任意 SMTP 服务。以 Resend 为例：

1. 注册后在 **Domains** 添加一个发送子域名（例如 `notify.au1bhi.com`，只用于发信、与应用域名分离，便于隔离和撤销）。
2. 按提示在 DNS 中添加三条 TXT 记录：
   - **SPF**：`v=spf1 include:_spf.resend.com ~all`（放在发送域名的 TXT 记录上，注意整个域名只允许一条 SPF，需合并现有记录）。
   - **DKIM**：Resend 给出的 `resend._domainkey.notify.au1bhi.com` 记录值。
   - **DMARC**：建议 `v=DMARC1; p=quarantine; rua=mailto:你的邮箱`（放在 `_dmarc.notellm.au1bhi.com` 上），只对同一根域生效一次。
3. 回到 Resend 等待子域名状态变为 **Verified**（通常几分钟）。

> 子域名（而非根域）用于发送，SPF/DKIM 只覆盖它，不影响根域其他服务；DMARC 记录则放在 `_dmarc.<根域>` 上并对整根域生效。

### 2. 填入 `.env`

```env
FRONTEND_HOST=https://notellm.au1bhi.com   # 邮件中的链接指向这里
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_TLS=True
SMTP_USER=resend
SMTP_PASSWORD=<Resend SMTP 密钥>
EMAILS_FROM_EMAIL=no-reply@notify.au1bhi.com
EMAILS_FROM_NAME=NoteLLM
# 注册/改邮箱域名白名单（逗号分隔，默认常见域名列表，`*` 放行任意域名）
ALLOWED_EMAIL_DOMAINS=163.com,qq.com,gmail.com,126.com,outlook.com,hotmail.com,foxmail.com,139.com,sina.com,icloud.com
```

`SMTP_HOST` 非空即启用邮件验证：新注册用户收到含 72 小时有效链接的验证邮件；登录后应用顶部会显示"邮箱尚未验证"横幅，可一键重发；设置页可查看验证状态、重发，或修改邮箱（需输入当前密码，新邮箱需重新验证）。未验证账户仍可登录、可用自带 API Key，但**不能消耗服务端免费额度**（防批量注册刷取 LLM 成本）。

### 3. 验证发信

`docker compose up -d --build` 后用 `make logs` 观察 `backend` 日志中的 `send email result`；也可注册一个真实邮箱点击链接走完整流程。若邮件进入垃圾箱，优先检查 SPF/DKIM/DMARC 是否生效（可用 mxtoolbox 等查询）。


## 快速开始（本地开发）

### 1. 准备配置

```bash
cp .env.example .env
```

编辑本机 `.env`，至少填写：

- 数据库与安全配置：`SECRET_KEY`（**≥32 字符**，可用 `python -c "import secrets; print(secrets.token_urlsafe(48))"` 生成）、`FIRST_SUPERUSER_PASSWORD`、`POSTGRES_PASSWORD`
- 聊天模型：`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`
- 嵌入模型：`EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`、`EMBEDDING_MODEL`

`EMBEDDING_DIMENSIONS` 必须与嵌入模型及数据库迁移一致；当前默认值为 `1024`。不要提交 `.env`、模型密钥或真实上传资料。

### 2. 启动数据库并迁移

```bash
docker compose up -d db
cd backend
POSTGRES_PORT=5433 uv run alembic upgrade head
```

项目使用 `pgvector/pgvector:pg18` 镜像。可检查向量扩展：

```bash
docker compose exec db psql -U postgres -d app -c \
  "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
```

### 3. 启动后端与前端

在两个终端分别运行：

```bash
cd backend
POSTGRES_PORT=5433 uv run fastapi dev app/main.py
```

```bash
bun run --filter frontend dev
```

打开：

- 产品界面：<http://localhost:5173>
- OpenAPI 文档：<http://localhost:8000/docs>

注册账户后，创建笔记本、上传资料，等来源状态显示为 `ready`，再新建会话提问。浏览器会保留登录会话；需要切换账户时可使用工作区右上角的“退出登录”。

## 一键导入合成演示资料

仓库提供不含个人信息的演示 Markdown。先在网页注册一个本地账户，再运行：

```bash
cd backend
POSTGRES_PORT=5433 uv run python scripts/seed_demo.py \
  --email your-local-email@example.com
```

脚本会为指定账户创建“NoteLLM 答辩演示”笔记本并完成向量化；默认不会覆盖已有演示数据。确认重建时再添加 `--replace`。更多演示步骤见 [本地验收指南](docs/project/DEMO.md) 与 [答辩演示脚本](docs/project/DEFENSE_DEMO.md)。

## API 与数据模型

核心实体如下：

```text
User 1 ── * Notebook 1 ── * Source 1 ── * Chunk
                    │
                    └── * Conversation 1 ── * Message 1 ── * Citation
```

主要 API 路径：

| 类别 | 路径示例 | 用途 |
| --- | --- | --- |
| 认证 | `/api/v1/login/access-token` | 获取 JWT 访问令牌。 |
| 笔记本 | `/api/v1/notebooks` | 笔记本 CRUD。 |
| 来源 | `/api/v1/notebooks/{notebook_id}/sources` | 上传、列出、重试和删除来源。 |
| 检索 | `/api/v1/notebooks/{notebook_id}/search` | 返回当前笔记本的 Top-K 证据分块。 |
| 会话 | `/api/v1/notebooks/{notebook_id}/conversations` | 创建和读取会话。 |
| 流式问答 | `/api/v1/conversations/{conversation_id}/messages/stream` | SSE 返回答案增量、引用和完成事件。 |

以正在运行的 `/docs` 为准获取完整请求与响应模型；前端客户端由后端 OpenAPI Schema 生成，不手工修改 `frontend/src/client/`。

## 质量与评测

### 自动化检查

```bash
cd backend
POSTGRES_PORT=5433 uv run pytest -q
uv run ruff check app scripts
uv run mypy app scripts
uv run ty check app scripts
cd ..
bun run --filter frontend build
```

后端测试使用假 provider，不消耗模型额度或依赖网络；覆盖数据隔离、上传/分块失败、pgvector 排序、引用映射和 SSE 事件序列。

### 固定 RAG 评测

评测集包含 7 份合成 Markdown 资料和 34 个固定问题，可通过以下命令复跑：

```bash
cd backend
POSTGRES_PORT=5433 uv run python scripts/evaluate_retrieval.py \
  --with-answers \
  --report ../docs/evaluation/latest-results.md
```

脚本会创建临时用户、笔记本、来源与文件副本，结束时全部清理。最近一次已提交结果：

| 指标 | 结果 |
| --- | ---: |
| Recall@5 | 100.0% |
| 自动引用来源匹配 | 97.1% |
| 关键词忠实度筛查 | 88.2% |
| 检索平均 / P95 | 339 ms / 894 ms |
| 回答平均 / P95 | 2904 ms / 5595 ms |

自动引用来源匹配只检查有效引用是否命中标注来源；关键词筛查不能替代人工忠实度判断。逐题答案、已验证引用来源和人工审核栏位见 [评测报告](docs/evaluation/latest-results.md)，方法说明见 [评测说明](docs/evaluation/README.md)。

## 项目范围

NoteLLM 当前是毕业设计 MVP，刻意不包含多人实时协作、网页爬取、OCR、复杂表格/图片理解、音频概览、移动端、消息队列、多模型容灾或大规模生产运维。优先目标是一个可靠的“上传资料 → 检索 → 带引用回答 → 重开会话”的完整闭环。

## 项目文档

- [产品目标与验收标准](docs/project/GOAL.md)
- [实施计划与当前进度](docs/project/PLAN.md)
- [架构与安全边界](docs/project/ARCHITECTURE.md)
- [API 与界面流程](docs/project/API_AND_UX.md)
- [本地验收与演示](docs/project/DEMO.md)
- [答辩演示脚本](docs/project/DEFENSE_DEMO.md)
- [固定评测集与结果](docs/evaluation/README.md)
