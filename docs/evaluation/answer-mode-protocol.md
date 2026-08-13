# 三种回答模式对照协议

本协议只规定论文实验章如何对照 `grounded` / `hybrid` / `knowledge` 三种回答模式，**不在此仓库里跑现场评测**。语料与问题均为合成内容，不含用户上传资料、账号、密钥或个人信息。表中数字格在真实跑完前保持 `—`，不要把假设写成已测结果。

三种模式的语义以 `backend/app/services/answers.py` 的 `answer_question` 为准，定义见下节。`--mode {grounded,hybrid,knowledge}` 与 `--questions` 已经接到 `evaluate_retrieval.py`。

## 模式语义（对照 `answers.py`）

常量 `INSUFFICIENT_EVIDENCE_ANSWER` 的精确字符串为：

> 资料不足，无法根据当前笔记本中的来源可靠回答。

下文「资料不足」均指与该字符串**完全一致**的回答，不是近义改写。

服务端在三种模式下都会丢弃不在本次检索候选集中的 citation ID（`knowledge` 根本不检索，因此永远不会留下引用）。引用上限为 5。

| 模式 | 是否检索 Top-K | 模型引用过滤 | 无存活引用时 | 无检索结果时 |
| --- | --- | --- | --- | --- |
| `grounded` | 是 | 丢弃不在候选集中的 ID | 用「资料不足」**替换**模型正文 | 不调用聊天模型，直接「资料不足」 |
| `hybrid` | 是 | 丢弃不在候选集中的 ID | **保留**模型正文，引用为空 | 仍调用聊天模型，保留正文，引用为空 |
| `knowledge` | 否 | 不适用 | 引用数组在服务端恒为空 | 不检索；只凭模型自身知识作答 |

要点：

- **grounded**：检索后只允许引用本次候选；过滤后若一条有效引用都不剩，答案被替换为「资料不足」。这是强制弃权，不是模型“自己决定少说”。
- **hybrid**：检索结果作为主要依据，但允许用模型自身知识补全。无检索结果、或过滤后引用为空时，**仍保留模型正文**，citations 为空。
- **knowledge**：不调用 `retrieve_chunks`；即使用户或模型返回了 chunk ID，服务端也固定 `citations=[]`。因此该模式的引用率在实现上就是 0，不是评测后才“测出来”的。

系统提示词还要求：`grounded` 证据不足时必须返回上述精确句子；`hybrid` 证据不足时仍用通用知识作答并留空引用；`knowledge` 的 citations 必须为空。论文描述应以后端强制行为为准，不要只复述提示词。

## 对照设计

同一批问题、同一套检索与分块参数，**只改 `--mode`**。

固定条件：

- 问题文件：`docs/evaluation/questions.csv`（**34** 题，语料内 / in-corpus）
- Top-K：`k=5`（`DEFAULT_RETRIEVAL_LIMIT`）
- 分块：`1000` 字符，重叠 `150` 字符
- 同一 git commit、同一嵌入模型与维度、同一聊天模型、同一隔离数据库镜像、同一运行日

禁止在本对照中同时改 k、分块、嵌入模型或问题文件。那些因子属于 `ablation-protocol.md`，不要和模式对照混在一轮里。

### 可选第二块：语料外（OOC）弃权率

语料外负例已落在 `docs/evaluation/questions-ooc.csv`（6 题，`expected_source=none`）。用**同一** `k=5`、分块 `1000/150` 和三种 `--mode` 再跑一轮，专门看弃权行为：

- `grounded` 在 OOC 上应倾向输出精确的「资料不足」；
- `hybrid` 在 OOC 上可能仍作答且引用为空；
- `knowledge` 不检索，引用仍为空，谈不上“据笔记本弃权”。

OOC 未落地时，只填语料内 34 题那张表，不要编造 OOC 数字。

## 每轮必须记录

写在该轮报告开头（建议路径 `docs/evaluation/runs/mode-<mode>.md`）：

- git commit（短哈希）
- 回答模式（`grounded` / `hybrid` / `knowledge`）
- 嵌入模型与向量维度
- 聊天模型
- Top-K（本协议固定 5）
- 分块长度 / 重叠（本协议固定 `1000/150`）
- 问题文件与题数
- 运行日期
- 数据库镜像（镜像名与标签）

不要把真实供应商端点、API 密钥或用户资料写进报告。需要占位 URL 时只用 RFC 2606 保留域（`*.example.com`、`*.example.invalid`）。

## 指标（按模式各算一次）

