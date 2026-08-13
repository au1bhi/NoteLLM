# 摘要与关键词（粘贴用草稿）

> 用法：中文摘要约 300—500 字，英文 Abstract 与之对应，不要扩成综述。数字只引用 2026-07-23、提交 `cb0ead1` 的基线。消融表未跑之前，摘要里不要出现「消融表明」「RAG 显著优于」这类句子。题目与仓库首页一致。

## 题目

基于FastAPI与RAG的个人学习问答系统设计与实现

## 中文摘要

针对个人学习中大语言模型容易偏离手头资料、缺少可核对出处、难以把一次问答变成后续安排的问题，本文设计并实现了面向单用户笔记本的检索增强问答原型 NoteLLM。系统将 UTF-8 文本、Markdown 与可提取文本的 PDF 放入笔记本，按 1 000 字符、150 字符重叠分块后写入 PostgreSQL + pgvector 的 1024 维索引；提问只在当前笔记本的就绪来源上取余弦 Top-K。聊天模型必须返回 JSON 答案与 chunk 标识，服务端只保留本轮检索集合内的引用；无存活引用时，`grounded` 模式将正文替换为固定句「资料不足，无法根据当前笔记本中的来源可靠回答。」`hybrid` 与 `knowledge` 作为对照策略存在，不与默认路径混写。系统还可从会话生成校验过的 3—60 天学习计划，提醒默认关闭且要求邮箱已验证。多用户场景下，不存在与无权限统一返回 404；用户自备接口地址与运营者代理分开；免费额度先原子预留再按实际结算。

在 7 份合成资料、34 道固定题上的单次基线为：来源级 Recall@5 100.0%，自动引用来源匹配 97.1%，关键词筛查 88.2%，检索 P95 894 ms，回答 P95 5595 ms。人工对照摘录后 34 题全部通过；自动指标缺口由千分位写法、近义漏检和来源级标注碰撞解释，不是幻觉。100% 召回只说明这份自描述语料的天花板，不能外推到真实教材。本文的贡献是可演示、可评测、可复现的工程闭环，而不是新的检索公式。

**关键词：** 检索增强生成；个人学习；引用校验；FastAPI；pgvector；学习计划

## Abstract

Large language models are convenient for tutoring, but they often drift from the learner's own materials, omit checkable citations, and leave a single Q&A session hard to turn into the next few days of work. This thesis designs and implements NoteLLM, a single-user notebook prototype for retrieval-augmented question answering. UTF-8 text, Markdown, and extractable PDFs are stored per notebook, split into 1,000-character chunks with a 150-character overlap, and indexed as 1,024-dimensional vectors in PostgreSQL with pgvector. Questions retrieve only ready sources inside the current notebook by cosine distance. The chat model must return a JSON answer plus chunk identifiers; the server keeps citations only when those identifiers belong to the retrieved set. In `grounded` mode, an empty surviving set is replaced by a fixed insufficient-evidence sentence. `hybrid` and `knowledge` exist as contrasting policies and are not claimed as the default path. A conversation can also be mapped to a validated 3–60 day study plan; email reminders stay off unless the address is verified. Across users, missing and forbidden objects both return 404; user-supplied provider URLs are pinned separately from the operator proxy; free-tier usage is reserved atomically and settled against actual consumption.

On seven synthetic documents and thirty-four fixed questions (commit `cb0ead1`, 23 July 2026) source-level Recall@5 is 100.0%, automatic citation-to-source match is 97.1%, keyword screening is 88.2%, retrieval P95 is 894 ms, and answering P95 is 5,595 ms. Human review accepted all thirty-four answers; the automatic gaps are thousand-separator spelling, near-synonym misses, and a source-level label collision, not hallucination. Perfect recall is a ceiling on this self-describing corpus, not an open-domain retrieval result. The contribution is a demonstrable, measurable, reproducible engineering loop rather than a new retrieval formula.

**Keywords:** retrieval-augmented generation; personal learning; citation validation; FastAPI; pgvector; study plan
