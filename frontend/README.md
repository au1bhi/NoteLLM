# NoteLLM 前端

笔记本工作区、流式问答、引用摘录与聚合甘特图。技术栈：Vite、React、TypeScript、TanStack Query / Router、Tailwind CSS。界面为中文，主题为 kraft / ink。

## 要求

- [Bun](https://bun.sh/)（推荐）或 [Node.js](https://nodejs.org/)

## 本地开发

仓库根目录：

```bash
bun install
bun run --filter frontend dev
```

浏览器打开 <http://localhost:5173>。完整栈（后端、数据库与可选邮件服务）用根目录 `docker compose watch`，见 [`../development.md`](../development.md)。

改了后端 OpenAPI 契约后，重新生成 `src/client`，不要手改生成文件。

```bash
bun run --filter frontend lint
bun run --filter frontend build
```

不要提交用户上传、真实供应商地址或密钥。论文截图清单见 [`../docs/thesis/SCREENSHOTS.md`](../docs/thesis/SCREENSHOTS.md)。
