# 基于FastAPI与RAG的个人学习问答系统设计与实现

本文档是毕业设计论文的粘贴用大纲。创新点按**工程闭环完整性**表述：在个人学习场景中做成「受控检索问答 + 可复现评测 + 用户隔离」的可演示原型，而不是声称检索或生成达到 SOTA。研究定位与「明确不做」以 `docs/project/GOAL.md` 为准。中英文摘要见 [`abstract.md`](abstract.md)。

## 第 1 章　绪论

### 1.1 研究背景

大语言模型便于答疑，但在个人学习中常出现三处缺口：回答偏离手头教材、缺少可核对出处、无法把一次问答转成可执行的后续安排。个人资料问答因此需要「先检索当前笔记本证据、再受控生成、再由服务端校验引用」的闭环，而不是开放域聊天。

### 1.2 研究定位

NoteLLM 是面向个人学习与研究的毕业设计原型：用户把 PDF / TXT / Markdown 放入笔记本，在限定资料范围内提问，获得带来源、页码（适用时）和原文摘录的回答，并可将对话转化为 3—60 天学习甘特图。目标是证明完整、可信且可评估的 RAG 工作流，而不是复刻工业级知识库产品。

核心研究问题（工程问题，非榜单问题）：

- 在笔记本范围内做余弦检索，能否让回答可核验、可回溯。
- 服务端引用白名单能否抑制伪造出处。
- 对话内容能否稳定映射为难度、周期、阶段任务与验收方式。
- 多用户共用同一套模型服务时，如何兼顾归属隔离、额度预留与出站安全。

### 1.3 明确不做

对齐 `GOAL.md`，本文不覆盖：

- 多人实时协作、企业级权限、音频概览、移动端 App。
- 网页爬取、OCR、复杂表格 / 图片理解与全格式文档支持。
- 微服务、消息队列、多模型容灾、超大规模并发和生产级运维。
- 开放域检索 SOTA、语义蕴含（NLI）式忠实度判定、跨语料泛化结论。

### 1.4 论文结构

第 1 章按 [`chapter-intro.md`](chapter-intro.md) 写定位与四个工程问题；第 2 章按 [`chapter-related.md`](chapter-related.md) 只列实际用到的技术；第 3 章给出系统与数据模型；第 4 章按 [`chapter-implementation.md`](chapter-implementation.md) 写摄取、检索、白名单与学习计划；第 5 章按 [`chapter-security.md`](chapter-security.md) 写边界；第 6 章按 [`chapter-experiment.md`](chapter-experiment.md) 报告基线与人工复核；第 7 章写部署与复现；第 8 章按 [`chapter-conclusion.md`](chapter-conclusion.md) 收束。

## 第 2 章　相关技术

正文按 [`chapter-related.md`](chapter-related.md) 粘贴。本章保持短篇幅，只写本系统实际用到的技术，不展开综述清单。

| 技术 | 在本系统中的角色 |
| --- | --- |
| FastAPI + SQLModel | 认证、摄取、检索、SSE 问答、学习计划与归属校验的单体后端 |
| PostgreSQL + pgvector | 业务数据与 1024 维向量同库；检索用 cosine distance 取当前笔记本 Top-K |
| Server-Sent Events | `POST .../messages/stream` 依次推送答案增量、引用与完成事件 |
| Docker Compose | 本地与生产同一套服务编排；低内存机可用预构建前端；`install.sh` 一键安装 |

嵌入与聊天均走 OpenAI 兼容接口，密钥只存在后端。前端为 React / Vite，不直接调用模型供应商。

## 第 3 章　系统设计

正文按 [`chapter-design.md`](chapter-design.md) 粘贴。下面只保留必须与实现一致的骨架。

### 3.1 总体架构

完整 mermaid 图见 `docs/project/ARCHITECTURE.md`，论文插图转绘该图即可。浏览器经 HTTPS API 与 SSE 访问 FastAPI；后端拆为认证与用户隔离、笔记本与会话、上传提取分块、检索与受控问答、对话学习计划；独立 scheduler 按用户时区在每天 09:00 投递已订阅提醒。向量与业务数据同在 PostgreSQL + pgvector；上传文件落在本地 Docker Volume。

### 3.2 一次问答数据流

1. 令牌鉴权后按 `Notebook.owner_id` 校验归属。
2. TXT / Markdown / PDF 写入本地 volume，按 1,000 字符、150 字符重叠分块。
3. 嵌入写入 1024 维向量；仅 `ready` 来源的非空向量可检索。
4. 提问时在当前笔记本内按 pgvector cosine distance 取 Top-5，把原文作为不可信证据构造提示词。
5. 聊天模型返回 JSON 答案与候选 chunk ID；后端只保留本轮检索集合中的引用，写入 `Message` 与 `Citation`，再经 SSE 下发。

### 3.3 数据模型

