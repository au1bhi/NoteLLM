# NoteLLM 实施计划

## 使用规则

每次开始开发前，先阅读本文件和 `GOAL.md`。只处理当前阶段中标记为“进行中”的项目；完成后更新状态、验收证据和下一步。需求与本计划冲突时，以用户最新明确指令为准。

## 阶段 0：范围与设计（已完成）

- 已在 `GOAL.md` 固化 MVP、非目标、验收标准和技术边界。
- 已在 `API_AND_UX.md` 绘制笔记本列表、工作区和上传/处理状态流程。
- 已在 `DESIGN.md` 定义核心实体、最小字段和用户隔离规则。
- 已选择 OpenAI-compatible 配置、PyMuPDF、pgvector 和本地文件存储；实施前需验证支持 pgvector 的 PostgreSQL 镜像。

验收证据：`DESIGN.md` 和 `API_AND_UX.md`。可开始修改应用代码。

## 阶段 1：笔记本与来源元数据（已完成）

- 已以 Alembic 迁移建立 Notebook 和 Source 元数据。
- 已实现 Notebook 的用户隔离 CRUD、来源列表 API 和笔记本基础页面。
- 已为 Notebook 创建、查询、更新、删除与跨用户访问编写 pytest 测试。
- 已生成正式 OpenAPI 客户端，并将 `frontend/src/services/notebooks.ts` 改为对生成 `NotebooksService` 的上传适配层。

验收证据：2026-07-23 已在 Docker PostgreSQL 上应用 Alembic 至 `4d2a6b1c8f90`，并通过后端全套 pytest（67 项）、前端 TypeScript 类型检查和 Vite 生产构建。

## 阶段 2：文档摄取（已完成）

- 已支持 PDF、TXT、Markdown 上传；限制大小和类型，并保存到 Docker volume。
- 已实现文本提取、页码保留、分块、处理状态、删除清理，以及失败后的重试操作。
- 已补充上传、分块和跨用户访问测试；`mypy`、`ty`、Ruff 与分块冒烟检查已于 2026-07-23 通过，并已在 Docker PostgreSQL 上通过集成测试。

验收证据：后端全套 pytest 于 2026-07-23 通过（67 项），其中包括笔记本与来源摄取接口测试。

## 阶段 3：检索与问答（已完成）

- 已接入 OpenAI-compatible 嵌入 provider：上传处理会批量写入 Chunk 向量；`POST /api/v1/notebooks/{notebook_id}/search` 以 pgvector cosine distance 返回当前笔记本的 ready 来源 Top-K Chunk，包含来源名、页码和相似度。provider 配置缺失或返回错误维度时，来源会安全地标记为失败而非生成不完整索引。
- 已建立 Conversation、Message 和 Citation 持久化；`POST /api/v1/conversations/{conversation_id}/messages/stream` 通过 SSE 返回答案、引用和完成事件。模型仅能返回本次检索的 Chunk ID，服务端会丢弃未知 ID；无证据或无有效引用时固定返回资料不足。
- 已在笔记本工作区显示会话、流式答案、来源名、页码和稳定摘录；刷新后从持久化消息恢复。

完成条件：端到端 MVP 闭环可演示，引用能回到正确来源。

验收证据：2026-07-23 已在 `pgvector/pgvector:pg18`（vector 0.8.5）上迁移至 `d4e8a2c5f731`，并通过后端完整 pytest（75 项，含真实 pgvector cosine 排序、笔记本隔离和 SSE 事件序列测试）、Ruff、mypy、ty、OpenAPI 路由检查和 Vite 生产构建（Node 22.23.1）。使用智谱 Embedding-3（1024 维）和 DeepSeek V4 Flash 完成了临时 TXT 上传、分块、向量写入、检索、SSE 回答、引用持久化和清理的真实端到端验收。

## 阶段 4：体验、评测与交付（进行中）

