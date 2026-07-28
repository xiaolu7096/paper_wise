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