| 指标 | 定义 |
| --- | --- |
| 引用率 | 带 **至少 1 条已验证引用** 的回答数 / 全部回答数。已验证 = 过滤后仍留在本次检索候选集中的 citation；`knowledge` 按实现应为 0。 |
| 关键词命中率 | 自动化忠实度筛查：回答是否包含该题 `expected_answer_terms`。**不等于**人工审核已通过。 |
| 资料不足次数 | 回答正文与 `INSUFFICIENT_EVIDENCE_ANSWER` **完全一致** 的题数。近义句、多字少字都不计。 |
| 人工忠实度 | 逐题阅读答案、已验证引用摘录与期望事实后标注（通过 / 未通过 / 不适用）。「资料不足」题应单独记是否为合理弃权，不要当成“答错”。 |

引用率与现有报告里的「引用正确率（自动）」不同：后者看已验证引用是否来自**标注期望来源**；本对照先报“有没有经后端验证的引用”，再在人工表里看是否忠于来源。两套数字都要抄，不要互相替代。

关键词命中在「资料不足」题上通常为否（该句不含各题关键词），这是弃权信号，不要据此宣称 grounded“更不准”。

## 事先假设（不是测量值）

下列是实现与题型导出的**先验**，抄进论文前必须换成实跑表中的数字。

- `knowledge` 引用率 = 0（服务端不检索、不保留引用）。
- `grounded` 在语料内 34 题上：引用率应偏高；一旦过滤后无存活引用，正文会被换成「资料不足」。
- `grounded` 在 OOC 上：应倾向弃权（资料不足次数升高）。
- `hybrid` 在 OOC 上：可能仍给出无引用的模型正文，资料不足次数低于 grounded。
- **在对照表填实之前，不得声称 RAG「提高了准确率」。** 关键词命中、人工忠实度、弃权率可能朝不同方向变化；没有填好的表就没有这条结论。

## 结果表（待实跑填写）

固定项：34 题、`k=5`、分块 `1000/150`。数字格保持 `—` 直到该模式真实跑完。

### 语料内（`questions.csv`，34 题）

| 模式 | 引用率 | 关键词命中率 | 资料不足次数 | 人工忠实度（通过/题） | 备注 |
| --- | ---: | ---: | ---: | ---: | --- |
| grounded | — | — | — | — | |
| hybrid | — | — | — | — | |
| knowledge | — | — | — | — | 引用率先验为 0 |

### 语料外（`questions-ooc.csv`，6 题；未跑则整表保持「—」）

| 模式 | 引用率 | 资料不足次数 | 无引用仍作答次数 | 备注 |
| --- | ---: | ---: | ---: | --- |
| grounded | — | — | — | 先验：应多弃权 |
| hybrid | — | — | — | 先验：可能无引用仍作答 |
| knowledge | — | — | — | 不检索，引用率先验为 0 |

「无引用仍作答」= 正文不是精确「资料不足」，且已验证引用数为 0。

## 命令

`--mode` 与 `--questions` 已经接到 `evaluate_retrieval.py`。一律在 `backend/` 下、对**隔离数据库**执行。不要对开发库或用户数据跑，也不要用 `pytest` 去连某个固定端口充当评测。

**会消耗聊天/嵌入 API 费用，不要进 CI。**

```bash
# 在 backend/ 下。先确认评测连的是隔离库，而不是开发库。

uv run python scripts/evaluate_retrieval.py --with-answers --mode grounded \
  --report ../docs/evaluation/runs/mode-grounded.md
uv run python scripts/evaluate_retrieval.py --with-answers --mode hybrid \
  --report ../docs/evaluation/runs/mode-hybrid.md
uv run python scripts/evaluate_retrieval.py --with-answers --mode knowledge \
  --report ../docs/evaluation/runs/mode-knowledge.md

# 语料外 6 题（不要并入 34 题基线）
uv run python scripts/evaluate_retrieval.py --with-answers --mode grounded \
  --questions ../docs/evaluation/questions-ooc.csv \
  --report ../docs/evaluation/runs/mode-grounded-ooc.md
```

跑完后把报告自动汇总的引用率、关键词命中率、资料不足次数和无引用仍作答次数抄进上表；人工忠实度逐题标注后再填。空格保持 `—`，不要用假设百分比占位。不要覆盖 `latest-results.md`（那是默认 grounded 路径的既有快照，不是本对照）。

## 局限（须写进论文）

- **单次 provider / 单日**：结果绑定当次聊天模型、嵌入模型、日期与网络状况，不能外推成“RAG 普遍更好”。
- **语料是合成且自描述的**：约 7 篇短 Markdown，内容就是 NoteLLM 自身说明，不是开放域问答基准。
- **引用校验是文件级成员关系**，不是 NLI / 蕴含判定：后端只确认 citation ID 属于本次检索候选，并在现有脚本里核对期望**文件名**；不验证句子是否真被摘录支持。
- **不要在 CI 里跑**。这是带密钥机器上的论文产物。评测脚本会创建临时用户与来源，结束时删除，不使用用户上传资料。