- 已保存和展示对话历史，并覆盖空状态、错误状态和删除清理。
- 已在工作区顶部提供始终可见的退出登录入口；退出时会清理本地访问令牌和当前用户缓存。
- 已建立 34 个问题的固定合成评测集；`backend/scripts/evaluate_retrieval.py` 在独立临时数据上计算 Recall@5、自动引用来源匹配、关键词忠实度筛查和耗时，并在结束时清理临时用户、向量和文件。完整方法见 `docs/evaluation/README.md`，首份结果见 `docs/evaluation/latest-results.md`。
- 已补充架构图（`ARCHITECTURE.md`）和约 6 分钟的答辩演示脚本（`DEFENSE_DEMO.md`）。
- 已补充可重复导入的合成 Docker 演示资料（`docs/demo/` 与 `backend/scripts/seed_demo.py`）；脚本要求显式指定已有账户，默认不覆盖数据。
- 已重写 GitHub 首页 `README.md`，说明产品能力、可信回答机制、架构、启动方式、演示、接口、评测结果与项目边界。
- 补充实验结果的人工忠实度复核。

2026-08 迭代（体验、额度与安全加固）：
- 全链路中文化：登录/注册/设置/管理页/表格/提示与时间显示改为中文，kraft/ink（牛皮纸 + 水墨）主题统一，底部 toast 同步主题。
- 免费额度系统：对话 10 万 token、嵌入 30 万字符，仅统计服务端计费用量；自备 Key 的用户对应维度不限额。额度按自然月惰性重置，并在问答流/检索/上传/概览/学习指南入口以原子化“预留—结算”方式拦截超额（防并发绕过与单次超大上传击穿）。
- 自备密钥（BYOK）：加密存储、掩码返回；支持 OpenAI 兼容 API 格式选择（含路径 / 根域名自动补 /v1），模型列表可自动探测 `/v1`；配置自己的 Key 后切回系统 API 需 24 小时冷却。
- 新手引导：首页“快速上手”四步引导（配置模型 → 创建笔记本 → 上传资料 → 提问），设置页支持 `?tab=model` 深链，模型配置页显示当前计费来源。
- 会话卡片支持删除；设置页 tabs 移动端可横向滚动；多个 UX 细节修复（无就绪资料时提示、ModelPicker 陈旧列表、无障碍标签、额度将尽提示等）。
- 安全加固：登录/注册/改密等接口限流（429 带 Retry-After）；SSRF 校验解析 DNS 并拦截十进制/十六进制/简写 IP 与私有/回环/云元数据地址；`SECRET_KEY` 生产环境强制 ≥32 字符；移除未鉴权的 `/private` 路由；SSE 越权改为前置依赖返回 404；nginx 增加 CSP 与安全响应头；提示词增加“不得复述指令”约束。
- 可移植性：后端要求降为 Python ≥3.12（去除 3.14 专属 `except A, B:` 语法与前置类引用，改括号形式与字符串前置引用），便于开源社区与论文复现环境接入。
- CI 可靠性：后端测试改用隔离的 pgvector GitHub Actions service container，不再依赖未提交的根目录 `.env`；Docker Compose 冒烟测试显式验证 `.env.example`、安装 Buildx、检查前后端健康状态并始终清理资源；移除无项目价值且会在覆盖率产物缺失时制造连锁失败的 Smokeshow。
- 对话学习计划：可从会话生成 3—60 天学习甘特图，由模型判断难度并给出阶段目标、每日投入与验收方式；任务完成状态可持久化。邮件提醒默认关闭，仅已验证邮箱可主动开启；独立 scheduler 按用户时区每天 09:00 投递当日未完成任务，并以数据库原子认领防止同日重复发送。
- 开源首页：论文名称统一为“基于FastAPI与RAG的个人学习问答系统设计与实现”，README 精简为论文价值、可复现实验、开源复用价值与最短部署入口。

2026-08 迭代验收证据：后端全套 pytest 131 项通过（含 SSRF 绕过表单、原子额度预留、会话删除、SSE 越权、API 格式等新增用例），mypy 与 Ruff 通过；前端 `bun run --filter frontend build` 与 lint 通过。2026-08-04 已根据此后 Git 历史与当前代码再次同步 `AGENTS.md`，补充邮箱身份/验证、令牌撤销、配额预留—结算、固定公网 IP 的 provider 请求、一键部署与低内存构建约束。

