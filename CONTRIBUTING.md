# 为 NoteLLM 做贡献

NoteLLM 是毕业设计原型「基于 FastAPI 与 RAG 的个人学习问答系统」。它从 [Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template) 起步，但产品范围、数据模型和论文材料都已经换成笔记本内 RAG、引用白名单与学习计划。请不要再按上游模板的 Users / Items 示例来改本仓库。

## 先读这些

- [`docs/project/GOAL.md`](docs/project/GOAL.md)：MVP、明确不做、验收标准
- [`docs/project/PLAN.md`](docs/project/PLAN.md)：当前阶段
- [`docs/project/ARCHITECTURE.md`](docs/project/ARCHITECTURE.md)：一次问答与学习计划数据流
- [`AGENTS.md`](AGENTS.md)：中文界面、归属 404、密钥不出浏览器、评测库隔离

大改动（新功能、换检索栈、改安全边界）请先开 Issue 说清楚要解决的论文或产品问题。错别字、类型错误、小范围回归修复可以直接提 PR。

## 本地开发

环境、Compose、lint 与测试见 [`development.md`](development.md)。后端测试必须连**独立**的 pgvector 实例，不要对 `compose.override.yml` 映射的 `5433` 跑 pytest：那是开发库，套件会删用户数据。

```bash
docker compose watch

cd backend
bash scripts/lint.sh
bash scripts/test.sh

cd ..
bun run --filter frontend build
bun run lint
```

改了 OpenAPI 契约后，重新生成前端客户端，不要手改 `frontend/src/client`。

## Pull Request

1. 行为变化要有测试；安全相关改动对照 `docs/project/THREAT_MODEL.md` 和 `docs/evaluation/security-experiments.md`。
2. 一个 PR 只做一件事。
3. 不要提交 `.env`、用户上传、真实反代域名或供应商密钥。测试与示例只用 RFC 2606 保留域（`example.com`、`example.invalid`）。
4. 不要把 `img/` 里的上游模板截图写成 NoteLLM 界面。论文插图在本机捕获，清单见 [`docs/thesis/SCREENSHOTS.md`](docs/thesis/SCREENSHOTS.md)。
5. 不要覆盖 `docs/evaluation/latest-results.md` 里 2026-07-23 的基线快照。新跑写入 `docs/evaluation/runs/`。

## 论文材料

可粘贴大纲与实验草稿在 [`docs/thesis/`](docs/thesis/)。写正文时对着本仓库的服务与测试，不要复述泛化的「RAG 提高准确率」。合成评测集上的 Recall@5 = 100% 是该语料的天花板，不是检索科学研究结论。
