# 为 NoteLLM 做贡献

NoteLLM 是毕业设计原型「基于 FastAPI 与 RAG 的个人学习问答系统」。它从 [Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template) 起步，但产品范围、数据模型和论文材料都已经换成笔记本内 RAG、引用白名单与学习计划。请不要再按上游模板的 Users / Items 示例来改本仓库。

## 先读这些

| 文档 | 内容 |
| --- | --- |
| [`docs/project/GOAL.md`](docs/project/GOAL.md) | MVP、明确不做、验收标准 |
| [`docs/project/PLAN.md`](docs/project/PLAN.md) | 当前阶段与里程碑 |
| [`docs/project/ARCHITECTURE.md`](docs/project/ARCHITECTURE.md) | 一次问答与学习计划数据流 |
| [`development.md`](development.md) | 环境、Compose、prek 与日常命令 |
| [`AGENTS.md`](AGENTS.md) | 硬性约定：中文界面、归属 404、密钥不出浏览器、评测库隔离等 |

大改动（新功能、换检索栈、改安全边界）请先开 Issue 说清楚要解决的论文或产品问题；错别字、类型错误、小范围回归修复可以直接提 PR。

## 本地开发

```bash
make up                # 首次运行会从 .env.example 生成 .env，然后构建并启动整个技术栈

# 后端：mypy、ty、Ruff、pytest、coverage
cd backend && bash scripts/lint.sh && bash scripts/test.sh

# 前端：生产构建 + Biome 检查
bun run --filter frontend build && bun run lint
```

容易踩的坑：

- 后端测试必须连**独立**的 pgvector 实例。不要对 `compose.override.yml` 发布的 `127.0.0.1:5433` 跑 pytest——那是你的开发库，测试套件会清空其中的用户数据。
- 宿主机跑后端用 `bash scripts/run-local-backend.sh`，它会先过 advisory-lock 保护的 Alembic 迁移门禁再启动；不要绕过它直接 `fastapi dev`。
- 改了 OpenAPI 契约后执行 `bash scripts/generate-client.sh` 重新生成前端客户端；**永远不要手改** `frontend/src/client/` 与 `routeTree.gen.ts`。
- 提交钩子使用 [prek](https://prek.j178.dev/)：在 `backend/` 下执行一次 `uv run prek install -f`，之后每次 `git commit` 自动检查并格式化；也可以随时手动 `uv run prek run --all-files`。

## 提交前自检

[`AGENTS.md`](AGENTS.md) 的要求是**严禁未经检验直接提交**。提交或发起 PR 前确认：

- [ ] 后端 `scripts/lint.sh` 与 `scripts/test.sh` 通过；
- [ ] 前端构建与 `bun run lint` 通过；
- [ ] 在真实运行环境里点过一遍改动涉及的功能，不只是单测变绿；
- [ ] 行为变化有对应测试；安全相关改动对照 `docs/project/THREAT_MODEL.md` 与 `docs/evaluation/security-experiments.md`；
- [ ] 部署相关改动遵循 AGENTS.md：前端产物只在本地/CI 构建，严禁在轻量服务器（VPS）上编译。

CI 会在 push 到 `master` 和所有 PR 上运行 `test-backend`（pytest + coverage，门槛 80%）与 `test-docker-compose`。仓库没有 Playwright/e2e 流水线，也没有对应的 compose 服务——不要在改动中引用它们。

## Pull Request 规范

1. 一个 PR 只做一件事。
2. 不要提交 `.env`、用户上传文件、真实反代域名或供应商密钥。测试与示例只用 RFC 2606 保留域（`example.com`、`example.invalid`）。
3. 不要把 `img/` 里的上游模板截图当成 NoteLLM 界面引用。论文插图在本机捕获，清单见 [`docs/thesis/SCREENSHOTS.md`](docs/thesis/SCREENSHOTS.md)。
4. 不要覆盖 `docs/evaluation/latest-results.md` 里 2026-07-23 的基线快照；新评测结果写入 `docs/evaluation/runs/`。
5. PR 描述说明 schema 或 prompt 变化、关联 Issue、附带测试；界面改动贴截图。

Commit message 用简短祈使句加 emoji 前缀，与现有历史保持一致：

```text
✨ feat(chat): support multi-turn conversation context
🐛 fix(answers): bypass citation validation for contextualized recall
🛡️ fix(ci): add study plan IDOR security tests
📝 docs: update PLAN.md with milestones and test results
```

## 论文材料

可粘贴大纲与实验草稿在 [`docs/thesis/`](docs/thesis/)。写正文时对着本仓库的服务与测试，不要复述泛化的「RAG 提高准确率」。合成评测集上的 Recall@5 = 100% 是该语料的天花板，不是检索科学研究结论。
