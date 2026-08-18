# 安全实验清单

本清单把仓库里**已经存在**的 pytest 安全回归用例整理成论文可引用的对照表。它不是渗透测试报告，也不声称覆盖全部攻击面。威胁分类与残余风险见 [`docs/project/THREAT_MODEL.md`](../project/THREAT_MODEL.md)。

规则：

- 表中的测试文件与函数名均来自当前仓库，未新增用例。
- 「期望结果」只复述测试里已经断言的行为，不把未测事项写成已验证。
- 示例主机只用 RFC 2606 保留域（如 `example.com`、`invalid`）和文档常见公网解析桩（如 `8.8.8.8`）；不含用户真实端点或密钥。

## 安全验证表

| 威胁 | 测试文件 | 测试函数 | 期望结果 |
| --- | --- | --- | --- |
| 跨用户学习计划（IDOR） | `backend/tests/api/routes/test_study_plans.py` | `test_user_cannot_access_another_users_study_plan` | 他人计划的 `PATCH` 返回 **404**（不是 403） |
| 聚合列表隔离 | 同上 | `test_list_study_plans_aggregates_owned_conversations` | 列表只含属主计划；按他人 `notebook_id` 过滤得到空列表；他人计划标题不可见 |
| 提醒需验证邮箱 | 同上 | `test_reminder_requires_verified_email` | 未验证时开启提醒 **400**（detail 含「验证邮箱」）；验证后同一请求 **200** 且 `reminder_enabled` 为真 |
| 学习计划 schema 缺失 | 同上 | `test_list_study_plans_reports_uninitialized_schema` | 列表在表未初始化时 **503**，detail 提示 `alembic upgrade head` |
| 学习计划 schema 缺失（生成） | 同上 | `test_generate_study_plan_reports_uninitialized_schema` | 生成计划同样 **503**，detail 提示 `alembic upgrade head` |
| SSRF：回环 / 私网 / 云元数据 | `backend/tests/core/test_ssrf.py` | `test_blocks_canonical_private_hosts` | `validate_outbound_url` 对 `127.0.0.1`、`localhost`、`[::1]`、`169.254.169.254`、`0.0.0.0`、`metadata.google.internal`、`10.0.0.5`、`192.168.1.1` 抛 **422** |
| SSRF：十进制 / 十六进制 / 简写绕过 | 同上 | `test_blocks_numeric_bypass_forms` | 对十进制、`0x`、八进制、`127.1` 等绕过形式抛 **422** |
| SSRF：不可解析主机 | 同上 | `test_blocks_unresolvable_host` | DNS 失败时拒绝，**422** |
| SSRF：非 HTTP 协议 | 同上 | `test_rejects_non_http_scheme` | `ftp://`、`file://` 拒绝，**422** |
| SSRF：公网主机放行 | 同上 | `test_allows_public_host` | 解析到公网地址时放行 `https://api.example.com/v1`（测试桩，非真实业务端点） |
| SSRF：IPv4-mapped IPv6 / CGNAT | 同上 | `test_blocks_ipv4_mapped_ipv6_private_forms` | 拒绝 mapped 形式的 CGNAT（`100.64.0.0/10`）、回环、RFC1918、链路本地 / 元数据；公网 mapped 地址仍可通过 |
| Turnstile 覆盖公开认证 | `backend/tests/core/test_turnstile.py` | `test_protected_auth_endpoints_require_turnstile_header`、`test_valid_turnstile_token_reaches_login` | 启用后登录、注册、找回密码缺 token 均 **400**；有效 token 才进入原认证逻辑 |
| Turnstile 失败关闭与配置 | 同上 | `test_turnstile_network_failure_returns_503`、`test_overlong_token_is_rejected_without_provider_call`、`test_turnstile_keys_must_be_configured_together` | Cloudflare 网络失败 **503**；超长 token 本地拒绝；site/secret 单边配置启动校验失败 |
| CORS 请求面收窄 | `backend/tests/api/routes/test_meta.py` | `test_cors_preflight_allows_declared_turnstile_header`、`test_cors_preflight_rejects_undeclared_header` | 明确允许认证所需 header；未声明 header 的预检 **400** |
| 代理头伪造 / Tunnel 单桶 | `backend/tests/core/test_rate_limit.py` | `test_direct_client_cannot_spoof_forwarding_headers`、`test_cloudflare_header_is_ignored_behind_trusted_public_proxy`、`test_tunnel_converted_xff_is_resolved_behind_trusted_ingress` | 非可信 peer 的头无效；公网代理后的伪造 CF 头被忽略；Tunnel 经 nginx 转换的 XFF 可恢复真实客户端 |
| 限流存储上限 | 同上 | `test_ipv6_rate_limit_identity_groups_by_64_without_truncating_client_ip`、`test_new_bucket_capacity_fails_closed_but_existing_bucket_updates`、`test_new_bucket_capacity_is_atomic_across_concurrent_workers` | IPv6 按 `/64` 聚合；新桶容量满时 503；并发准入不突破硬上限，已有桶仍可计数 |
| 额度耗尽：嵌入检索 | `backend/tests/api/routes/test_usage.py` | `test_embedding_quota_exhausted_blocks_search` | 搜索 **429**，detail 含「免费嵌入额度已用完」 |
| 额度耗尽：资料上传 | 同上 | `test_embedding_quota_exhausted_blocks_upload` | 上传 **429**，detail 含「免费嵌入额度已用完」 |
| 额度耗尽：笔记本概览 | 同上 | `test_chat_quota_exhausted_blocks_overview` | 概览 **429**，detail 含「免费对话额度已用完」 |
| 额度耗尽：对话流 | 同上 | `test_chat_quota_exhausted_returns_error_event` | SSE 通道 HTTP **200**，事件正文含「免费对话额度已用完」（流式接口不改成 429） |
| 额度预留结算 | 同上 | `test_reserve_usage_is_atomic_and_stops_at_quota` | 两次半额预留后第三次抛 `QuotaError`；计数器不超过免费上限 |
| 周期滚动结算 | 同上 | `test_usage_rolls_over_when_period_changes` | 过期周期用量归零，查询 **200** |
| 自备 Key 不计服务端额度 | 同上 | `test_reserve_with_own_key_is_unlimited` | BYOK 预留量为 0，不计入免费额度 |
| 配额失败退款 / 零预留 | `backend/tests/services/test_usage.py` | `test_usage_reservation_refunds_only_reserved_amounts_on_failure`、`test_usage_reservation_ignores_actual_for_zero_reserved_dimension` | 异常只退本次真实预留；BYOK 的零预留维度不产生结算 |
| Fernet / JWT 用途分离 | `backend/tests/core/test_security.py` | `test_hkdf_separates_jwt_and_fernet_keys`、`test_new_jwt_uses_derived_key_and_legacy_jwt_still_decodes` | HKDF 子密钥不同；新 JWT 不能用 raw `SECRET_KEY` 验证，旧 JWT 仍可迁移读取 |
| 旧 Fernet 密文兼容 | 同上 | `test_decrypt_secret_accepts_legacy_sha256_ciphertext` | 升级后仍能解密旧 SHA-256 派生密钥写入的 BYOK |
| PDF 页码与损坏处理 | `backend/tests/services/test_sources.py` | `test_extract_pages_from_real_pdf_preserves_page_numbers`、`test_corrupt_pdf_marks_source_failed_and_removes_existing_chunks` | 真实两页 PDF 保留 1/2 页码；损坏 PDF 变为 `failed`、清掉旧 chunk 且不调用 embedding provider |
| 笔记本跨用户 / 不存在 | `backend/tests/api/routes/test_notebooks.py` | `test_notebook_is_not_visible_to_another_user` | 他人笔记本不出现在列表；`GET` / `PUT` / `DELETE` 均为 **404**（不是 403） |
| 笔记本不存在 | 同上 | `test_read_notebook_not_found` | 随机 UUID **404** |
| 会话跨用户读取 | `backend/tests/api/routes/test_conversations.py` | `test_user_cannot_read_another_users_conversation` | **404** |
| 会话跨用户改名 | 同上 | `test_user_cannot_rename_another_users_conversation` | **404** |
| 会话跨用户删除 | 同上 | `test_user_cannot_delete_another_users_conversation` | **404** |
| 会话跨用户流式提问 | 同上 | `test_user_cannot_stream_another_users_conversation` | **404** |
| 向他人笔记本上传 | `backend/tests/api/routes/test_sources.py` | `test_user_cannot_upload_to_another_notebook` | **404** |
| 引用白名单：未知 ID 丢弃 | `backend/tests/services/test_answers.py` | `test_answer_discards_citations_not_in_retrieved_set` | 模型给出检索集合外的 chunk ID 时，引用被清空，正文替换为固定「资料不足」 |
| 引用白名单：只保留检索命中 | 同上 | `test_answer_persists_only_retrieved_citation` | 仅保留本轮检索到的 ID，重复 ID 去重 |