2026-08-04 CI 修复验收：测试夹具现固定发件地址及完全虚假的服务端聊天/嵌入配置，不再读取开发者根目录 `.env`；在无 `.env` 的临时源码副本和独立 `pgvector/pgvector:pg18` 中完整执行迁移及 183 项后端测试，全部通过，覆盖率 84%（门槛 80%），HTML 覆盖率报告可生成。仅使用 `.env.example` 的干净环境通过 `docker compose config`，确认后端 8000、前端 5173 端口及本地非 external 网络配置；修改后的工作流通过 YAML/TOML 检查和 Zizmor 审计。完整 Docker 镜像构建已进入依赖安装阶段，但本机直连 PyPI 长时间停滞后主动终止，最终结果以推送后的 GitHub-hosted Runner 为准。

2026-08-04 生产部署验收：在 2 核、约 1.6 GiB 内存的 Ubuntu 22.04 ECS 上验证 `install.sh --prod --yes --dry-run` 会自动选择低内存 Compose；当前 `compose.yml + compose.traefik.yml + compose.lowmem.yml` 配置合法，后端与 PostgreSQL 健康且无重启/OOM，Alembic 位于 `46a98a434c83 (head)`，pgvector 为 0.8.5。公网前端与 API 健康检查返回 200，生产 `/docs` 返回 404，Adminer/Traefik 返回 401，TLS 与 CSP/HSTS 等响应头有效。服务器 Git 已通过离线 bundle 重建为干净、可追踪的 `master`，旧目录完整备份于 `/root/NoteLLM.backup.20260804-221139`。Cloudflare Bot Fight Mode 注入脚本现使用 nginx 每响应 nonce，CSP 同时精确允许 Web Analytics 域名而未放开 `unsafe-inline` / `unsafe-eval`；线上已验证 CSP nonce 与注入脚本 nonce 一致。仍待处理：安装总结展示已关闭的生产 `/docs` 链接；SSH 仍允许 root 密码登录。

2026-08-04 学习计划与发布验收：Alembic 从空库完整升级至 `8f2c1a7e9d04`；在独立 `pgvector/pgvector:pg18` 中通过 189 项后端测试，覆盖率 84%（门槛 80%），包括计划生成、跨用户隔离、邮箱验证门槛、9:00 投递、主动关闭与同日去重。前端 lint 和生产构建通过；普通及低内存 Compose 配置解析通过；完整 pre-commit（Biome、Ruff、mypy、ty、OpenAPI 客户端一致性与 Zizmor）通过。Release 工作流生成版本化 `frontend-dist-<tag>.tar.gz` 与 SHA-256 校验和，供 `install.sh` 自动发现。

2026-08-05 上传服务商连通性修复：为仅由部署者配置的服务端聊天/嵌入模型增加可选 `SERVER_PROVIDER_PROXY_URL`。它解决 Clash Fake-IP 将公网域名解析为保留地址而触发 SSRF 防护的误判；用户 BYOK 地址继续走 DNS 解析、公网地址校验与 IP 固定请求，不能使用此代理。已在独立 pgvector 数据库通过嵌入 provider 代理分支与 SSRF 测试，并通过 Ruff、mypy、ty 和 Compose 配置检查。

2026-08-05 会话删除与线上功能验收：服务器此前停留在 `2164748` / `46a98a434c83`，缺少学习计划数据表，删除带计划的会话会返回 500。已快进部署至学习计划版本并运行迁移 `8f2c1a7e9d04`；后端与 scheduler 健康。新增覆盖“会话删除级联清理学习计划及任务”的回归测试；独立 pgvector 环境中后端 192 项测试、Ruff、mypy、ty 均通过，前端生产构建和 Biome lint 通过。

2026-08-13 聚合甘特图：新增 `GET /api/v1/study-plans`，按当前用户聚合全部会话计划并附带笔记本/对话标题；侧边栏增加「甘特图」入口，把所有计划画在同一条时间轴上，并可通过 `?conversation=` 回到对应会话。

