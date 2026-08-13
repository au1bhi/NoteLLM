# 固定评测集

本目录的资料和问题均为合成内容，不含用户上传资料、账号、密钥或个人信息。`questions.csv` 固定为 34 个问题；每题对应一个期望来源和用于自动筛查的关键词。

数据库与 provider 配好后，从 `backend` 目录运行。必须另起隔离 pgvector，不要打开发用的 Compose 5433。新报告写入 `docs/evaluation/runs/`，**不要**覆盖 2026-07-23 基线 `latest-results.md`。

```bash
uv run python scripts/evaluate_retrieval.py \
  --with-answers \
  --report ../../docs/evaluation/runs/local-run.md
```

`--with-answers` 会调用已配置的聊天模型，只作为论文实验产物，不要放进 CI。

可选参数：

- `--top-k K`：检索深度，默认 5，限制在 1–10。报告中的 Recall@{k} 与 `answer_question` 的 `limit` 都使用该值。
- `--mode {grounded,hybrid,knowledge}`：回答模式，默认 `grounded`。`knowledge` 仍跳过检索；Recall 仍单独跑一次检索以便计分。
- `--questions PATH`：评测问题 CSV。默认固定集须为 30–50 题；显式传入其他路径时允许 1–50 题（供库外 / OOC 小集使用）。
- `--chunk-size N` / `--chunk-overlap N`：分块长度与重叠，转发给 `process_source` / `split_page`。省略时用线上默认 1000 / 150。重叠必须小于长度，否则分块函数会拒绝。
- `--report PATH`：把 Markdown 报告写到指定路径。
- `--with-answers`：同时调用聊天模型测量引用与回答（论文实验，非 CI）。

`expected_source` 为 `none`（忽略大小写）的题目不计入 Recall 分母。带回答时，这类题在答案含“资料不足”或引用为空时记为引用成功；若把库内来源当作命中则记失败。

回答耗时包含 `answer_question` 内部的再次检索，与单独统计的检索耗时不可相加。

脚本创建临时评测用户、笔记本、来源和上传副本，结束时全部删除。它输出并可写入报告的指标包括：Recall@{k}、检索/回答平均和 P95 耗时、带引用回答的期望来源命中率，以及答案关键词命中率。带回答运行还会生成逐题的“人工忠实度复核表”，其中保存问题、模型回答和已验证引用来源。后两项的边界如下：

- “引用正确率（自动）”只验证有效引用是否来自标注的期望来源；后端本身已经拒绝未知 chunk ID。
- “关键词命中率”只是忠实度筛查信号，不等于人工忠实度。对应 2026-07-23 基线的 34 题已人工标完（34 通过 / 0 未通过），见 `human-faithfulness.md`。新跑仍须重新逐题审阅，不要把旧结论抄到新报告上。

为比较不同参数，应保持相同语料与问题，仅改变一个变量，并把代码提交、provider、向量维度、Top-K、回答模式、分块配置、日期和异常情况记入报告。
