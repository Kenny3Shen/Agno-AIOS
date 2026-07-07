# Agno Scheduler 是调度数据源

Agno AIOS 使用 Agno Scheduler 的 schedules 和 schedule runs 作为定时执行的事实来源。Scheduler 视图直接消费 AgentOS `/schedules` API，并在前端把 Agno 的 endpoint、cron、retry、timeout、timezone、trigger 和 run history 模型适配为当前 Vue 控制面需要的展示结构。

第一阶段的 schedule target 只支持 Agno agent、team 和 workflow run endpoints，重复规则只支持 Agno 标准五段式 `cron_expr`；旧自定义模型中的 interval 和 one-shot schedules 不保留。旧 AIOS `/api/os/scheduler*` facade 不保留，避免继续维护两套调度 API 和两套 endpoint 转换规则。

Agno Scheduler 和 AgentOS 调度能力在同一个 FastAPI app 内挂载执行；Vue 应用通过专用前端适配模块接收 operator 友好的 target type 和 target id，再生成标准 Agno endpoint，而不是让多个后端 wrapper 继续重复映射逻辑。

第一阶段的创建和编辑流程暴露 Agno 标准执行控制，包括 timezone、timeout、retry count 和 retry delay，但在界面上作为高级选项呈现，并提供保守默认值。Schedule payload 保持 JSON object，直接透传给 Agno `payload`，第一阶段不为不同 target 提供动态表单。

Scheduler 页面应优先呈现列表，再展示选中 schedule 的 detail 和 run history panel，而不是以创建表单加通用 ledger 为主。第一阶段操作覆盖 Agno Scheduler 核心生命周期：create、edit、enable、disable、trigger、delete 和 inspect schedule runs。

Scheduler 导航和请求改用 AgentOS scope 语义：前端导航检查 `schedules:read`，运行时 lifecycle 权限应由 AgentOS authorization/RBAC 负责。启用 AgentOS RBAC 前，不能重新引入 `/api/os/scheduler*` 作为兼容入口。Scheduler execution 通过 Agno 的 in-process poller 和 executor 运行，lock handling、retries、manual triggers 和 run history 都遵循 Agno Scheduler 语义。

因为旧自定义 scheduler table 没有需要保留的数据，实现应删除旧 `app.os_schedules` table 和相关自定义 scheduler code paths，而不是携带迁移层。这个决策用 Agno 模型替代当前自定义 `app.os_schedules` 加自定义定时执行语义，因为 Agno 已定义 AgentOS Scheduler 需要的 lifecycle interface 和 execution records。