2026-08-13 论文完备性审计：`THESIS_READINESS_AUDIT.md` 对照问题、设计、实现、测试、实验、复现和论文材料，结论为核心功能已经充足，不再新增产品模块；BYOK/SSRF、原子额度与邮箱身份、精确提醒调度、低内存生产安全等归入工业化加固，不作为本科论文主创新。评测脚本补充模式对照直接需要的引用率、精确资料不足次数和无引用仍作答次数，并修复临时评测用户未满足当前规范邮箱模型、动态旧接口绕过类型检查的问题；离线单元测试、Ruff、mypy 与 ty 已通过。

完成条件：可复现演示和论文所需证据齐全。

2026-08-14 安全修复：管理员 `DELETE /users/{id}` 与自助删号一样先 `delete_owner_upload_files`，避免 volume 残留上传原文；认证限流改按 `X-Forwarded-For` 最右跳（代理实际观察到的地址）分桶，伪造最左跳不能绕过登录节流；概览/学习指南把规则放到 `system`、资料放到 `user`；前端 Markdown 只保留 http(s) 链接并加 `noopener noreferrer`。

2026-08-18 配额与会话服务重构：新增统一的用量预留上下文，成功时按实际 provider 用量结算、异常时回滚会话并仅退还真实预留额度，BYOK 零预留维度不产生幽灵结算；搜索、资料处理、问答、概览、学习指南、模型发现与学习计划均移除手写 reserve/settle 分支。会话详情组装与回答持久化迁入 service 层，用户/助手消息在模型成功后成对提交，同时保留中文 SSE 分块及路由 monkeypatch 兼容入口。独立 pgvector 数据库中相关 API/service 测试 84 项通过，聚焦 Ruff、mypy、ty 均通过。

## 当前下一步

2026-08-19 安全、服务重构与前端体验验收：登录、注册和找回密码已按公开元数据按需加载 Cloudflare Turnstile，并通过统一请求头提交一次性 token；CSP 仅增加官方 challenge 域名。认证限流迁入 PostgreSQL 以跨 worker 原子共享，可信代理链、IPv6 `/64`、活跃桶上限和 Cloudflare Tunnel 专用回源端口均有回归。JWT 与 Fernet 使用 HKDF 分域子密钥并兼容读取旧格式；CORS 方法/请求头显式列举。统一配额上下文覆盖检索、摄取、回答、概览、学习指南、模型发现和学习计划，BYOK 零预留与跨月结算有独立测试；会话详情和回答持久化迁入 service 层，provider 失败不再留下孤立消息。前端流式问答补充阶段状态、后端错误正文、断流提示和“停止接收”操作，明确客户端中止不等于取消已开始的后台模型调用或持久化；会话深链、加载、错误与重试状态已补齐。仓库尚无前端自动化测试框架，静态证据与人工验收矩阵见 `docs/evaluation/frontend-quality.md`。

最终验收在独立 pgvector 数据库完成：后端 267 项测试全部通过，覆盖率 88%；mypy、ty、Ruff 与格式检查通过。OpenAPI 客户端重新生成且一致，前端 Biome lint、TypeScript `noEmit` 和 Vite 生产构建通过（为避开 NTFS 工作区目录删除阻塞，构建在 `/tmp` ext4 的同锁文件源码副本完成，2450 个模块、退出码 0）。Alembic 当前数据库与 head 均为 `6ea2d54c90f1`；本地、Traefik 生产、Traefik + 低内存三套 Compose 配置通过。完整 `uv run prek run --all-files`（含 Biome、Ruff、mypy、ty、OpenAPI、Zizmor）通过，`git diff --check` 无错误。三个独立代理分别复核前端认证、运行登录链路与安全/限流；复核发现并修复了查询 429 无限重试、认证断网英文提示、迁移门与限流准入锁 ID 冲突，并补充迁移失败解锁测试。

