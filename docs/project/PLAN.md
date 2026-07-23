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
- 已建立 34 个问题的固定合成评测集；`backend/scripts/evaluate_retrieval.py` 在独立临时数据上计算 Recall@5、自动引用来源匹配、关键词忠实度筛查和耗时，并在结束时清理临时用户、向量和文件。完整方法见 `docs/evaluation/README.md`，首份结果见 `docs/evaluation/latest-results.md`。
- 补充 Docker 演示数据、架构图、实验结果的人工忠实度复核和答辩脚本。

完成条件：可复现演示和论文所需证据齐全。

## 当前下一步

补充 Docker 演示数据、架构图、实验结果的人工忠实度复核和答辩脚本。默认不要加入阶段目标外的依赖或服务；如确有必要，先记录原因与替代方案。

阶段 4 当前验收证据：2026-07-23 使用 7 份合成 Markdown 资料、34 个固定问题、智谱 Embedding-3（1024 维）与 DeepSeek V4 Flash 运行评测；Recall@5 为 100.0%，自动引用来源匹配率为 100.0%，关键词忠实度筛查为 97.1%，检索平均/P95 为 320/986 ms，回答平均/P95 为 3227/6701 ms。该结果不替代逐题人工忠实度审核。