上表是论文「安全验证」的主表。下列用例同属自动化回归，可按需在附录引用，但不是本清单的最低集合。

| 威胁 | 测试文件 | 测试函数 | 期望结果 |
| --- | --- | --- | --- |
| 登录接口跨 worker 共享限流 | `backend/tests/core/test_rate_limit.py` | `test_login_endpoint_rate_limited_after_many_attempts` | PostgreSQL 共享窗口内第 21 次 **429**，`Retry-After` 为 1—60 秒 |
| 邮箱域名白名单绕过 | `backend/tests/api/routes/test_email_domain_whitelist.py` | `test_is_allowed_email_bypass_battery`、`test_signup_rejects_lookalike_domains`、`test_signup_malformed_email_cannot_bypass` | 形似域名、畸形地址不能绕过允许列表 |
| 令牌用途隔离 | `backend/tests/api/routes/test_email_verification.py` | `test_verify_token_is_purpose_scoped`、`test_purpose_token_as_bearer_is_403_not_500` | 验证令牌不能当登录令牌；误用为 Bearer 时 **403** 而非 500 |
| 改密撤销旧 JWT | `backend/tests/api/routes/test_users.py` | `test_access_token_without_pwd_snapshot_is_rejected`、`test_admin_password_reset_revokes_existing_jwts` | 无口令快照或改密前签发的令牌失效 |
| 删除后重注册不能刷新额度 | 同上 | `test_delete_and_reregister_preserves_allowance` | 同址再注册保留当月已用量 |

