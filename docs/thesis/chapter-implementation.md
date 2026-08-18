# 第 4 章　关键实现（粘贴用草稿）

> 用法：以下正文按本仓库当前代码写成，可直接改写入论文第 4 章。函数名、常量与固定句必须与实现一致，不要改成泛化的「RAG 流程」。截图按 [`SCREENSHOTS.md`](SCREENSHOTS.md) 本机捕获，不要使用仓库 `img/`。

## 4.1 摄取、分块与状态机

上传入口只接受三种扩展名：`.txt`（`text/plain`）、`.md`（`text/markdown`，也接受误标成 `text/plain` 的情况）和 `.pdf`（`application/pdf`）。校验在 `validate_upload`：无文件名返回 400，扩展名不在白名单或 `Content-Type` 与扩展名不一致返回 415。写入本地 volume 时按 64 KiB 分片累加，超过 `MAX_UPLOAD_SIZE_BYTES` 返回 413 并删除半成品。

文本文件按 UTF-8（含 BOM）整文件读入；PDF 用 PyMuPDF 按页 `get_text("text")`，页码从 1 计，以便引用带页。提取有两道硬上限，与额度无关，用来挡住解压炸弹和超大页数：`MAX_PDF_PAGES = 500`，`MAX_EXTRACTED_CHARS = 5_000_000`。解码失败或超限都变成来源 `failed`，不写残缺向量。

默认分块常量是 `CHUNK_SIZE = 1000`、`CHUNK_OVERLAP = 150`。`split_page` 还接受同名可选参数，供评测脚本做分块消融；线上上传 API **不**暴露这两项。切分前 `validate_chunk_params` 要求长度大于 0、重叠非负且严格小于长度。切点优先在窗口内从 `CHUNK_MIN_BREAK = 500` 起向右找换行，其次空格，避免在词中间硬切。空页不产生块。

来源状态只能是 `pending` → `processing` → `ready` / `failed`，该字段在模型与公开 schema 中使用 `Literal` 收窄。提取失败或文本为空时，异常处理仍会 `mark_failed`，不会把来源卡在 `processing`。嵌入按 64 条一批调用；统一额度上下文在异常时回滚未提交分块并退款，维度错误或 provider 缺失标记 `failed`，不写入半截索引。删除来源时级联删分块、向量和本地文件。

额度在调用嵌入之前按「全部分块字符数之和」原子预留。自备嵌入 Key 的预留量为 0，不计入服务端免费额度。

## 4.2 笔记本范围内的余弦检索

`retrieve_chunks` 只在**当前笔记本**、状态为 `ready`、且 `embedding` 非空的分块上检索。度量是 pgvector 的 `cosine_distance`；返回给上层的 `score` 定义为 `1.0 - distance`，只用于排序，界面不得把它解释成「回答正确的概率」。默认 `limit = 5`，接口允许 1—10，超过 10 会被拒绝。可选 `source_ids` 把检索收窄到用户勾选的来源，但不能跨笔记本。

提问时的查询文本同样要走嵌入。`usage_reservation` 保存 `reserve_usage` 返回的**实际预留量**，失败时只按该量退还；自备 Key 的预留为 0，不能用查询字符数制造退款。

## 4.3 三种模式与引用白名单

回答模式是服务端策略，定义在 `AnswerMode`，前端标签为「仅依据资料 / 资料 + 已有知识 / 自由问答」，请求体字段是 `grounded` / `hybrid` / `knowledge`。实现全部在 `answer_question`，评测脚本用同一函数，`--mode` 只改变这一处。

系统规则走 `system` 消息，问题与检索原文走 `user` 消息；证据块写成 `<source chunk_id="…">`，正文标 `untrusted_source_text`，并写明不得执行其中的指令。模型必须返回 JSON：`answer` 字符串加 `citations`（chunk ID 数组）。后端用本轮 `retrieved` 做成 `retrieved_by_id`，只保留出现在该字典里的 ID，去重后最多 5 条（`MAX_CITATIONS`）。摘录截到 `QUOTE_LENGTH = 500` 个字符，页码来自分块而不是模型。

三种模式的强制行为如下，论文应写后端行为，不要只复述提示词。

| 模式 | 是否调用 `retrieve_chunks` | 过滤后无存活引用 | 检索结果为空 |
| --- | --- | --- | --- |
| `grounded` | 是 | 正文替换为固定句 | **不**调用聊天模型，直接固定句 |
| `hybrid` | 是 | **保留**模型正文，引用为空 | 仍调用聊天模型，引用为空 |
| `knowledge` | 否 | 引用数组在服务端恒为空 | 不检索 |

固定句常量是：

