# 附录（粘贴用草稿）

> 用法：附录放「正文放不下、但答辩要核对」的材料。不要把第 4、5、6 章再抄一遍。示例主机只用 RFC 2606。

## 附录 A　STRIDE 资产表

完整表见仓库 `docs/project/THREAT_MODEL.md`。正文第 5 章只写四点控制与残余风险；答辩若被问「还考虑过哪些威胁」，翻本附录，不要现场扩写成未实现的 WAF 或审计日志。

必须一起念出的残余风险：

- 白名单只约束引用 ID，答案正文仍可能服从注入。
- `hybrid` / `knowledge` 允许无引用作答。
- 任意公网主机都可当 BYOK 目标。
- `SECRET_KEY` 泄露可解密已存用户密钥。

## 附录 B　已有安全回归对照

完整表见 `docs/evaluation/security-experiments.md`。每一行都对应仓库里已经存在的 pytest 函数名，例如：

- `test_user_cannot_access_another_users_study_plan` → 他人计划 **404**
- `test_blocks_canonical_private_hosts` / `test_blocks_numeric_bypass_forms` → BYOK 地址 **422**
- `test_reserve_usage_is_atomic_and_stops_at_quota` → 额度预留停在上限
- `test_reminder_requires_verified_email` → 未验证邮箱不能开提醒
- `test_list_study_plans_reports_uninitialized_schema` → 缺表 **503**

这些用例走隔离 pgvector 与假 provider。绿测试证明回归仍通过，不能写成「已完成渗透测试」。

## 附录 C　评测集与口径

- 语料：`docs/evaluation/sources/`，7 份合成 Markdown，自描述、无用户上传。
- 正例：`docs/evaluation/questions.csv`，34 题，每题一个期望来源文件。
- 语料外：`docs/evaluation/questions-ooc.csv`，6 题，`expected_source=none`，用来看 `grounded` 是否落到固定句。
- 指标定义：`docs/evaluation/sources/study_protocol.md`。Recall@5 是来源级成员关系，不是 chunk 命中，也不是 MRR。
- 基线报告：`docs/evaluation/latest-results.md`（2026-07-23，`cb0ead1`）。人工说明：`docs/evaluation/human-faithfulness.md`。
- 消融与模式对照：协议已接通，数字格在本机实跑前保持「—」。新报告写入 `docs/evaluation/runs/`。

## 附录 D　复现命令

隔离库上执行，不要打开发用的 Compose 5433。

```bash
# 后端检查（另起 pgvector，端口不要 5432/5433）
cd backend
uv run ruff check
uv run pytest -q

# 前端
cd frontend
bun run lint
bun run build

# 评测（会调用真实模型，写入 runs/，不覆盖 latest-results）
cd backend
uv run python scripts/evaluate_retrieval.py \
  --top-k 5 --mode grounded \
  --chunk-size 1000 --chunk-overlap 150 \
  --with-answers \
  --report ../docs/evaluation/runs/baseline-rerun.md
```

本地开发：仓库根目录 `docker compose up -d` 后，在 `backend` 执行 `alembic upgrade head`。`fastapi dev` 不会自动迁移。

## 附录 E　截图与演示

截图清单见 [`SCREENSHOTS.md`](SCREENSHOTS.md)。不要使用仓库 `img/`。演示脚本见 `docs/project/DEFENSE_DEMO.md`（不要对 5433 跑 pytest，也不要覆盖基线报告）。演示资料见 `docs/demo/` 与 `backend/scripts/seed_demo.py`。截图和演示账号里不要出现真实邮箱、真实供应商地址或密钥。