## 如何复现

这些用例走后端测试夹具，会写入并清理测试库。必须指向**独立**的 pgvector 实例，**不要**把 pytest 打到 Compose 开发库映射的 `5433`：那是本地 `compose.override.yml` 给应用用的端口，套件会删用户数据。

从 `backend` 目录运行：

```bash
# isolated pgvector, NEVER compose 5433 for pytest
POSTGRES_PORT=<isolated> uv run pytest tests/core/test_ssrf.py tests/api/routes/test_usage.py tests/api/routes/test_study_plans.py -q
```

把 `<isolated>` 换成独立实例的端口。需要把上表主表一次跑完时，可追加：

```bash
POSTGRES_PORT=<isolated> uv run pytest \
  tests/core/test_ssrf.py \
  tests/core/test_rate_limit.py \
  tests/core/test_security.py \
  tests/core/test_turnstile.py \
  tests/api/routes/test_meta.py \
  tests/api/routes/test_usage.py \
  tests/api/routes/test_study_plans.py \
  tests/api/routes/test_notebooks.py \
  tests/api/routes/test_conversations.py \
  tests/api/routes/test_sources.py \
  tests/services/test_answers.py \
  tests/services/test_sources.py \
  tests/services/test_usage.py \
  -q
```

CI 在独立服务里跑完整 `backend/scripts/test.sh`，不依赖本机 `5433`。

套件默认关闭 SMTP（见 `backend/tests/conftest.py` 的 `_disable_email_verification_gate`），避免开发者 `.env` 误开邮件后门闩。需要邮件路径的用例会自行 `monkeypatch` `SMTP_HOST`。provider 调用在测试中被替换为桩，不消耗真实额度。

## 与威胁模型的对应关系

| 本表行组 | `THREAT_MODEL.md` 资产 |
| --- | --- |
| 学习计划跨用户 / 聚合列表 / 笔记本与会话 404 | 笔记本、会话、学习计划（IDOR，统一 404） |
| 提醒需验证邮箱 | 学习提醒邮箱 |
| SSRF 绕过表 | 服务器出站网络（BYOK URL） |
| Turnstile / 共享限流 / 代理链 / CORS | 公开认证与限流 |
| 额度预留与超限 | 服务端免费额度 |
| HKDF 与旧密文兼容 | Provider 密钥与 `SECRET_KEY` |
| 引用白名单 | 系统提示词与引用集合 |
| schema 503 | 部署完整性（缺表时拒绝服务式失败，而不是空白 500） |

威胁模型写的是设计与残余风险；本清单只证明对应回归用例仍然通过。两边一起引用，不要把 pytest 绿写成「已完成渗透测试」。

## 边界

- 自动化回归，不是渗透测试报告，也不是形式化证明。
- 未单独列名的用例不代表不存在，只是不在本表最低引用集中。
- 套件不发起真实出站请求，也不扫描公网；SSRF 用例在进程内调用 `validate_outbound_url`。
- 不要把本文件中的示例 URL 写成用户真实反代或聚合站地址。
