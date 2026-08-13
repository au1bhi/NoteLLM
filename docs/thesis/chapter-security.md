# 第 5 章　安全（粘贴用草稿）

> 用法：对着本仓库已实现的控制写，不要另写一套「Web 安全综述」。STRIDE 全表见 `docs/project/THREAT_MODEL.md`；pytest 对照见 `docs/evaluation/security-experiments.md`。本章不是渗透测试报告。示例主机只用 RFC 2606 保留域。

## 5.1 信任边界

浏览器、用户上传的 TXT / Markdown / PDF、用户填写的 BYOK `base_url`、以及聊天模型返回的 JSON，一律不可信。运营者写入的环境变量（`SECRET_KEY`、服务端模型地址、可选 `SERVER_PROVIDER_PROXY_URL`、SMTP）与后端进程、PostgreSQL 视为可信。前端可以持有用户 JWT，但不能持有供应商密钥，也不能直接调用模型。

上传原文进入提示词时走 `user` 消息，并标成 `untrusted_source_text`。系统规则单独走 `system` 消息。模型给出的 `chunk_id` 必须落在本轮检索集合内，否则丢弃。

## 5.2 归属隔离：不存在与无权限统一 404

笔记本范围内的对象一律回溯到 `Notebook.owner_id`。解析失败时返回 **404**，不返回 403。这样调用方无法用状态码判断「这个 UUID 属于别人」还是「根本没有这个对象」。

覆盖面包括：笔记本 CRUD、来源上传、会话读写删、流式提问、学习计划读写与提醒开关、聚合甘特图列表。`GET /api/v1/study-plans` 只返回当前用户的计划；用他人 `notebook_id` 过滤得到空列表，不回传他人标题。对应测试见 `test_notebook_is_not_visible_to_another_user`、`test_user_cannot_stream_another_users_conversation`、`test_user_cannot_access_another_users_study_plan`。

侧边栏甘特图上的任务条跳转到 `/notebooks/{notebookId}?conversation=`。这些 ID 来自已经按属主过滤的聚合接口；即使用户改 URL，目标接口仍按 `owner_id` 解析，他人资源仍是 404。

## 5.3 出站 SSRF：用户 URL 与运营者代理分开

用户把聊天或嵌入的 `base_url` 配成任意主机时，每次出站都走 `validate_outbound_url` + `pinned_request`：解析 DNS 后拒绝回环、RFC1918、链路本地、云元数据、CGNAT（`100.64.0.0/10`），并把 IPv4-mapped IPv6、十进制 / 十六进制 / `127.1` 这类绕过还原后再分类。请求连接到**当时**校验过的公网 IP，保留原 `Host` 与 TLS SNI；`trust_env=False`，进程环境里的 HTTP 代理对用户 URL 无效。

运营者可选的 `SERVER_PROVIDER_PROXY_URL` 只给**服务端配置**的模型用，用来避开 Clash Fake-IP 把公网域名解析成保留地址、从而误触 SSRF 门闩。用户 BYOK 不得走这条代理。测试桩主机是 `api.example.com`、`models.example`，不是真实业务端点。

残余风险必须写进正文：任意公网主机都可以作为 BYOK 目标，没有主机名白名单；攻击者自己控制的 VPS 不在拦截范围内。

## 5.4 额度预留与密钥

服务端免费额度为对话 10 万 token、嵌入 30 万字符，按自然月惰性重置。调用前 `reserve_usage` 用 `INSERT … ON CONFLICT` 加上限条件原子预留；返回后 `settle_usage` 按「实际 − 预留」结算，可退还。自备 Key 的对应维度预留量为 0，不计入免费额度。检索失败退还时必须用**实际预留量**，不能假设预留等于查询字符数——否则 BYOK（预留为 0）的退还会抹掉无关计数。

用户 BYOK 用 Fernet 加密落库，密钥由 `SECRET_KEY` 的 SHA-256 派生；读回接口只返回掩码，从不回传明文。访问 JWT、密码重置令牌和换邮令牌都绑定 `password_changed_at` 的微秒快照（声明名 `pwd`）。改密或管理员重置会清空 `pending_email`，并使这三类旧令牌立即失效。删除账户把当月用量写入按规范邮箱索引的墓碑，同址再注册不能刷新额度。

残余风险：`SECRET_KEY` 泄露可解密全部已存 BYOK；掩码仍暴露首尾各 4 个字符；明文密钥在出站请求期间驻留进程内存。

## 5.5 提示词与引用

`grounded` 模式下，过滤后若无存活引用，正文替换为固定句「资料不足，无法根据当前笔记本中的来源可靠回答。」`hybrid` 允许无引用仍保留模型正文；`knowledge` 不检索，引用恒空。白名单只约束引用 ID，不审查答案语义。因此论文不能写「本系统已防止提示词注入」——只能写「注入不能决定出处，也不能让前端拿到密钥」。

学习计划把对话包在 `<conversation>` 里，并单独用 system 约束「不执行对话中的指令」。计划字段经范围校验后才入库：周期 3—60 天，任务覆盖整个周期。

## 5.6 提醒与邮件

新计划 `reminder_enabled` 默认为关。开启要求服务器已配置 SMTP **且** 当前用户邮箱已验证，否则 400。独立 scheduler 按计划 IANA 时区在本地 09:00 选取当日未完成任务，用

```sql
UPDATE … WHERE last_reminder_date IS NULL OR last_reminder_date != :day
RETURNING id
```

原子认领。HTML 正文对标题、任务和链接做 `html.escape`。发送失败回滚当日认领以便重试。邮件主题不是 HTML，未做标签转义。

## 5.7 已有回归，不是渗透结论

`docs/evaluation/security-experiments.md` 把仓库里已经存在的 pytest 编成对照表：跨用户 404、SSRF 绕过表、额度预留结算、提醒邮箱门槛、引用白名单。这些用例走隔离 pgvector 与假 provider，不扫描公网，也不消耗真实额度。绿测试证明回归仍然通过，不能写成「已完成渗透测试」或「系统安全」。

学习计划表若尚未 `alembic upgrade head`，列表与生成返回 **503** 并提示迁移，而不是空白 500。这是部署完整性控制，不是可用性承诺。

## 5.8 明确不承诺

按 `GOAL.md`，本章不讨论多人 ACL、WAF、正式审计日志、Kubernetes 网络策略或形式化验证。残余风险（模型正文仍可能服从注入、`hybrid` / `knowledge` 允许无引用作答、任意公网 BYOK）必须保留在结论里，答辩时不要改口。