ER 关系见 `docs/project/DESIGN.md`：

```text
User 1 ── * Notebook 1 ── * Source 1 ── * Chunk
                    │
                    └── * Conversation 1 ── * Message 1 ── * Citation ── 1 Chunk
                                      │
                                      └── 0..1 StudyPlan 1 ── * StudyTask
```

所有标识为 UUID；删除父实体级联清理子实体与派生数据。笔记本范围内的对象一律回溯到 `Notebook.owner_id`，不信任客户端传入的 ID。

### 3.4 主要接口

接口契约见 `docs/project/API_AND_UX.md`。除登录注册外均需 Bearer 认证；调用方不拥有的资源统一返回 **404**（不返回 403，避免存在性探测）。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` / `POST` | `/api/v1/notebooks/` | 列出或创建当前用户笔记本 |
| `GET` / `PUT` / `DELETE` | `/api/v1/notebooks/{notebook_id}` | 读写删一本笔记本 |
| `GET` / `POST` | `/api/v1/notebooks/{notebook_id}/sources/` | 列出或上传来源 |
| `POST` | `/api/v1/conversations/{conversation_id}/messages/stream` | SSE 流式问答 |
| `GET` / `POST` | `/api/v1/conversations/{conversation_id}/study-plan` | 读取或生成会话学习计划 |
| `GET` | `/api/v1/study-plans` | 聚合当前用户全部计划（甘特图） |

流式接口依次发出 `delta`、`citations`、`done`；失败发 `error`。笔记本没有 `ready` 来源时拒绝提问。

## 第 4 章　关键实现

正文按 [`chapter-implementation.md`](chapter-implementation.md) 粘贴，不要另写一套泛化 RAG 流程。下面只列必须出现的实现事实。

### 4.1 摄取与分块

只接受 UTF-8 TXT、Markdown 和 PDF；PDF 用 PyMuPDF 按页提取以便引用带页码。默认分块 **1,000** 字符、重叠 **150** 字符；`split_page` / `process_source` 接受同名可选参数供评测消融，上传 API 不暴露这两项。来源状态为 `pending` → `processing` → `ready` / `failed`。提取失败必须能 `mark_failed`，不能把来源卡在 `processing`。嵌入维度错误或 provider 缺失时标记 `failed`，不写入残缺索引。删除来源时级联清理分块、向量与本地文件。

### 4.2 Top-5 余弦检索

提问只在当前笔记本的 `ready` 来源中检索。度量是 pgvector cosine distance，默认 Top-K = 5（接口 `limit` 范围 1—10）。相似度只用于排序，UI 不得把它解释成「回答正确的概率」。

### 4.3 引用白名单

模型只能返回本轮检索到的 chunk ID。后端按检索集合做白名单过滤，丢弃未知 ID；`grounded` 模式下过滤后若无有效引用，正文替换为固定句「资料不足，无法根据当前笔记本中的来源可靠回答。」前端不提交引用 ID，也不持有供应商密钥。时序图建议画：提问 → 检索 Top-5 → 构造 system / user 分角色提示词 → 模型 JSON → 白名单过滤 → 持久化 → SSE。

### 4.4 三种回答模式（策略，不是已测结论）

实现见 `backend/app/services/answers.py` 的 `AnswerMode`。三种模式是**服务端策略**，对照表在实验章留空，未跑完不得声称「RAG 提高了准确率」。

| 模式 | 是否检索 | 无存活引用时 | 无检索结果时 |
| --- | --- | --- | --- |
| `grounded` | 是 | 正文替换为「资料不足」 | 不调用聊天模型，直接「资料不足」 |
| `hybrid` | 是 | **保留**模型正文，引用为空 | 仍调用聊天模型，引用为空 |
| `knowledge` | 否 | 引用数组恒为空 | 不检索，只凭模型知识作答 |

### 4.5 学习计划（3—60 天）

从会话截取近期对话作为不可信输入，模型给出难度、周期与阶段任务；后端校验周期落在 3—60 天、补齐未覆盖日期，落为 `StudyPlan` + `StudyTask`。邮件提醒默认关闭，仅已验证邮箱可主动开启；独立 scheduler 按计划 IANA 时区每天 09:00 投递当日未完成任务，并以数据库原子认领防止同日重发。侧边栏甘特图通过 `GET /api/v1/study-plans` 聚合当前用户全部会话计划。截图由作者本机捕获后插入。

## 第 5 章　安全

正文按 [`chapter-security.md`](chapter-security.md) 粘贴。STRIDE 全表与 pytest 对照已经在本仓库：

- `docs/project/THREAT_MODEL.md`（威胁模型附录）
- `docs/evaluation/security-experiments.md`（已有 pytest 对照表，不是渗透测试报告）

四点必须写进正文：

1. **归属 404**：笔记本 / 会话 / 学习计划均按 `Notebook.owner_id` 解析；不存在与无权限统一 404。
2. **SSRF 固定出口**：用户 BYOK `base_url` 解析 DNS 后拦截回环 / 私网 / 链路本地 / 云元数据 / 十进制与 IPv4-mapped 绕过，并 pin 到当时校验过的公网 IP；运营者代理不得用于用户 URL。
3. **额度预留—结算**：模型调用前原子 `reserve_usage`，返回后按实际用量 `settle_usage`；自备 Key 的维度不计入服务端免费额度。
4. **提示词隔离**：系统规则走 `system` 消息，资料与问题走 `user` 消息并标明不可信；引用 ID 只保留本轮检索集合。

残余风险（须承认）：模型仍可能在正文中服从注入内容；`hybrid` / `knowledge` 允许无引用作答；任意公网主机都可作为 BYOK 目标。

## 第 6 章　实验

粘贴用草稿见同目录 [`chapter-experiment.md`](chapter-experiment.md)。基线数字引用 2026-07-23、提交 `cb0ead1` 的 `docs/evaluation/latest-results.md`，**不要改写成更新跑数**，除非另有新报告。

| 指标 | 数值 |
| --- | ---: |
| Recall@5 | 100.0% |
| 自动引用来源匹配 | 97.1% |
| 关键词忠实度筛查 | 88.2% |
| 检索 P95 | 894 ms |
| 回答 P95 | 5595 ms |

人工忠实度已对应该次基线回答逐题标完：**34 通过 / 0 未通过**，说明见 `docs/evaluation/human-faithfulness.md`。Top-K / 分块消融表、三种回答模式对照表的协议与 CLI 已接通，数字格在本机实跑前保持「—」，不得把协议里的先验写成测量值。100% 召回是本合成自描述语料上的天花板，不是检索科学研究结论。截图清单见 [`SCREENSHOTS.md`](SCREENSHOTS.md)，不要使用仓库 `img/`。

## 第 7 章　实现与部署

正文按 [`chapter-deploy.md`](chapter-deploy.md) 粘贴。

- 后端 Python ≥ 3.12，Alembic 管理 schema；前端 React / Vite，OpenAPI 生成客户端。
- 本地：`docker compose` 拉起 `pgvector/pgvector:pg18`（主机 5433），`backend` 目录执行 `alembic upgrade head`。
- 一键安装：仓库根目录 `install.sh`（`--local` / `--prod` / `--low-mem` / `--dry-run`）。生产侧 Traefik + TLS；低内存机下载 Release 中的预构建 `frontend-dist`。
- 检查：后端 pytest、Ruff、mypy、ty；前端 lint 与生产构建。单元测试使用假 provider，不在 CI 消耗外部模型额度。
- 真实评测只对合成语料、在隔离库上跑，结束后清理临时用户与文件。

## 第 8 章　总结与展望

正文按 [`chapter-conclusion.md`](chapter-conclusion.md) 粘贴。总结应回到工程闭环：笔记本内 RAG、引用白名单、可复现评测、用户隔离与学习计划，而不是「提出了更优的检索算法」。展望须落在 MVP 边界内，例如：在隔离库上补齐消融 / 模式对照的实跑数字；在不引入独立向量库的前提下按评测单变量调节分块或 Top-K；加强答案语义核验（仍不宣称 NLI SOTA）。不把多人协作、OCR、微服务列为「下一步必做」。

## 插图与表格清单

| 编号建议 | 内容 | 来源 |
| --- | --- | --- |
| 图 3-1 | 系统架构 mermaid | `ARCHITECTURE.md` |
| 图 3-2 | 实体关系 | `DESIGN.md` |
| 图 4-1 | 问答 + 引用白名单时序 | 第 4.3 节文字流程 |
| 图 4-2 | 流式回答与引用摘录 | 作者本机截图，见 `SCREENSHOTS.md` |
| 图 4-6 | 聚合甘特图 | 作者本机截图；空状态须能说明生成入口 |
| 表 6-1 | 基线自动指标 | `latest-results.md`（2026-07-23，`cb0ead1`） |
| 表 6-2 | 自动指标与人工结论不一致的四题 | Q04 / Q09 / Q32 / Q34，均已标通过 |
| 表 6-3 | Top-K / 分块消融 | 待本机实跑，见 `docs/evaluation/ablation-template.md` |
| 表 6-4 | 三种回答模式对照 | 待本机实跑，见 `docs/evaluation/answer-mode-protocol.md` |
| 表 5-1 | STRIDE 资产与残余风险 | `THREAT_MODEL.md`，正文见 `chapter-security.md` |
| 表 6-5 | 人工忠实度复核 | `latest-results.md`：**34 通过 / 0 未通过** |
| 参考文献 | RAG / DPR / JWT / STRIDE / 本仓库依赖 | `references.bib`，缺的条目读过再补 |
