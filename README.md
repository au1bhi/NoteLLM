<div align="center">

# NoteLLM

**基于 FastAPI 与 RAG 的个人可信知识库与智能学习计划系统**

*让个人资料中的每一个回答可溯源、可验证，并一键转化为可落地的学习甘特图与每日行动计划。*

[![Test Backend](https://github.com/au1bhi/NoteLLM/actions/workflows/test-backend.yml/badge.svg)](https://github.com/au1bhi/NoteLLM/actions/workflows/test-backend.yml)
[![Test Docker Compose](https://github.com/au1bhi/NoteLLM/actions/workflows/test-docker-compose.yml/badge.svg)](https://github.com/au1bhi/NoteLLM/actions/workflows/test-docker-compose.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-amber.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19.0-61DAFB.svg)](https://react.dev/)
[![pgvector](https://img.shields.io/badge/PostgreSQL-pgvector-336791.svg)](https://github.com/pgvector/pgvector)

[🌐 在线演示](https://notellm.au1bhi.com) · [✨ 核心特性](#-核心特性) · [🏗️ 架构与安全](#️-系统架构与安全体系) · [🚀 快速开始](#-快速开始) · [📊 实验与评测](#-实验与评测结果) · [📄 毕业设计与开源价值](#-毕业设计与开源价值)

---

</div>

## 💡 为什么选择 NoteLLM？

通用大语言模型回答迅速，但在个人学习与严谨学术场景中常面临三大痛点：**缺少权威出处、存在事实幻觉、以及知识无法直接转化为行动**。

**NoteLLM**（启发自 Google NotebookLM）提供了一个完整的个人知识库与学习执行闭环：
1. **真实可信**：支持 PDF、Markdown、TXT 资料解析与分块索引，问答严格匹配原文片段、出处与页码，证据不足主动说明；
2. **多模式问答**：支持 `资料可信模式 (Grounded)`、`混合补充模式 (Hybrid)`、`自由问答模式 (Knowledge)` 自由切换；
3. **学习闭环**：通过对话一键生成 3~60 天学习计划与**交互式甘特图**，自动规划难度、阶段任务、每日耗时与验收标准；
4. **自备算力 (BYOK)**：支持自带 OpenAI 兼容的第三方大模型与 Embedding API（如 DeepSeek、通义千问、Kimi 等），密钥强加密存储，保护隐私与额度自由；
5. **轻量极速**：专为单机与轻量云服务器（1GB/2GB 内存 VPS）深度优化，提供免构建热更与预编译注入方案。

---

## ✨ 核心特性

| 模块 | 特性说明 |
| :--- | :--- |
| 📚 **笔记本与资料摄取** | 支持创建多个独立笔记本，上传并解析 PDF / TXT / MD 文档，多用户数据严格隔离。 |
| 🔍 **高精度向量检索** | 基于 `PostgreSQL + pgvector` 进行余弦相似度检索，支持来源过滤与元数据精准关联。 |
| 💬 **多会话与可信问答** | 下拉框便捷切换会话；流式输出带精准数字角标与折叠式**原文摘录/页码引用**。 |
| 📅 **智能甘特图与计划** | 从对话提炼结构化学习路径，支持在时间轴/流水线/任务列表查看进度，支持 **AI 自然语言交互调整** 与拖拽编辑。 |
| 🧮 **LaTeX 与 Markdown 增强** | 完美渲染行内 `$E=mc^2$` 与独立块 `$$\sum$$` KaTeX 公式，代码块配备语言徽章与**一键复制代码**。 |
| 🔔 **每日学习邮件提醒** | 可选每日上午 09:00 推送当日学习任务清单（仅对已完成邮箱验证的用户生效）。 |
| 🛡️ **企业级安全基线** | 具备 IDOR 越权强隔离、SSRF 防护（防 DNS Rebinding / 私网拦截）、Turnstile 人机验证、分布式限流、原子配额预留。 |

---

## 🏗️ 系统架构与安全体系

```mermaid
flowchart TB
    subgraph Client["用户端 (Web SPA)"]
        UI["React 19 + Vite + Tailwind CSS"]
        Theme["Kraft/Ink 纸墨护眼主题 (支持 KaTeX / 甘特图)"]
    end

    subgraph Gateway["接入与安全网关"]
        Traefik["Traefik / Nginx (HTTPS + CSP + 静态缓存)"]
        SecFilter["安全防护 (SSRF 校验 / Turnstile / 分布式限流)"]
    end

    subgraph Backend["后端核心服务 (FastAPI)"]
        Auth["认证授权 & HKDF 密钥派生"]
        RAG["RAG 引擎 (解析 / 分块 / 向量检索 / 引用白名单校验)"]
        PlanEngine["学习规划引擎 (难度判断 / 周期规划 / AI 调整)"]
        Usage["配额与预留系统 (Atomic Reservation)"]
    end

    subgraph Storage["数据与向量层"]
        PG[(PostgreSQL + pgvector)]
        DataVolume[(资料与嵌入索引卷)]
    end

    subgraph ModelLayer["模型服务接入层 (BYOK / Server)"]
        LLM["Chat Provider (OpenAI / DeepSeek / Qwen 等)"]
        Embed["Embedding Provider (Text-Embedding-3 / BAAI 等)"]
    end

    UI --> Traefik --> SecFilter --> Backend
    RAG --> PG
    PlanEngine --> PG
    Auth --> PG
    RAG --> ModelLayer
    PlanEngine --> ModelLayer
```

---

## 🚀 快速开始

### 方式一：远程一键安装（推荐，全自动部署）

无需预先克隆仓库，在 Linux 服务器终端直接运行：

```bash
bash <(curl -Ls https://raw.githubusercontent.com/au1bhi/NoteLLM/master/install.sh)
```

> **国内服务器加速**：
> ```bash
> bash <(curl -Ls https://codeload.github.com/au1bhi/NoteLLM/tar.gz/refs/heads/master | tar -xzO NoteLLM-master/install.sh)
> ```

脚本会自动检测系统内存、网络连通性、引导生成 `.env` 配置，并一键启动全套容器服务。

---

### 方式二：本地克隆与开发运行

```bash
# 1. 克隆仓库
git clone https://github.com/au1bhi/NoteLLM.git
cd NoteLLM

# 2. 交互式本地开发安装
bash install.sh --local

# 3. 启动开发热更模式
docker compose watch
```

* 本地前端访问地址：`http://localhost:5173`
* 本地后端 API 文档：`http://localhost:8000/docs`

---

## 💡 轻量服务器（VPS）低内存部署机制与 Release 指南

线上轻量服务器（如 1核 1GB / 2GB 内存 VPS）在直接执行前端 Vite/Webpack 编译或 Docker 构建时极易触发 **OOM（Out of Memory）导致卡死崩溃**。NoteLLM 针对该场景提供了业界最优的**免构建极速部署体系**：

```
┌─────────────────────────────────────────────────────────────┐
│ 本地 / CI 环境 (充足内存)                                     │
│   1. bun run build -> 生成 dist 产物                         │
│   2. tar -czf frontend-dist.tar.gz -C dist .                │
└──────────────────────────────┬──────────────────────────────┘
                               │
            ┌──────────────────┴──────────────────┐
            ▼ (开发者日常更新)                      ▼ (开源公开发布)
┌───────────────────────────────┐     ┌───────────────────────────────┐
│ SFTP / 数据卷直接注入           │     │ 发布 GitHub Release Tag       │
│ 直接解包到 Nginx volume 挂载点 │     │ 上传 frontend-dist-vX.Y.Z 资产 │
└───────────────┬───────────────┘     └───────────────┬───────────────┘
                │                                     │
                ▼                                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 线上轻量 VPS 服务器 (1GB/2GB 内存)                            │
│   ✔ 零构建消耗：直接使用纯 Nginx 提供静态资源                   │
│   ✔ 后端代码卷挂载：git pull 后 restart backend 秒级热更     │
└─────────────────────────────────────────────────────────────┘
```

### ❓ 我是否需要上传 GitHub Release？

* **场景 A：开发者日常自建部署 / 私有更新（无需上传 Release）**
  * 在本地运行 `bash scripts/build-frontend-dist.sh` 生成 `frontend-dist.tar.gz`；
  * 通过 SFTP 上传至服务器数据卷解压，后端代码 `git pull` 后直接 `docker compose restart backend`，**5 秒内完成免编译更新**。
* **场景 B：开源版本分发 / 给第三方用户使用（推荐上传 Release）**
  * 在 GitHub 发布正式版本 Release（如 `v0.1.0`）时，附带上传预构建包 `frontend-dist-v0.1.0.tar.gz` 及其 `.sha256`；
  * 其他用户在 1GB 内存 VPS 上运行 `install.sh` 时，脚本会自动从 GitHub Release 下载预编译包，**无需配置 Node/Bun 环境，零内存压力一键拉起**。

---

## 📊 实验与评测结果

系统内置了标准 RAG 评测集（包含 7 份合成资料与 34 个复杂学术问答）：

| 评测维度 | 评测指标 | 测试表现 |
| :--- | :--- | :---: |
| **检索精准度** | Top-5 召回率 (Recall@5) | **100.0%** |
| **引用可信度** | 自动引用来源匹配率 (Source Precision) | **97.1%** |
| **事实忠实度** | 人工逐题复核通过率 (Faithfulness) | **34 / 34 (100%)** |
| **响应时延** | 检索平均时延 / P95 | **339 ms / 894 ms** |
| **生成时延** | 问答生成平均时延 / P95 | **2904 ms / 5595 ms** |

*详细评测基准、合成语料与逐题人工复核报告参见 [评测说明文档](docs/evaluation/README.md) 与 [最新报告](docs/evaluation/latest-results.md)。*

---

## 📄 毕业设计与开源价值

* **学术价值**：围绕“大模型幻觉抑制”、“受控出处生成”、“动态学习计划转化”构建了完整的论文级工程闭环；
* **可复用性**：提供解耦的 Provider 接口，完全兼容市面上所有 OpenAI 格式的云端模型与本地 Ollama / vLLM 实例；
* **测试完备性**：包含 **275+ 单元与集成测试**，后端覆盖率达 **84%**，具备完整的 GitHub Actions CI 自动化质量门禁；
* **开箱即用**：自带基于 OKLCH 色域的纸墨（Kraft/Ink）护眼设计，无缝支持移动端/桌面端响应式交互。

---

## 🛠️ 技术栈

* **后端框架**：Python 3.12+ / 3.14 · FastAPI · SQLModel · Pydantic v2 · Alembic
* **向量检索**：PostgreSQL · pgvector · Cosine Similarity Index
* **前端架构**：React 19 · Vite · TypeScript · Tailwind CSS v4 · Radix UI · Lucide Icons
* **图表与排版**：KaTeX (LaTeX 公式) · 自定义 SVG 甘特图 · React-Markdown
* **运维与部署**：Docker · Docker Compose · Traefik · Nginx · Cloudflare Tunnel

---

## 📜 开源许可证

本项目基于 [MIT License](LICENSE) 协议开源。欢迎提交 Issue 与 Pull Request 共同改进！
