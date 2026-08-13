# Release Notes

NoteLLM 自己的变更记录。仓库最初由 Full Stack FastAPI Template 生成，上游模板的 PR 列表不属于本项目，已从本文件移除，避免被误当成产品说明或论文材料。

## Latest Changes

合并进 `master` 的 Pull Request 会由 `.github/workflows/latest-changes.yml` 追加到本节。

## 2026-08 毕业设计闭环

- 笔记本内 RAG：上传 TXT / Markdown / PDF，按 1,000 字符、150 字符重叠分块，pgvector cosine Top-K（默认 5，上限 10）。
- 三种回答模式：`grounded` / `hybrid` / `knowledge`；`grounded` 在无有效引用时替换为固定句「资料不足，无法根据当前笔记本中的来源可靠回答。」
- 服务端引用白名单：只保留本轮检索集合内的 chunk ID。
- 对话学习计划：3—60 天甘特图；`GET /api/v1/study-plans` 按用户聚合；删除会话级联清理计划。
- 安全：归属统一 404、BYOK SSRF 固定公网 IP、额度原子预留—结算、改密撤销 access / 重置 / 换邮令牌。
- 评测：34 题合成集 + 6 题语料外负例；人工忠实度 34 / 34 通过；Top-K、分块与模式对照的 CLI 已接通，结果表待本机实跑。
