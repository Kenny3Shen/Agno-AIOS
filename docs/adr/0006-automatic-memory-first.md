# 用户记忆优先使用 Automatic Memory

Agno AIOS 第一阶段对安全运营助手使用 Agno Automatic Memory（`update_memory_on_run=True`），默认不启用 Agentic Memory（`enable_agentic_memory=True`）。这个选择遵循 Agno 面向生产环境的建议，让 memory 行为更可预测，并避免让对话 Agent 通过成本更高的嵌套 LLM 路径决定何时修改 memories。若 operator 需要显式 remember 或 forget workflow，后续可以在 AIOS permissions 后面引入明确的 memory management tools。

Chat Sessions 也会启用 Agno Session Summaries，但 summaries 是独立的 Session Summary 概念，不应在界面上当作 Memory 呈现。Fallback Agent path 参与同一套 user memory 和 session summary 行为，但仍省略 tools、Knowledge、Skills 和 MCP，避免降级执行时分叉用户上下文。

第一阶段 Memory 页面是 Agno user memories 的只读 observability view，提供 filtering、user grouping 和 growth signals；editing、deletion、pruning 和 optimization 延后，直到它们的 permission 与 audit 语义完成设计。

Memory 读取遵循现有 resource ownership model：普通用户只能看到自己的 `user_id` memories，admin 用户可以跨用户读取并按用户过滤。Growth signals 使用 Agno 生产建议作为默认值：memory 数量达到 50 条或以上的用户标记为需要 optimization review，达到 500 条或以上的用户标记为 abnormal growth risk；页面不自动 pruning。

Vue shell 应在现有 `memory` navigation 和 `/api/os/memory` 后端 seam 下使用专用 Memory view，而不是拉伸通用 AgentOS ledger。后端读取应优先使用 Agno `PostgresDb` memory interface，例如 `get_user_memories()` 和 `get_user_memory_stats()`；只有 Agno 没有暴露聚合信号时，才 fallback 到直接 SQL。
