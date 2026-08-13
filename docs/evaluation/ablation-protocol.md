# 消融实验协议

本协议只规定论文实验章如何做单变量对照，**不在此仓库里跑现场评测**。语料与问题均为合成内容，不含用户上传资料、账号、密钥或个人信息。填写数字时，把各轮报告抄进 [`ablation-template.md`](ablation-template.md)。

## 单变量规则

与 [`sources/study_protocol.md`](sources/study_protocol.md) 和 [README](README.md) 一致：**同一轮不得同时改 Top-K 与分块长度/重叠**。比较配置时保持相同语料与问题，只动一个因子，其余记入配置头后保持不变。

禁止在同一轮里同时改：

- 检索数量 `k` 与分块长度或重叠；
- 嵌入模型 / 向量维度与上述任一检索参数；
- 问题文件与检索参数。

允许的对照只有两条独立扫描线：

1. **Top-K 扫描**：固定分块 `1000/150`，只改 `k`。
2. **分块扫描**：固定 `k=5`，只改分块长度与重叠。

## 因子与取值

检索硬上限为 10（后端 `limit` 约束 `ge=1, le=10`），因此 `k=8` 合法。**不要开 `k=20`**，该值会被拒绝，也不能写进论文对照。

| 因子 | 取值 | 固定条件 |
| --- | --- | --- |
| Top-K | `{3, 5, 8}` | 分块 `1000/150` |
| 分块长度/重叠 | `{500/50, 1000/150, 1500/200}` | `k=5` |

默认点 `k=5`、分块 `1000/150` 是两条扫描线的交点，应只跑一次并同时填入两张表。

## 每轮必须记录

抄进 [`ablation-template.md`](ablation-template.md) 配置头，或写在该轮报告开头：

- git commit（短哈希）
- 嵌入模型
- 向量维度（本协议固定 **1024**）
- 聊天模型
- Top-K
- 分块长度 / 重叠
- 问题文件（默认 `docs/evaluation/questions.csv`，**34** 题）
- 运行日期
- 数据库镜像（镜像名与标签，例如本地隔离实例所用的 Postgres/pgvector 镜像）

不要把真实供应商端点、API 密钥或用户资料写进报告。需要占位 URL 时只用 RFC 2606 保留域（`*.example.com`、`*.example.invalid`）。

## 从评测报告抄录的指标

指标定义与 [`sources/study_protocol.md`](sources/study_protocol.md) 一致。Recall 随本轮 `k` 记为 Recall@k，不要把 `k=3` 的结果标成 Recall@5。

| 指标 | 定义 | 抄录来源 |
| --- | --- | --- |
| Recall@k | 来源文件名命中：前 k 个返回分块中至少有一个来自期望文件名的题数 / 全部题数 | 报告「自动指标」 |
| 引用正确率 | 模型生成了回答时，至少一个已验证引用来自期望来源；未知 chunk ID 必须已被后端丢弃，不得计为正确 | 报告「引用正确率（自动）」 |
| 关键词命中 | 自动化忠实度筛查：回答是否包含该题指定关键词；**不等于**人工审核已通过 | 报告「关键词命中率」 |
| 检索均值 / P95 | 从开始调用检索到拿到检索结果，毫秒 | 报告检索平均与 P95 |
| 回答均值 / P95 | 从开始调用回答到拿到回答结果，毫秒 | 报告回答平均与 P95 |

网络波动、供应商限流和冷启动写在该轮「备注」。最终忠实度仍须人工逐题阅读答案、引用摘录与期望事实；本协议的表只收自动指标。

## 必须写进论文的局限

- **Recall 是来源文件名命中**，不是 chunk 级命中，也不是 MRR / nDCG。
- **语料是合成且自描述的**：约 7 篇短 Markdown，内容就是 NoteLLM 自身说明，不是开放域检索基准。
- **本集合上 Recall@5 = 100% 是天花板**，不能当成检索科学研究结论。
- **不要在 CI 里跑**。这是带密钥机器上的论文产物：本地隔离数据库 + 已配置的嵌入/聊天 provider。评测脚本会创建临时用户与来源，结束时删除，不使用用户上传资料。

## 如何运行

`--top-k`、`--chunk-size`、`--chunk-overlap` 已经接到 `evaluate_retrieval.py`，并转发给 `answer_question` / `process_source`。一律在 `backend` 目录、对**隔离数据库**执行。不要对开发库或用户数据跑，也不要用 `pytest` 去连某个固定端口充当评测。

需要引用与关键词指标时加 `--with-answers`。报告写入 `docs/evaluation/runs/`，不要覆盖 `latest-results.md`。

```bash
# 在 backend/ 下。先确认评测连的是隔离库，而不是开发库。

# --- Top-K 扫描（固定分块 1000/150）---
uv run python scripts/evaluate_retrieval.py --top-k 3 --report ../docs/evaluation/runs/topk-3.md
uv run python scripts/evaluate_retrieval.py --top-k 5 --report ../docs/evaluation/runs/topk-5.md
uv run python scripts/evaluate_retrieval.py --top-k 8 --report ../docs/evaluation/runs/topk-8.md

# --- 分块扫描（固定 k=5；1000/150 与上一组 k=5 为同一轮，勿重复跑）---
uv run python scripts/evaluate_retrieval.py --top-k 5 --chunk-size 500 --chunk-overlap 50 --report ../docs/evaluation/runs/chunk-500-50.md
uv run python scripts/evaluate_retrieval.py --top-k 5 --chunk-size 1500 --chunk-overlap 200 --report ../docs/evaluation/runs/chunk-1500-200.md
```

跑完后把各报告的自动指标抄进 [`ablation-template.md`](ablation-template.md)，空格保持 `—` 直到该轮真实跑完。
