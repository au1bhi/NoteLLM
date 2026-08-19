# 第 7 章　实现与部署（粘贴用草稿）

> 用法：写本仓库真实能走通的路径。示例主机只用 RFC 2606 的 `notellm.example.com` / `example.com`，不要写作者的反代域名。评测不要打开发用的 Compose 5433。

## 7.1 运行时与仓库布局

后端 Python ≥ 3.12，FastAPI + SQLModel，Alembic 管理 schema。前端 React / Vite，OpenAPI 生成客户端。聊天与嵌入走 OpenAI 兼容 HTTP，密钥只在后端。本地与生产共用同一套 `compose.yml`；开发叠加 `compose.override.yml`，生产显式指定 `compose.yml`，低内存机再叠加 `compose.lowmem.yml` 并下载 Release 里的预构建 `frontend-dist`。

源码树里的 `img/` 曾经放过上游模板截图，现已清空，论文插图不要从那里取。演示数据用 `docs/demo/` 与 `backend/scripts/seed_demo.py`，脚本要求显式指定已有账户，默认不覆盖。

## 7.2 本地复现

1. 复制 `.env.example` 为 `.env`，填入服务端模型地址与密钥。不要把填好的 `.env` 提交进版本库。
2. 仓库根目录 `docker compose up -d` 拉起 `pgvector/pgvector:pg18`（开发端口默认映射到主机 **5433**）和前后端；容器启动门禁会在服务前串行迁移。
3. 若改为宿主机直启后端，运行 `bash scripts/run-local-backend.sh`。脚本读取 Compose 的实际映射端口并先执行迁移门禁，避免自定义端口时误连其他 PostgreSQL。
4. 浏览器打开 `http://localhost:5173`，API 在 `http://localhost:8000`。生产环境关闭 `/docs`。

检查：后端 `uv run pytest`（必须另起隔离 pgvector，**不要**把 pytest 指到 5433 或本机 5432）、Ruff、mypy、ty；前端 `bun run lint` 与生产构建。单元测试使用假 provider，不消耗外部额度。

## 7.3 一键安装与生产

仓库根目录 `install.sh` 支持 `--local` / `--prod` / `--low-mem` / `--dry-run`。生产侧前面是 Traefik，负责 TLS 与按子域分流。文档里的域名写成 `notellm.example.com`：

- 前端 `https://dashboard.notellm.example.com`
- API `https://api.notellm.example.com`
- Traefik / Adminer 走 HTTP Basic Auth

低内存机不要在服务器上现场编译前端，改为下载 GitHub Release 的 `frontend-dist-<tag>.tar.gz` 并核对 SHA-256。部署后确认 Alembic 位于当前 `head`，后端与 scheduler 健康且无重启循环。

密钥类环境变量（`SECRET_KEY`、`POSTGRES_PASSWORD`、`FIRST_SUPERUSER_PASSWORD`）必须换成 `secrets.token_urlsafe(32)` 生成的值；生产环境 `SECRET_KEY` 强制不少于 32 个字符。SMTP 未配置时学习计划仍可生成，只是打不开邮件提醒。

## 7.4 评测复现

固定语料在 `docs/evaluation/sources/`，34 题在 `questions.csv`，语料外 6 题在 `questions-ooc.csv`。脚本是 `backend/scripts/evaluate_retrieval.py`。

基线数字引用 2026-07-23、提交 `cb0ead1` 的 `latest-results.md`，不要改写成「最新一次」除非另存新报告。新的消融或模式对照写入 `docs/evaluation/runs/`，命令形如：

```bash
uv run python scripts/evaluate_retrieval.py \
  --top-k 5 --mode grounded \
  --chunk-size 1000 --chunk-overlap 150 \
  --with-answers \
  --report ../docs/evaluation/runs/topk-5-grounded.md
```

必须在隔离库上跑，跑完脚本会删临时用户与文件。不要覆盖 `latest-results.md`。不要把 Recall@5 = 100% 抄成开放域结论。

## 7.5 本章不写的内容

不把 Kubernetes、服务网格、多活容灾写成已实现。CI 用隔离 pgvector service container，不读取开发者根目录 `.env`。作者真实反代域名和 SMTP 账号只存在本机环境，论文与仓库示例一律用保留域。
