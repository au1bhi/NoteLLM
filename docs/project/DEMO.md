# NoteLLM 本地验收

## 1. 配置（不提交密钥）

复制 `.env.example` 为本机 `.env`，填入一个 OpenAI-compatible provider 的后端配置：

```bash
cp .env.example .env
```

必填的模型变量是 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 和 `EMBEDDING_MODEL`。`LLM_BASE_URL` 应是 API 版本根路径，例如 `https://provider.example/v1`。当前 pgvector 迁移使用 1536 维向量，因此 embedding 模型必须返回 1536 维，且 `EMBEDDING_DIMENSIONS` 保持 `1536`。

密钥只存在于 `.env` 和后端容器环境中；浏览器请求不会携带 provider 密钥。

## 2. 启动与迁移

```bash
docker compose up -d db
cd backend
POSTGRES_PORT=5433 uv run alembic upgrade head
POSTGRES_PORT=5433 uv run pytest -q
cd ..
bun run --filter frontend build
```

`db` 使用 `pgvector/pgvector:pg18`。验证扩展：

```bash
docker compose exec db psql -U postgres -d app -c \
  "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
```

## 3. 演示路径

1. 登录并创建笔记本。
2. 上传一份 UTF-8 TXT、Markdown 或 PDF，确认来源显示为 `ready`。
3. 新建 conversation，提出一个可由文档直接回答的问题。
4. 确认答案流式显示，并展示文档名、适用页码和稳定摘录。
5. 刷新页面，确认来源和会话历史仍然存在。
6. 使用另一账户尝试访问该笔记本或 conversation；API 必须返回 `404`。

若 embedding 或 chat provider 未配置，来源或问答会返回安全的配置错误/资料不足信息，不会改由前端调用模型。
