# NoteLLM 后端

FastAPI 单体：认证与用户隔离、笔记本与来源摄取、pgvector 检索、SSE 受控问答、对话学习计划。密钥与提示词只存在后端。

## 要求

- [Docker](https://www.docker.com/)
- [uv](https://docs.astral.sh/uv/)
- Python ≥ 3.12

## 本地开发

完整栈见 [`../development.md`](../development.md)：

```bash
docker compose watch
```

只装后端依赖时，在 `backend/`：

```bash
uv sync
source .venv/bin/activate
```

数据库 schema 用 Alembic。`fastapi dev` **不会**自动迁移；缺学习计划表时接口返回 503，需要：

```bash
alembic upgrade head
```

本地 Compose 数据库映射在主机 `5433`。**不要**对这个端口跑 pytest：套件会删用户数据。测试必须另起隔离的 pgvector 实例，见 `scripts/test.sh` 与 `docs/evaluation/security-experiments.md`。

```bash
bash scripts/lint.sh
bash scripts/test.sh
```

评测脚本 `scripts/evaluate_retrieval.py` 会创建临时用户（邮箱用 `example.invalid`）并在结束时清理。真实 `--with-answers` 消耗 API 额度，不要进 CI，也不要覆盖 `docs/evaluation/latest-results.md` 的 2026-07-23 基线。