2026-08-19 登录可用性补充验收：根因是宿主机 FastAPI 曾把容器内 `POSTGRES_PORT=5432` 当成 Compose 发布端口，而实际 `.env` 使用 `POSTGRES_HOST_PORT=55440`，限流按设计 fail-closed 后显示“请求保护服务暂时不可用”。新增 `scripts/run-local-backend.sh` 从 `docker compose port db 5432` 发现实际端口、执行迁移门禁后再启动 API；所有宿主机开发、演示和论文命令已同步。主库确认 `rate_limit_bucket` 存在且 Alembic 为 `6ea2d54c90f1`；实际 health/readiness/正确登录/`users/me` 均返回 200，错误密码保持通用 400。主库 collation 版本漂移已在 `/tmp` 备份后执行 `REINDEX DATABASE app` 与 `ALTER DATABASE app REFRESH COLLATION VERSION`，记录值和运行值均为 2.36，随后登录仍成功。

在隔离库上按 `docs/evaluation/ablation-protocol.md` 与 `answer-mode-protocol.md` 实跑，把数字抄进空表；新报告写入 `docs/evaluation/runs/`，不要覆盖 2026-07-23 基线。然后完成新轮人工忠实度复核、按 `SCREENSHOTS.md` 本机截图，并将第 1—8 章草稿改写进学校模板且补齐文内引用。项目功能已足够，默认不再添加产品模块、依赖或服务；完整范围判断见 `THESIS_READINESS_AUDIT.md`。

2026-08-21 交互体验、安全加固与 CI 完备性验收：
- **多会话与计划下拉选择**：前端会话列表重构为紧凑响应式 `<Select>` 下拉框，整合重命名、置顶、删除与新建会话；聚合甘特图工具栏新增按计划/会话筛选器。
- **代码块与排版增强**：Markdown 新增自定义 CodeBlock 组件，支持语法高亮语言徽章与一键复制代码；保持 KaTeX 行内/块级数学公式排版。
- **模型容错与上下文记忆**：`clean_json_text` 剥离 `<think>` 思考标签，增强 JSON 抽取与纯文本降级保护；修复 `answers.py` 中 `knowledge` 模式检索分支判断与多轮对话记忆召回。
- **安全加固与越权测试**：在 `test_study_plans.py` 中补充跨用户 IDOR 越权访问/修改/删除 404 隔离测试；学习计划调整增加 `<instruction>` 和 `<conversation>` 独立沙箱与提示词防注入规则。
- **轻量服务器部署规范与文档升级**：在 `AGENTS.md` 明确“严禁在轻量服务器上构建”铁律；全面重构 GitHub `README.md`，增加架构图、在线演示、评测指标与低内存部署/Release 机制说明。
- **验收证据**：后端 275 项 pytest 测试全量通过（100% 通过率），代码覆盖率 84%（超过 80% 门禁线）；前端 TypeScript 类型检查与 Biome lint 0 错误；线上 VPS（`https://notellm.au1bhi.com`）全链路自动化测试与健康检查全部通过。

阶段 4 当前验收证据：2026-07-23 使用 7 份合成 Markdown 资料、34 个固定问题、智谱 Embedding-3（1024 维）与 DeepSeek V4 Flash 运行评测；Recall@5 为 100.0%，自动引用来源匹配率为 97.1%，关键词忠实度筛查为 88.2%，检索平均/P95 为 339/894 ms，回答平均/P95 为 2904/5595 ms。人工对照摘录后 **34 通过 / 0 未通过**（见 `docs/evaluation/human-faithfulness.md`）；Q32 是来源级标注碰撞，Q04 / Q09 / Q34 是关键词假阴性，均非幻觉。`--top-k` / `--chunk-size` / `--mode` / `--questions` 已接通，消融与模式对照表待本机实跑。

