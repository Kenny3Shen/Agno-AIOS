# 在 FastAPI 进程内挂载 FastMCP

Agno AIOS 通过把集成 FastMCP ASGI app 挂载到主 FastAPI 服务的 `/mcp/` 来暴露 MCP 协议。我们选择这种方式而不是单独部署 MCP server，是为了让控制面、MCP token 存储、服务开关和内置工具共享同一套部署与配置生命周期；代价是 MCP runtime refresh 与 API 进程可用性绑定在一起。
