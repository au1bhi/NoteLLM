# 2026-10-09 红队问题修复记录

## 范围与证据边界

输入为报告摘要（认证面 medium、finding 44/40/24/23 low），没有原始请求/响应或测试环境配置。不能把未复现的问题升级为已证实漏洞，也不能据此为其他攻击面出具全局安全结论。

当前代码在修复前已具备 PostgreSQL 共享的登录 IP 限流（20 次/60 秒）、DNS 公网检查、请求时 IP 固定、密钥隔离和生产关闭 API 文档。故“无限速”与当前代码不一致，需要对齐报告所测部署版本、配置和请求频率。2026-10-09 公网 `/api/v1/meta/turnstile` 返回 `enabled=false`、`site_key=null`，验证码确实未启用。公网 `/api` 返回 301、`/docs` 返回 302，Location 分别为 `http://notellm.au1bhi.com:8081/api/` 和 `http://notellm.au1bhi.com:8081/docs/`，finding 23 已在线复现；SSH 在握手/响应阶段超时，尚未核对或修改线上部署。

## 修复

- 登录保留 IP 限流，增加规范化邮箱维度 10 次/300 秒的数据库共享预算，跨 IP 和邮箱大小写/别名共用桶。在验证密码前原子计数，对不存在的账户同样处理，不暴露账户存在性；成功登录不重置预算，过量请求不延长固定窗口。返回 429 与 `Retry-After`。不永久锁号、不修改 `is_active`，恢复密码保留独立限流。已存在会话不受登录节流影响。
- 非 local 环境禁止 `RATE_LIMIT_ENABLED=false`。新增 `TURNSTILE_REQUIRED` 配置门禁：为 true 而密钥缺失时拒绝启动。验证码仍支持本地不配置；启用后沿用服务端 Siteverify 与失败关闭机制。
- finding 40：上传文件名在数据库写入、文件保存之前拒绝 ASCII 控制字符（含 NUL、DEL），返回中文 400。回归测试以真实原始 multipart 字节构造 NUL，不依赖客户端转义。
- finding 24：全部五处列表分页统一 `skip ∈ [0, 2147483647]`、`limit ∈ [1, 100]`，非法值由 FastAPI 返回 422；正常分页不变。
- finding 23：nginx 使用相对重定向，禁用内部端口写入 Location；`/docs` 直接代理到后端，让生产配置返回 404。保留专用 Tunnel listener 和可信客户端地址处理。
- finding 44：保存 BYOK 设置时立即校验目标，调用时继续复验并固定 IP；用户目标只允许 HTTPS/443，拒绝 userinfo、query、fragment；保存接口增加 10 次/分钟的 IP 限流。传输层强制不跟随重定向，即使调用者传入 `follow_redirects=True` 也不例外。
- 新增 `BYOK_ALLOWED_HOSTS` 精确域名允许列表（逗号分隔或 JSON，无通配符），同时适用于保存、模型发现、聊天和嵌入的用户配置解析。允许列表不能豁免私网/DNS 重绑定检查。服务端配置的代理仍只用于运营方目标。

BYOK 的产品功能本身需要访问用户选择的公网模型服务。因此默认空允许列表仍允许符合 HTTPS/443 与公网校验的任意服务，不能宣称“所有服务端出站原语已消失”或“报告证实了内网 SSRF”。如部署要求彻底限制公网探测，必须配置精确允许列表；已有自定义 HTTP、非 443 端口、query 凭据的配置需迁移至合规 HTTPS 端点。

## 上线配置与复验

1. 在 Cloudflare 创建绑定实际站点域名的 Turnstile widget，将有效 Site Key 和 Secret Key 写入服务器受保护的 `.env`，同时设置 `TURNSTILE_REQUIRED=true`。不得使用测试密钥冒充生产配置，不在日志、提交或聊天中输出 Secret Key。
2. 根据实际使用的模型服务填写 `BYOK_ALLOWED_HOSTS`（例如 `api.openai.com,api.deepseek.com`，只是示例，不是本项目部署清单），确认已有用户配置兼容。保留 `RATE_LIMIT_ENABLED=true`。
3. 前端仅在本地/CI 构建；服务器通过预构建产物和后端代码挂载更新。迁移门禁必须成功后再启动。nginx 配置先 `nginx -t` 再 reload；不要在轻量服务器编译。
4. 真实浏览器完成验证码和登录；检查无验证码/无效验证码被拒绝、有效验证码可登录。用测试邮箱验证账号/IP 节流及过期恢复，不使用真实用户账号做失败尝试。
5. 验证 `/api` Location 为 `/api/`，生产 `/docs`、`/docs/`、`/redoc`、`/api/v1/openapi.json` 为 404；验证非法分页 422、NUL 文件名 400、禁用出站目标 422。

## 参考

- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)：账号维度节流、避免永久锁号拒绝服务，CAPTCHA 是纵深防御。
- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)：按业务选择允许列表、验证解析地址、禁止自动重定向。

## 验证结果

- 独立 pgvector 数据库从空库完成迁移至 `7c3f9a1b2d40`；`alembic check` 无待生成迁移。
- 后端全量 **407 passed**，覆盖率 **91%**；SSRF、Turnstile、security、provider settings、rate limit、usage 六模块均为 **100%**，通过仓库覆盖率门禁。测试不调用真实 AI 服务；虚构 provider 域名以模拟 DNS 验证。
- mypy、ty、Ruff 及格式检查全部通过；顺带修复既有 `CursorResult` 缺少类型参数问题，并格式化三处已有格式偏差，未改变相关业务逻辑。
- `scripts/generate-client.sh` 重新生成客户端；前端 lint、TypeScript、同源 Vite 生产构建通过。未在 VPS 编译。
- 本机真实 nginx + 生产模式后端容器：正常登录及用户查询 200、笔记本创建/删除 200、负分页 422、原始 NUL 文件名 400、私网/HTTP provider 设置 422；轮换 Tunnel 客户端地址的第 11 次登录尝试 429 且带 Retry-After。
- 两个 nginx listener 均通过首页/登录页 200、文档端点 404、`/api` 相对重定向及 readiness 200；nginx -t 和生产低内存 Compose 配置解析通过。

**尚未部署**：线上 SSH 多次握手/响应超时，Turnstile 有效密钥及实际 provider 允许列表尚未取得。公开端点仍能复现 finding 23 和 Turnstile disabled；本记录不能作为线上已关闭问题的证明。