2026-09-21 Cloudflare Tunnel 运维修复：SSH 核对线上应用及数据库容器健康、loopback 回源 readiness 返回 200。`cloudflared-notellm` 历史日志存在 QUIC 握手/空闲超时、四连接同时中断及 DNS 解析超时；排查时隧道已自行恢复，不能据此确定用户本次错误的精确发生时间。仅为该 systemd 服务新增 `/etc/systemd/system/cloudflared-notellm.service.d/transport.conf`，设置 `TUNNEL_TRANSPORT_PROTOCOL=http2` 并重启；四连接均以 HTTP/2 注册，`/ready` 返回 200 / readyConnections=4，请求错误计数为 0，开机启动保持 enabled。公网首页、登录页、入口 HTML 引用的 JS/CSS、health/readiness 与公开元数据接口全部返回 200。回滚方式为移除此新增 drop-in、daemon-reload 并重启该服务。此次仅调整服务器隧道传输配置，未变更或构建应用、未执行前后端测试套件、未提交或同步源码；验收限于实际部署的访问与健康检查，不代表已验证登录后 RAG 功能或长期链路稳定性。

2026-10-09 红队摘要修复（代码及本地验收完成，上线待连接恢复）：保留 IP 登录限流并增加规范化账号维度 10 次/300 秒共享限流；非 local 环境禁止关闭限流，增加 Turnstile 必需配置门禁。上传 NUL/控制字符返回 400，五处分页统一有界校验并返回 422；BYOK 保存与调用时校验 HTTPS/443、可选精确域名允许列表，传输层禁止重定向；nginx 使用相对重定向且 `/docs` 交由后端生产配置返回 404。独立 pgvector 空库迁移至 `7c3f9a1b2d40`，407 项后端测试通过、覆盖率 91%，SSRF/Turnstile/security/provider settings/rate limit/usage 六模块覆盖率 100%；mypy、ty、Ruff（含格式）、前端 lint、TypeScript 与 Vite 生产构建通过，客户端由脚本重新生成。真实 nginx + 生产模式后端容器验证登录、用户查询、笔记本创建/删除、非法分页 422、原始 multipart NUL 文件名 400、非法 provider URL 422、轮换客户端 IP 后第 11 次登录 429 与 Retry-After；双 listener 的 `/api` 仅相对跳转、文档端点 404、readiness 200，nginx -t、生产低内存 Compose 配置与 alembic check 通过。线上只读复核仍存在 8081 Location 泄露及 Turnstile disabled；SSH 多次握手/响应超时，未部署、未启用验证码。详细范围、兼容性、待配置项和复验步骤见 `docs/security/redteam-remediation-2026-10-09.md`；公网 BYOK 本属产品能力，默认空允许列表不等于封闭全部公网出站。

2026-10-09 红队复现条件补充：已将用户提供的 finding 44 与登录测试条件写入 `docs/security/redteam-remediation-2026-10-09.md`。10 次错误登录未越过原有 20 次/60 秒 IP 阈值，不能支持“无限速”；公网域名 8081 的 curl 000/12 秒超时不能证明内网可达，503/耗时也不能单独证明目标收到了请求。写侧接受私网 URL 的校验不一致已由本轮修复覆盖。原始 worker 证据路径不在本工作区，注明为用户提供而非独立审阅。用户确认未配置有效 Turnstile 密钥，上线仍待 SSH 恢复及密钥配置。本次只校正文档，代码验证沿用同轮 407 项测试及真实容器验收。

2026-10-09 Turnstile 既有 widget 接入：使用用户提供的公开 site key `0x4AAAAAAFSZqpTS9XSOMui_`，补齐登录/注册/找回密码的 action 绑定、Siteverify 严格 success/action/hostname 校验，以及提交后的单次 token 重置。新增 `TURNSTILE_HOSTNAMES` 部署级精确允许列表；启用时列表不能为空，生产拒绝本地主机/私网地址。421 项后端测试通过、覆盖率 91%，安全关键模块保持 100%；mypy/ty/Ruff、前端 lint/类型检查/生产构建、生成客户端、生产 Compose 检查均通过。真实本地 nginx/后端容器确认公开 site key 元数据、三处缺 token 均 400、readiness 200；容器仅用明确标记的占位 secret，不代表真实验证成功。前端预构建包位于 `/tmp/notellm-turnstile-frontend-dist.tar.gz`。用户确认未安装 Wrangler，既有 widget 流程要求审批项目外的固定版本 CLI、账号与 secret 写入清单；尚未获取或存储真实 secret，SSH 仍超时，实际 token 成功/重放验收及部署待完成。见 `docs/security/turnstile-integration.md`。

