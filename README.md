# paperwise_v1.5

PaperWise v1.5 是面向中文用户的 AI 论文阅读辅助工作台。当前版本已完成核心功能优化、公开部署适配、域名解析与生产环境部署，可通过 HTTPS 域名为本人及少量受邀用户提供服务，同时保留本地开发模式。

> 本章节描述当前 v1.5 的最终状态，优先于下方保留的早期本地 MVP 说明。下方原有内容未删除，主要用于查阅项目初始结构、本地启动方式和历史设计边界。

## 当前能力

- PDF 论文上传、解析、按页阅读、页码跳转、缩放和全文索引。
- 基于 `multilingual-e5-small`、FTS5 与 RRF 的混合检索，支持中文问题检索英文论文。
- 带真实页码和原文摘录的论文问答；摘要、引言、方法、实验、结果和结论等章节问题会优先召回对应内容。
- 简体中文问答、文字解释、选区总结和追问，保留必要的专有名词、公式与技术术语。
- PDF 文字选区解释、页面区域截图解释，以及解释结果和普通笔记的保存与管理。
- 根据论文类型生成带来源引用的连续 Markdown 中文速读报告。
- 论文搜索、切换和删除；删除论文时同步清理其 PDF、索引、问答、速读、笔记及截图资产。
- 文本模型与视觉模型独立配置，兼容 OpenAI Chat Completions 接口。
- 登录、退出、首次管理员初始化、少量受邀用户和用户级资源隔离。
- 每个用户的模型 API Key 使用服务端主密钥加密保存。
- 独立使用指南页面：生产站点的 `/tutorial.html`。

## 最终部署形态

生产环境采用以下最小架构：

```text
Browser
   |
   | HTTPS
   v
Caddy
   |-- /        -> React 静态应用
   |-- /api/*   -> FastAPI
   |
   +-- 自动申请和续期 TLS 证书

FastAPI
   |-- SQLite + 本地 PDF/截图持久化
   |-- 进程内论文解析任务队列
   +-- 用户配置的文本模型与视觉模型
```

- Docker Compose 统一运行前端、Caddy 和 FastAPI。
- 前后端同域部署，浏览器通过 `/api` 访问后端，避免跨域 Cookie 和公网端口暴露。
- Caddy 根据 `PAPERWISE_SITE_ADDRESS` 提供域名访问和自动 HTTPS。
- 业务数据保存在宿主机 `data/`；embedding 模型、Caddy 证书与配置使用独立 volume。
- 当前部署定位为不超过 5 人的小范围受邀版本，继续使用 SQLite 和单进程任务队列。

生产域名、API Key、加密主密钥等配置仅存在于服务器 `.env`，不会提交到仓库。主应用、健康检查和使用指南的访问路径分别为：

```text
https://<生产域名>/
https://<生产域名>/api/health
https://<生产域名>/tutorial.html
```

## 生产部署

准备 Linux 服务器、Docker、Docker Compose、已解析到服务器的域名以及开放的 80/443 端口。复制并填写环境变量：

```bash
cp .env.example .env
```

公网部署至少需要配置：

```env
PAPERWISE_AUTH_ENABLED=true
PAPERWISE_FRONTEND_ORIGIN=https://你的域名
PAPERWISE_PUBLIC_HOST=你的域名
PAPERWISE_SESSION_COOKIE_SECURE=true
PAPERWISE_SITE_ADDRESS=你的域名
PAPERWISE_KEY_ENCRYPTION_KEY=你的Fernet主密钥
```

构建并启动：

```bash
docker compose up -d --build
curl https://你的域名/api/health
```

完整的首次管理员、模型缓存、备份恢复和故障处理说明见 `部署说明.md`。

## 数据与安全边界

- 公网模式必须启用登录鉴权、HTTPS 和安全 Cookie；后端仅由 Caddy 在容器网络中访问。
- 论文、任务、问答、速读、笔记、截图和模型配置均按用户隔离。
- 应用日志不得记录论文原文、用户问题、模型回答、密码或 API Key。
- 日常备份需要覆盖整个 `data/` 目录；不要使用 `docker compose down -v` 清除生产 volumes。
- 模型调用会将必要的论文片段或区域图片发送到用户配置的模型服务，使用者应自行确认对应服务的隐私政策。
- 当前版本不提供开放注册、密码找回、团队空间、共享论文库、公开分享链接、协作批注或计费能力。

---

# PaperWise v1.5

PaperWise 是一个本地优先的 AI 论文阅读辅助工作台。MVP 已实现 PDF 阅读、按页索引、带来源问答、文字与区域解释、笔记和自适应中文速读报告。

## 规范入口

- `项目说明文档.md`：产品目标和 MVP 边界。
- `技术文档-优化版.md`：架构、存储和实现顺序。
- `接口规范.md`：前后端接口的唯一行为规范。
- `实现计划.md`：逐步实现顺序、每步验证和退出条件。

发生冲突时，接口字段、状态码和错误码以 `接口规范.md` 为准；产品范围以 `项目说明文档.md` 为准。

## 目录

```text
backend/
  app/
    api/          FastAPI 路由、请求/响应 schema、统一错误映射
    core/         配置、日志、路径和进程级基础设施
    db/           SQLite 连接、migration 和持久化模型
    jobs/         单工 ingest 队列与任务恢复
    services/     论文、检索、模型、卡片、资产和 annotation 业务逻辑
  migrations/    SQLite migration 文件
  tests/
    unit/         纯函数和边界校验
    contract/     接口规范与 OpenAPI 契约测试
    integration/  SQLite、PDF 和完整服务组合测试

frontend/
  src/
    app/          应用壳和顶层状态
    api/          从 OpenAPI 生成的类型及薄 API client
    components/   无业务归属的通用组件
    features/     papers、reader、chat、cards、annotations、settings
  tests/
    unit/         组件和状态测试
    e2e/          完整用户流程及 PDF canvas 裁剪测试

contracts/        FastAPI 导出的 OpenAPI 文件；不得手工维护重复 schema
data/             本地运行数据，除占位文件外不进入版本控制
```

## 开发环境

- Python >= 3.11；当前验证版本 3.13.7。
- Node.js >= 20.19；当前验证版本 24.16.0。
- npm 当前验证版本 11.13.0；Windows PowerShell 使用 `npm.cmd`。

后端虚拟环境位于 `backend/.venv`。

## 本地启动

首次安装：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,retrieval]"
cd ..\frontend
npm.cmd install
```

分别打开两个 PowerShell：

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm.cmd run dev
```

浏览器打开 `http://127.0.0.1:5173`。后端默认只接受本机 Host，前端 Origin 默认为该地址。

## 验证

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check --no-cache app tests scripts

cd ..\frontend
npm.cmd run generate:api
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
npm.cmd run test:e2e
```

## 本地数据与隐私

- PDF、SQLite、索引和区域截图默认位于仓库 `data/`；可用 `PAPERWISE_DATA_DIR` 覆盖。
- 页面原文、问题、回答和模型密钥不得写入应用日志。
- 模型密钥来自环境变量或用户配置文件；设置状态接口不会返回密钥。用户配置文件包含明文密钥，应依赖本机账户权限保护。
- 问答和文字解释会把相应文本发送到用户配置的文本模型；区域解释会发送裁剪图片、附近文字和问题到视觉模型。
- 应用没有登录鉴权，仅适用于本机单用户运行，不应暴露到局域网或公网。
