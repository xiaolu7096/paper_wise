# API Contract

后端实现后，从 FastAPI 导出 `openapi.json` 到本目录，并用它生成前端 TypeScript 类型。

`openapi.json` 是生成文件，不手工编辑，也不提交到版本控制。契约测试必须对照根目录 `接口规范.md` 检查端点、schema、状态码和错误结构。
