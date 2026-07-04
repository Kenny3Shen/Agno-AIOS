# 使用 PostgreSQL schemas 划分运行时领域

Agno AIOS 把应用数据、Agno 运行时数据、MCP 配置和知识库数据存放在同一个 PostgreSQL database 中，并通过 `app`、`agno`、`mcp`、`knowledge` schemas 分域。我们选择这种方式而不是拆成多个 database，是为了让本地部署、备份和跨视图查询保持简单，同时仍通过 schema 边界暴露数据归属；代价是这些领域的扩展和保留策略暂时共享同一个 PostgreSQL 运行单元。
