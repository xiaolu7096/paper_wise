# Backend

FastAPI 后端骨架。业务代码尚未实现。

后续实现顺序必须遵循技术文档：文件与阅读、解析与问答、选择与笔记、速读卡片与收尾。所有 Pydantic schema 和路由行为必须以根目录 `接口规范.md` 为准。

依赖清单刻意不包含 FAISS、rank-bm25、MinerU 和 PyMuPDF4LLM。

向量检索依赖位于 `retrieval` extra；在实现计划 S5 开始前安装，S1-S4 不加载本地 embedding 模型。