2026-10-10 Turnstile 已部署与 3x-ui 移除：用户批准项目外 Wrangler 4.109.0、OAuth、CLI 返回账户和生产写入清单；真实密钥在内存中通过 Siteverify 校验，经 SSH stdin 写入 ignored `.env`（0600），启用 site key/required/精确 hostname。资源压力阻塞部署后，按明确授权正常重启 VPS；系统恢复并稳定约 11 小时。服务器已快进至 a8397d5，本地预构建前端注入数据卷；通过 `/root/notellm-runtime.yml` 挂载新版 nginx，无 VPS 构建。公网 metadata enabled=true、readiness 200；三处缺 token 的回源请求 400，文档 404，`/api` 相对重定向；nginx/Compose 检查、容器健康通过。421 项后端测试与前端 lint/类型检查/构建为同一已部署代码的本地证据。真实生产挑战在自动化浏览器失败/超时，用户普通浏览器验证后用不存在账号提交得到“邮箱或密码错误”，首次通过由用户人工确认；用户再重放原 access-token 请求，确认 400“人机验证失败”，真实验证码首次通过及单次使用边界已完成人工验收；此证据不代表登录后 RAG 全流程。按用户要求停止/禁用并移除 3x-ui 程序、配置及 unit，root-only 备份 `/root/3x-ui-backup-20261010.tar.gz`；服务 not-found/inactive，无 x-ui/xray 进程，两条隧道及 NoteLLM 健康。详细部署命令、回滚产物与验证边界见 `docs/security/turnstile-integration.md`。

2026-10-10 低内存部署调整：按用户要求在服务器 `/root/notellm-runtime.yml` 设置后端为 2 workers，保留 migration gate 与 `--no-proxy-headers`，仅无构建重建 backend。运行时确认两 worker + 一 resource tracker；容器 healthy、公网 readiness 200、Turnstile enabled=true、登录页 200、缺 token 登录 400。后端内存样本从约 641 MiB 降至 431 MiB；此前覆盖文件备份 `/root/notellm-runtime.before-workers-20261010.yml`。未改应用源码或前端产物，本次配置验证采用生产 Compose 检查与实际容器/接口验证；应用测试证据沿用同一代码的 421 项后端及前端 lint/类型检查/构建。


2026-10-22 论文复测驱动的通用修复（本机隔离验证，未提交/部署）：混合历史回顾与明确文档事实请求保留检索；纯历史回顾/问候保留无资料路径，任意非空历史不再绕过 grounded 文档依据要求。增强逐陈述引用支持、必要/充分条件、排他范围与“未规定”提示词，但不声称保证忠实度。保留 Citation.quote 500字符快照；新增非持久化可选 chunk_content，通过授权会话同笔记本关联块组装并同步SSE，前端可展开滚动查看“完整引用片段”（非完整文件/永久归档）；客户端由既有生成脚本在隔离副本生成，无数据库迁移。新增32项回归，最终后端453项全部通过（原421+新增32），覆盖率91.0180%（含branch），85%及安全100/99门槛通过；mypy、ty、Ruff check/format、前端TypeScript/Biome只读check/生产构建均通过。Chromium新profile/loopback预置合成记录完成10项检查，确认500字符后依据展开可见、折叠隐藏、刷新后仍可展开、其他用户404；仅本轮进程使用--no-sandbox，不代表默认浏览器安全配置或真实上传/模型闭环。保留7次假SMTP域名DNS阻断、概览无模型503和权限反例404，不能证明邮件送达。旧代码新增25项先运行10通过/15失败，单句比较路由另保留2项失败；原始日志与修复前后源码/测试/runner已归档。真实同题模型生成与独立评估由后续单独实验记录，本条不代替其结论。未改论文、生产配置或现有数据库；未commit/push。