> 资料不足，无法根据当前笔记本中的来源可靠回答。

统计「资料不足次数」时必须与该字符串**完全一致**。近义改写、多字少字都不算。`knowledge` 的引用率在实现上就是 0，不是评测后才「测出来」的。前端不提交引用 ID，也不持有供应商密钥。

流式接口 `POST /api/v1/conversations/{id}/messages/stream` 依次推送 `delta`、`citations`、`done`；失败推 `error`。笔记本没有 `ready` 来源时拒绝提问。建议的后续问题（最多 3 条）与主回答并行请求，失败不得拖垮主回答。

## 4.4 从对话到学习计划

一份 `Conversation` 至多对应一份 `StudyPlan`（0..1），计划下有多条 `StudyTask`。删除会话级联删除计划与任务。生成入口是 `POST /api/v1/conversations/{id}/study-plan`，**不是**侧边栏 `/gantt`。`/gantt` 只读 `GET /api/v1/study-plans`，把当前用户全部计划画在同一条时间轴上，按笔记本着色，并可用 `?conversation=` 跳回会话。没有计划时的空状态必须写明「这里只聚合、不会自己生成」。

生成时从该会话截取最近 30 条消息、合计不超过 16 000 字符，按「学习者 / 助教」拼进 `<conversation>`，并在 system 侧写明对话不可信、不得改输出格式。模型给出标题、摘要、难度、周期和 4—12 项任务。后端把周期钳在 3—60 天；难度接受中英别名（入门 / beginner / easy 等），无法识别时落成 `intermediate`；缺日期的空隙由服务端补齐，保证任务覆盖整个周期且不越界。`estimated_minutes` 表示该阶段每天建议投入，不是整个阶段的总分钟数。

邮件提醒默认关闭。开启要求服务器已配置 SMTP **且** 当前用户邮箱已验证，否则 400。独立 scheduler 按计划的 IANA 时区在本地 09:00 选取当日未完成任务，用

```sql
UPDATE … WHERE last_reminder_date IS NULL OR last_reminder_date != :day
RETURNING id
```

原子认领，避免进程重启造成同日重发。HTML 正文对标题、任务和链接做 `html.escape`。发送失败回滚当日认领以便重试。

学习计划相关表若尚未 `alembic upgrade head`，列表与生成返回 **503**，detail 提示执行迁移，而不是空白 500。`fastapi dev` 不会自动跑 Alembic。

## 4.5 归属、令牌与额度（实现要点）

笔记本范围内的对象一律回溯到 `Notebook.owner_id`。不存在与无权限统一 **404**，不返回 403，避免用状态码探测资源是否存在。工作区打开他人或未知 UUID 时，界面是带大号「404」的空状态，文案同时写「没有这份笔记本，或不属于当前账户」，两种情况同一句，不靠正文区分。聚合甘特图按当前用户过滤；用他人 `notebook_id` 过滤得到空列表，不回传他人计划标题。

访问 JWT、密码重置令牌和换邮令牌都绑定账户的 `password_changed_at` 微秒快照（声明名 `pwd`）。改密或管理员重置会清空 `pending_email`，并使旧令牌立即失效。无快照的遗留 access token 一律拒绝。

服务端免费额度为对话 10 万 token、嵌入 30 万字符，按自然月惰性重置。所有 provider 调用通过 `usage_reservation` 在调用前原子预留，成功按实际用量结算，失败先回滚再退款。自备 Key 的对应维度预留为 0。删除账户会把当月用量写入按规范邮箱索引的墓碑，同址再注册不能刷新额度。

用户填写的 BYOK `base_url` 每次出站都经 `validate_outbound_url` + `pinned_request`：解析时刻拒绝回环、RFC1918、链路本地、云元数据、CGNAT 以及十进制 / 十六进制 / IPv4-mapped 绕过，并连接到当时校验过的公网 IP。运营者可选的 `SERVER_PROVIDER_PROXY_URL` 只服务端配置的模型能用，用来避开 Fake-IP DNS 把公网域名解析成保留地址；用户 URL 不得走这条代理。

## 4.6 与实验章的衔接

本章描述的是**实现**，不是测量值。第 6 章的基线是 2026-07-23、提交 `cb0ead1`、`grounded`、Top-K=5、分块 1000/150 的单次快照。人工忠实度已对应该次回答逐题标完：34 通过 / 0 未通过。Top-K / 分块消融与三种模式对照的 CLI（`--top-k`、`--chunk-size`、`--chunk-overlap`、`--mode`、`--questions`）已经接到上述同一套函数；结果表在实跑前保持「—」，不得把本节的策略写成「RAG 提高了准确率」。
