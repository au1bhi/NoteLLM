# 前端质量评估

本记录覆盖认证人机验证、流式问答交互、错误与加载状态，以及当前仓库可重复执行的前端检查。日期：2026-08-19。

## 自动化检查

从仓库根目录执行：

```bash
bun run --filter frontend lint
bun run --filter frontend build
```

本轮结果：TypeScript 严格类型检查、Vite 生产构建和 Biome 检查均通过，Biome 零诊断。配置 schema 已与 CLI 2.4.16 对齐，过期的 `ModelPicker.tsx` 抑制注释已删除。

仓库当前没有前端 `test` 脚本，也没有 Vitest、Jest 或 Playwright 配置，因此不能声称存在前端单元测试或浏览器端到端测试。后端测试覆盖 API 契约；下列浏览器行为需按本页清单人工验收。若以后引入浏览器测试，应先提交真实的测试框架和服务配置，再把命令加入 CI。

## 静态契约证据

```bash
rg -n "meta/turnstile|X-Turnstile-Token" \
  frontend/src/services/auth.ts backend/app
rg -n "challenges.cloudflare.com" frontend/nginx.conf
rg -n "AbortController|onCancelStream|streamPhase|streamError" \
  frontend/src/routes/_layout/notebooks/'$notebookId'.tsx \
  frontend/src/components/Notebooks/ChatPanel.tsx
```

- `GET /api/v1/meta/turnstile` 决定是否渲染组件；未配置站点密钥时不加载 Cloudflare 脚本。
- 登录、注册、找回密码使用 OpenAPI 生成客户端保持 form/body 契约，并统一通过 `X-Turnstile-Token` 传递一次性 token。
- token 过期、验证错误或认证请求失败后会清空并重置组件；配置或脚本加载失败时提交按钮保持禁用并提供重试。
- 生产 CSP 只为 `https://challenges.cloudflare.com` 增加脚本、连接和 iframe 权限，`script-src` 仍未加入 `unsafe-inline` 或 `unsafe-eval`。
- grounded/hybrid 流式请求展示检索、生成和保存阶段，knowledge 模式直接进入生成；非 2xx 响应优先显示后端中文 `detail`，收到 `done` 后立即结束读取而不等待代理关闭连接。用户可停止接收与显示，接收期间仍可编辑下一条问题。当前后端在发送 SSE 分块前已经完成模型调用和持久化，因此客户端中止不等于取消后台工作。

## 浏览器验收矩阵

使用 Cloudflare 官方测试站点密钥和测试密钥，不使用真实账户密钥。每种状态分别在桌面窄屏和移动宽度下检查，确认组件不溢出认证卡片、按钮和文案不重叠。

| 场景 | 操作 | 预期结果 |
| --- | --- | --- |
| Turnstile 关闭 | 不配置站点/服务端密钥，打开三个认证页 | 不下载 Turnstile 脚本，表单可正常提交 |
| Turnstile 开启 | 配置测试密钥，打开登录、注册、找回密码页 | 验证完成前提交禁用；完成后请求带 `X-Turnstile-Token` |
| token 失效 | 完成验证后等待 token 过期 | 提交重新禁用，组件允许再次验证 |
| 认证失败 | 使用失败测试密钥或让后端拒绝 token | 显示中文错误，旧 token 被重置，不能重复提交 |
| 脚本不可用 | 在浏览器中阻止 `challenges.cloudflare.com` | 显示“安全验证加载失败”和重试按钮 |
| 流式成功 | 在有就绪资料的会话中提问 | 阶段依次更新，文本增量稳定追加，完成后恢复持久化消息与引用 |
| 流式拒绝 | 触发额度或后端校验错误 | 页面内错误状态和 toast 展示后端 `detail`，乐观消息随后与服务端状态对齐 |
| 主动停止 | 接收中点击停止图标 | 客户端停止接收，页面明确回答可能仍在后台完成并保存，刷新会话后同步服务端结果；输入框中的下一条草稿保留 |
| 网络中断 | 流中断但没有 `done` 事件 | 显示“回答流意外结束，请重试”，不把半截文本伪装成已完成回答 |

人工验收不得调用计费模型；使用测试 provider 或固定合成资料。真实 provider 的论文评测仍按 `docs/evaluation/README.md` 在隔离环境执行。
