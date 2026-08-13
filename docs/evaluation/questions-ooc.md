# 语料外负例（OOC）

本文件对应 `questions-ooc.csv`：6 道询问评测语料未记载事实的问题。
`expected_source` 固定为 `none`，`expected_answer_terms` 固定为 `资料不足`。
grounded 模式应拒答，供后续与 hybrid / knowledge 对比。

不要并入 `questions.csv` 的 34 题基线。

从 `backend` 目录、在隔离 pgvector 上运行（不要打 5433）。报告写入 `runs/`：

```bash
uv run python scripts/evaluate_retrieval.py \
  --questions ../docs/evaluation/questions-ooc.csv \
  --mode grounded \
  --with-answers \
  --report ../docs/evaluation/runs/ooc-grounded.md
```
