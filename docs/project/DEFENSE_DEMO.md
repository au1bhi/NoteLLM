# 答辩演示脚本（约 6 分钟）

## 演示前检查

```bash
docker compose up -d db
cd backend
POSTGRES_PORT=5433 uv run alembic upgrade head
POSTGRES_PORT=5433 uv run pytest -q
cd ..
bun run --filter frontend build
```

本地启动后访问 `http://localhost:5173`；API 文档位于 `http://localhost:8000/docs`。使用本机已有测试账户或在页面注册新账户。不要在演示屏幕、终端历史或截图中显示 `.env` 内容和 provider 密钥。

## 讲解与操作

1. **目标（30 秒）**：说明这是面向个人学习的、带可追溯引用的文档问答闭环，而不是通用聊天机器人。
2. **资料摄取（90 秒）**：创建“答辩演示”笔记本，上传一份 UTF-8 TXT、Markdown 或 PDF；展示来源从处理状态变为 `ready`。说明 PDF 可保留页码，TXT/Markdown 显示来源摘录。
3. **受控问答（90 秒）**：新建会话，提出一个资料中有明确答案的问题。展示答案流式出现、来源名、页码（适用时）和稳定摘录。强调模型只能引用本轮检索到的 chunk ID，未知 ID 会被后端过滤。
4. **持久化与隔离（60 秒）**：刷新页面，展示会话和引用仍存在。若准备了第二账户，可在 API 文档中访问第一账户的 notebook ID，展示 404。
5. **资料不足（30 秒）**：提出资料中没有覆盖的问题，展示固定的“资料不足”回答，说明系统不应编造证据。
6. **评测（60 秒）**：打开 `docs/evaluation/latest-results.md`。说明 34 个固定问题、7 份合成资料、Recall@5、自动引用来源匹配、关键词筛查及延迟均可重跑；明确关键词筛查不替代人工忠实度审核。

## 可现场运行的评测命令

```bash
cd backend
POSTGRES_PORT=5433 uv run python scripts/evaluate_retrieval.py \
  --with-answers \
  --report ../docs/evaluation/latest-results.md
```

脚本只上传仓库中的合成 Markdown，并在结束时删除临时用户、来源、向量与文件。网络或 provider 限流会影响延迟，因此答辩时可使用已提交报告展示基线结果，并说明运行环境。

## 常见问题的简短回答

- **为什么是 pgvector？** 项目规模适合 PostgreSQL 内的向量检索，减少额外服务，且可用余弦距离完成 Top-K 检索。
- **如何防止幻觉？** 只向模型提供本轮检索证据、限制可引用 ID、后端校验引用；无有效证据即固定回复资料不足。
- **如何评估？** 固定合成语料和问题可重跑 Recall@5、引用来源匹配和耗时；回答忠实度仍需人工逐题复核。
- **下一步是什么？** 在不改变 MVP 边界的前提下补齐人工审计表和 Docker 端到端演示数据，再根据评测结果单独调优分块或 Top-K。
