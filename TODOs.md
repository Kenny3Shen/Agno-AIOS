# 下一步工作

## 已完成：HITL pause session_id 回退 + cancel runId 跟踪

- `run.paused` 缺 `session_id` 时回退 `request.session_id`（审批通知/深链一致）。
- 前端从任意带 `runId` 的 SSE 事件更新 `activeRunId`（重试后 cancel 仍可用）。
- 用户停止生成时 `clear-error`，避免残留 soft-error 横幅。

## 已完成：run.completed session_id 回退请求会话

- Agno 终态事件可能省略 `session_id` 时，用 `request.session_id` 填充 `run.completed` / `run.continued`，避免新会话 history 深链丢会话。

## 已完成：Chat 取消 404 静默 + network-error 清 retry + SSE 结束打断 backoff

- `cancelRun` 返回 404（已结束/竞态）不再 toast「服务端取消失败」。
- `network-error` 清空 `retry`，与其它终态一致。
- `_stream_agent_events` finally 中 `stream_cancel.set()`，SSE 断开时打断模型重试睡眠。

## 已完成：多选开启 HITL 被 Parallel 拦截时 Toast

- `updateSelectedSteps` 返回跳过数量（Strict Mode 安全预计算）。
- 多选确认/输入/复核开关走 `bulkHitlWithGuard`；跳过时 `multiSelectHitlSkipped` 提示。
- 终态 `run.completed` 同步清空 `retry`。

## 已完成：粘贴后聚焦选中节点 + 取消清理 retry 态

- Studio 粘贴/复制后 `focusEpoch++`；画布 fitView 优先框选当前选中（粘贴结果），无选中再 fit 全图。
- Chat `run.cancelled` / `run.failed` 清空 `retry`，避免停止后仍显示重试条元数据。

## 已完成：Chat 重试等待期可中断取消

- `_sleep_interruptible`：模型重试 backoff 按 100ms 切片，可被 `cancel_event` 打断。
- `cancel_run` 设置 per-run / per-user stream cancel；retry 睡眠中的 cancel 发出 `run.cancelled`。
- 前端 `consumeSse` 接受 `AbortSignal`，停止时 cancel reader，避免悬挂读。
- 清理 `pasteNodesIntoSelection` 重复 docstring。

## 已完成：Chat 重试可见性强化

- `formatRetryDetail`：展示 attempt/max，有 `delay_seconds` 时显示等待秒数，并附带简短提供商错误。
- 消息占位 / run strip / 列表底部 `chat-retrying` 条：重试中可点「停止」；样式 warning 色。
- 画布：HITL 节点拖入 Parallel 不再高亮非法 drop；连线 `isValidConnection` 同步拦截。

## 已完成：Studio 粘贴进容器 / 同级 + Parallel 内 HITL 防护

- `pasteNodesIntoSelection`：单选容器 → `defaultDropTarget` 默认槽；单选普通步骤 → `locateNode` + `insertAfterLocation` 同级插入；多选/无选中 → 根级追加。
- Parallel（含嵌套）粘贴 HITL 树时回退到根级，对齐 Agno「Parallel 内不可 HITL」。
- 抽取 `nodeTreeHasHitl` / `locateNode` / `isInsideParallel` / `insertAfterLocation`；`reparentNode` 复用 HITL 检测。
- 客户端校验 `hitl_in_parallel`；Inspector / 多选批量开启 HITL 在 Parallel 内禁用或跳过。
- 单测：粘贴进 condition/parallel、同级顺序、HITL 回退根级、校验码。

## 已完成：粘贴位置锚定 + layout nodeLabel 对齐

- `pasteClipboard`：有选中宿主时把新节点锚在宿主旁（容器 +220/+40），避免粘贴进嵌套后飞到旧坐标。
- `nodeLabel`：空 Agent 步不再回退 `targetId`；校验路径文案与默认画布名一致（Agent step / Parallel / …）。

## 已完成：HITL 粘贴分流提示

- `pasteNodesIntoSelection` 返回 `{ steps, divertedHitlCount }`。
- Studio 粘贴时若 Parallel 内 HITL 被改放到根级，Toast 提示数量。

## 已完成：拖入 Parallel 的 HITL 明确拦截提示

- `reparentNode` 返回 `{ steps, blocked }`（`cycle` / `hitl_in_parallel` / `invalid`）。
- 画布 reparent / 分支连线失败时 Toast，不再静默无反馈。
- 与粘贴/复制 HITL 分流提示一致，对齐 Agno Parallel 约束。

## 已完成：Chat 自动轻量后 Knowledge/Live 开关去高亮

- 上一轮 `leanMode` 时，即使偏好仍开，Knowledge / Live Search 开关不再显示 active，改用 muted + Tooltip 说明「偏好保留，下一轮有工具意图再生效」。
- 纯函数：`isLastTurnAutoLean` / `isKnowledgeToggleActive` / `isLiveSearchToggleActive`。

## 已完成：多选摘要抽取 + clone 深拷贝 + 单步指令标签

- `summarizeSelectedAgentSteps`：多选 Inspector 混合态可测纯函数。
- `cloneNodeDeep`：深拷贝 `skills` / `userInputSchema`，避免复制/粘贴共享数组。
- 单步 Inspector：步骤指令补 `instructionsLabel` 标签。
- Grok lean 冒烟：`input_tokens≈2064`（search/live 开启但有效挂载仍为 false）。

## 已完成：Chat 关工具时请求体不发 Knowledge / Live Search

- `streamMessage`：`enable_tools=false` 时强制 `search_knowledge=false`、`live_search=false`，避免 UI 偏好残留误导服务端。

## 已完成：Studio 多选批量 HITL 开关

- 多选 Inspector：批量 `requiresUserInput` / `requiresOutputReview`（与确认开关一致，支持 indeterminate）。
- 与执行器 / Skill / 指令批量编辑同一面板。

## 已完成：Studio 多选批量指令 + Chat 关工具清 Live Search

- 多选 Inspector：批量编辑 Agent `instructions`（不一致时提示覆盖）；输入用 burst undo（600ms）避免历史刷屏。
- Chat：关闭「工具/Skill」时清 `liveSearch` 状态与 localStorage，与禁用开关一致。

## 已完成：Chat 关工具时禁用 Knowledge / Live Search 开关

- `enableTools=false` 时禁用并取消高亮 Knowledge / Live Search 开关（与后端 lean 忽略一致）。
- Tooltip 提示需先打开「工具/Skill」。

## 已完成：Studio 多选批量 Skills + 画布 Skill 徽标

- 多选 Inspector：批量绑定 Skill（覆盖写；清空 = 全部不挂）；不一致时提示并显示空选择。
- 画布 Agent 节点展示 `Skill · N` 徽标；presentation patch / contentKey 感知 skills。
- 单测：`updateNodeInTree` bulk skills。

## 已完成：Studio 多选批量编辑 Agent 执行器/确认

- 多选 Inspector：对选中的 Agent 步骤批量设置 `targetId` 执行器与 `requiresConfirmation`。
- `useWorkflow.updateSelectedSteps` + undo 历史；控制流节点自动跳过。
- 文案：`multiSelectAgentHint` / `multiSelectAgentCount` / 无 Agent 提示。

## 已完成：Lean 跳过 Live Search + Studio 快捷键/双击聚焦

- Chat lean / tools-off：`live_search` 强制关闭（与 Knowledge 一致），全量工具面仍透传请求开关。
- Studio：快捷键忽略 Ant Design 可编辑宿主（Select/Picker/CEL 等），避免 Inspector 输入时误删节点。
- 双击画布节点：选中并聚焦 Inspector 名称字段；快捷键/调色板提示补充「双击聚焦配置」。
- 单测：lean/full live_search 转发；`isKeyboardTargetEditable`。

## 已完成：Chat 有效 Knowledge 挂载可见性 + 文案对齐

- `run.started` / 历史投影携带 **有效** `search_knowledge`（与 agent 实际挂载一致；lean/tools-off 为 false）。
- 消息条与顶栏：全量工具面且用户关闭知识库时显示「知识库未挂载」chip。
- lite prompt 与 `autoLeanHelp` / `toolsSkillsHelp` / `knowledgeSearchHelp` 说明 lean 轮次不挂 Knowledge。
- 单测：history 投影、chat reducer、normalizeMessages。

## 已完成：Chat 轻量轮次跳过 Knowledge 注入

- `_build_security_agent`：仅在 `tool_surface=True` 时挂载 Knowledge / `search_knowledge` 指令；lean / tools-off 忽略请求里的 `search_knowledge=true`，避免 trivial 轮次加载检索工具与说明。
- 全量工具面（MCP 或 Skills）仍按请求启用知识库与 `knowledge_filters`。
- 单测：lean 请求 knowledge 不调用 KB；全量 surface 请求时加载 KB。
- Grok 4.5 冒烟（search_knowledge true/false）：均 `lean_mode=true`，`input_tokens` ≈2100–2135（与关闭 knowledge 同量级，说明未挂检索工具面）。

## 已完成：Chat 轻量轮次跳过 datetime + 空会话 history

- `_build_security_agent`：`tool_surface=False` 时 `add_datetime_to_context=False`。
- 轻量 + 无 `session_id`：`add_history_to_context=False`、`num_history_runs=0`（新会话无历史可拉）。
- 轻量 + 已有 `session_id`：仍 `num_history_runs=2`、注入 history，便于续聊。
- 全量工具面不变：`num_history_runs=5` + datetime + history。
- 单测：空会话 lean / 续聊 lean / 全量 surface 分别锁定 history 与 datetime 开关。


## 已完成：Chat 轻量轮次跳过 Memory 上下文注入

- `_build_security_agent`：`tool_surface=False`（tools-off 或意图未挂 Skill）时 `add_memories_to_context=False`，`store_tool_messages=False`；仍可在 `memory_enabled` 时后台写入 memory。
- 保留 lite prompt + 关闭 session summaries；history/datetime 见「跳过 datetime + 空会话 history」。
- 单测：trivial `ping` / tools-off / 显式 `memory_enabled=True` 轻量路径均断言不注入 memories。


## 已完成：画布边标签 i18n + Skill 渐进工具名 + Grok lean 冒烟

- Studio 边标签：`next/then/else` 展示为 i18n（中文「下一步/成立/否则」）；拓扑逻辑仍用英文 raw label。
- Chat：`get_skill_instructions` / `get_skill_reference` / `get_skill_script` 走 `tools.*` 本地化（渐进加载 Skill 时 ThoughtChain 可读）。
- Grok 4.5 冒烟（本机）：
  - tools on + `ping` → `lean_mode=true`、`skill_names=[]`、内容 `pong`
  - tools off + `ping` → `enable_tools=false`、`lean_mode=false`、`skill_names=[]`、内容 `pong`
  - tools on +「列出可用的安全剧本」→ `skill_names=["playbook-skill"]`、挂载 playbook 工具


## 已完成：jsdom TextArea autoSize height:NaN 测试环境修复

- 根因：jsdom `getComputedStyle` 返回 `border-*-width: medium` 等非数值，`@rc-component/input` autoSize `parseFloat` → NaN → React 警告。
- `frontend/src/test/setup.ts`：代理 `getComputedStyle` 将布局关键指标规范为有限 px；`HTMLElement.scrollHeight` 为 textarea 提供稳定行高。
- 单测 `getComputedStyle.autosize.test.ts` 锁住 finite height；ChatPage 模型设置用例不再刷 `height: NaN`。
- 测试环境 stub `Notification` + 过滤残留 antdx 警告，Chat 套件 stderr 干净。


## 已完成：Chat 工具调用可读名 + 会话侧栏测试路由 mock

- `formatToolLabel` / `humanizeToolId`：内置 MCP（`basic_`/`hitl_`/`playbook_`）走 chat i18n `tools.*`，其它 id 去命名空间后 Title Case。
- ThoughtChain 工具标题使用本地化名称（如「模拟隔离资产」/「Simulate containment」）。
- Workflow Inspector 空步骤名 placeholder 优先显示当前执行器显示名。
- `ChatSidebar`/`ChatTaskPanel` 测试 mock `useRouter`，消除 RouterProvider 告警。
- Approvals 列表/标题对 MCP `tool_name` 复用 `formatToolLabel`（workflow.step:* 保持原样）。


## 已完成：Chat Skill 可读名 + 轻量说明 / Workflow 空步骤名提示

- Chat：`formatSkillLabel(s)` 把 `cve-intel-skill` 等目录 id 显示为 `CVE Intel`；消息条与顶栏 Skills Tooltip 使用友好名。
- Chat：`autoLeanHelp` 文案补充可触发意图的关键词示例（CVE/隔离/剧本等）。
- Workflow Inspector：Agent 步骤名为空时提示「运行日志将显示执行器显示名」；Skill 多选选项改为「描述 (短名)」。
- Chat：`--chat-sender-offset` 测量高度做 `Number.isFinite` 守卫，避免 jsdom/异常布局写出 `height: NaN`。


## 已完成：画布 Step 副标题映射 Executor 显示名

- `resolveNodeCanvasSubtitle`：Agent step 副标题优先用 executor catalog `name`（如「安全运营助手」），无匹配回退 `targetId`，空 ref 用 i18n `subtitleAgent`。
- `WorkflowCanvas` 通过 `executorNames` 注入目录；catalog 到达后仅 presentation patch，不触发全量 layout。
- 内容 patch 的默认节点标题与 `buildGraph` 对齐（`defaultName_*`，不再误用 raw subtitle）。
- 单测覆盖映射 / 回退 / 控制流副标题 / `executorNamesKey` 稳定序。



## 已完成：Run 时 Step 空名映射 Executor 显示名

- 编译 `validate_and_normalize_definition`：step `name` 为空 / 等于 id / 等于 ref 时，写入 catalog `name`（如「安全运营助手」），Run Log / HITL 不再裸露 `security-operations`。
- 前端 `toDefinition` 不再把 `targetId` 当作 name 序列化；显式空名交给后端解析。
- 保留用户自定义步骤名。

## 已完成：Executor 目录产品化 + Playbook 内容库

- 内置执行器目录扩展字段：`category` / `capabilities` / `recommended_for` / `role`（`security-operations` 运营 vs `safe-fallback` 轻量）。
- Studio Inspector：执行器下拉展示名称、说明与适用场景；选中后显示描述摘要。
- `playbook-skill`：补齐七类处置场景、标准作业流程、异常表与输出模板；`references/scenarios.md` 速查。
- Grok 冒烟：剧本列表意图 → `skill_names=["playbook-skill"]`，并 progressive 加载扩充后的 SKILL.md。


## 已完成：P1 角色预设（分析师 / 作者 / 审批 / 审计）

- `ROLE_SCOPES` 扩展：`analyst` / `author` / `approver` / `auditor`（保留 `admin`/`user`/`guest` 兼容）。
- `GET /api/auth/roles` 角色目录；`GET/PATCH /api/auth/admin/users` 管理端用户列表与角色赋值（审计 `auth.role_update`）。
- Settings「角色与用户」Tab（管理员）：下拉分配角色；superuser 不可直接降级。
- 前端 `UserRole` 类型扩展；RBAC 单测覆盖四类预设。


## 已完成：Chat tools-off 与自动轻量语义分离

- `is_lean_tool_surface` 仅表示「工具开启 + 意图未挂 Skill」的自动轻量；`enable_tools=false` 不再标 lean。
- `from_chat_args(enable_tools=False)` 固定 `skill_names=[]`，跳过意图推断。
- 历史投影与消息级 chip：`enable_tools` / `lean_mode` / `skill_names` 三分；消息条与顶栏区分「轻量（无工具）」与「本轮自动轻量」。
- Skills 列表 `scripts` Tag 走 i18n。
- Grok 4.5 冒烟：tools on `lean_mode=true`；tools off `lean_mode=false` + `enable_tools=false`。


## 已完成：Chat 历史重载保留 lean_mode / skill_names

- `get_session_messages_async` 从 run `metadata.tais_runtime` 投影 `lean_mode` 与 `skill_names`（null=全量、[]=轻量、列表=部分）。
- 前端 `normalizeMessages` 映射为 `leanMode` / `skillNames`，历史会话仍显示工具面 chip。


## 已完成：Approvals/Memory/MCP Schema/Workflow Handle 文案收口

- Approvals Drawer 标题、Memory 元数据标题、MCP Input/Output Schema 与调用结果、画布 Handle tooltip 走 i18n。

## 已完成：运维面 i18n 残差 + Chat 本轮 Skills 可见性

- Audit：筛选表单、列表卡标题、详情 Descriptions、元数据标题走 audit i18n（测试按 zh-CN）。
- MCP Drawer：`服务与组件` / 概览 / Schema 与字段标签 i18n。
- Skills Drawer：内容 Tab / 元数据 Tab i18n。
- Dashboard 时延图：`P50`/`P95`/纵轴 `ms` 走 dashboard i18n。
- Knowledge 入库 strategy 选项短标签 i18n。
- Chat：消息条与顶栏在 `skillNames.length > 0` 时展示「Skills · N」chip（Tooltip 列出名称）；`skillNames === null` 展示「全量 Skills」；`leanMode` 仍显示「本轮自动轻量」。

## 已完成：Workflow 运行历史/触发历史状态 i18n + Grok 自动轻量冒烟

- 运行历史 Tag：`historyStatus_*`（运行中/已完成/失败/已取消/已暂停）。
- Inspector 节点类型 Tag 走 `nodeType_*`。
- 触发历史：source（cron/webhook）与 status（success/error/…）i18n。
- Grok 4.5 冒烟：`enable_tools=true` + `ping` → `lean_mode=true`、`skill_names=[]`、`input_tokens≈2467`、内容 `pong`。

## 已完成：Workflow Run Log 事件类型 i18n + Chat 消息级自动轻量标记

- Run 日志 Tag 将 `workflow.*` / `step.*` / `parallel|condition|loop|router.*` 映射为 workflow 命名空间文案（未知类型仍显示原始 type）。
- Chat 助手消息元信息在 `leanMode` 时显示「本轮自动轻量」chip（与顶栏徽标一致）。

## 已完成：Workflow 默认路径文案 + Chat 轻量徽标与 token 本地化

- Router 未命名分支 handle 用 `defaultPathName` i18n；空路径空槽用 `slotAddPathDefault`。
- Chat 自动轻量徽标仅看**最近一条**助手消息；token 指标用 `Intl` 默认 locale + i18n。

## 已完成：Chat 自动轻量模式可见性（run.started lean_mode）

- `run.started` SSE 携带 `lean_mode` / `skill_names` / `enable_tools`，前端消息与顶栏「本轮自动轻量」徽标（Tooltip 说明意图过滤跳过 MCP/Skills）。
- `is_lean_tool_surface` 与 `should_connect_mcp` 对齐；单测覆盖 lean 判定与 reducer。

## 已完成：Workflow 画布运行态/节点类型 i18n + Knowledge 检索台文案

- Studio 节点：运行态 pill（运行中/成功/失败/暂停）与类型标签走 workflow i18n。
- Knowledge：检索试验台 Tab、检索类型、结果 Source/Chunk/Document、渲染模式选项 i18n；元数据 ID 标签。
- 相关 Knowledge 单测按 zh-CN 文案断言。

## 已完成：Chat 意图过滤 MCP 工具面 + Skills/Audit/Eval 表头 i18n

- trivial / 非安全句：`skill_names=[]` 时**不连接 MCP**，走 lite 提示词与短历史。
- 关键词 skill：只保留对应内置 MCP 前缀（`hitl_` / `playbook_`）+ 始终保留 `basic_`；外部 MCP 工具名保留。
- 通用安全句：仍全量 MCP + 全量 enabled skills。
- Skills / Audit / Evaluations 列表表头 i18n；Chat 工具开关帮助文案更新。

## 已完成：Chat 按意图挂载 Local Skills（对齐 Workflow skills[]）

- `infer_chat_skill_names`：闲聊/指令类消息不挂 Skill；CVE / 隔离封禁 / 剧本 / 内网关键词只挂对应 skill；其它安全运营句挂全部已启用 skill。
- `SecurityRunRequest.skill_names` 写入 runtime metadata，HITL resume 原样恢复；Eval 关闭意图过滤以保持稳定工具面。
- `_build_enabled_skills` 走 `resolve_enabled_skill_dirs`（enabled ∩ names）；MCP 仍随 `enable_tools` 全量连接。
- Chat 开关帮助文案与 `security_operations.md` 边界说明同步。

## 已完成：后端 workflow_ref 自引用拦截 + 表头/画布 i18n 收口

- `validate_and_normalize_definition(..., forbid_self_workflow_id=)`：update / publish / compile 拒绝指向当前工作流的 `workflow_ref`（嵌套深度与 condition 分支均覆盖）。
- 单测：`test_forbid_self_workflow_ref_*`；引用其它 id 仍允许。
- Settings / Memory / MCP / CVE 列表与详情表头走 i18n；Dashboard 运行量图轴/系列中文化。
- Studio 画布空态与节点副标题（嵌套/循环/并行）补齐 workflow 命名空间，去掉硬编码英文。

## 已完成：嵌套工作流禁止自引用 + Trace 会话名回退

- Studio 保存：`workflow_ref` 引用当前工作流自身时校验失败并聚焦嵌套选择器。
- Trace session 无 title/preview 时用 session_id，不再硬编码英文 `Session`。

## 已完成：Workflow 运行/发布/触发器错误 i18n + 空 CEL 校验

- `useWorkflow`：发布/运行/启用触发器的英文硬编码改为 workflow i18n。
- 保存校验：条件 `evaluatorCel`、路由 `selectorCel` 为空时报错，Inspector 聚焦。

## 已完成：工作流名称必填 + Chat 轻量徽标 + Dashboard 失败行打开 Studio

- Studio 保存：空名称校验 `empty_name`，名称输入框 error 状态。
- Chat 顶栏：关闭「工具/Skill」时显示「轻量（无工具）」徽标。
- Dashboard 最近失败：subject 为 workflow_id 时可点进 Studio（不拦截整行进 Trace）。

## 已完成：Trace 打开 Studio + user_input 校验 + Dashboard 文案

- Trace：session 投影 `workflowId`；列表标 `[WF]`；选中工作流会话时顶栏「打开工作流」→ Studio。
- Studio 保存：开启用户输入但无有效字段名时校验失败，并聚焦 Inspector。
- Dashboard 最近失败「未命名运行」走 i18n。

## 已完成：Workflow 空节点名保留 + Chat 轻量上下文 + [WF] 进 Studio

- `toDefinition`/`fromRecord` 不再把空控制流名写成 Parallel/Condition 等英文；画布仍用 `defaultName_*` i18n。
- Chat `enable_tools=false`：`num_history_runs=2`，关闭 session summaries（减少摘要模型与历史体积）。
- 最近对话 / `#/chat?session=` 对 workflow：有 `workflow_id` 时打开 Studio（`#/workflow?workflow_id=`），否则仍进 Trace。

## 已完成：Approvals HITL 表单类型化 + Studio schema 编辑器 + Chat 开关持久化

- Approvals `user_input`：按 `field_type`（str/text/number/bool）渲染 Input / TextArea / InputNumber / Switch；提交时 coerce 为 bool/number；取消时清空表单状态。
- `output_review`：编辑区下方 Markdown 预览。
- Studio：用户输入字段由 JSON 文本改为结构化编辑（增删字段、类型、必填、说明）。
- 后端 `user_input_schema` 校验归一化（type 别名、重名拒绝）。
- Chat：`enable_tools` / `search_knowledge` / `live_search` 写入 localStorage，刷新保留偏好。

## 已完成：Chat 工具/Skill 开关 + Workflow 校验 i18n

- Chat 请求新增 `enable_tools`（默认 true）；关闭时跳过 MCP 连接与 Local Skills，改用 `security_operations_lite.md`。
- 输入区开关「工具/Skill」与联网/知识库并列；runtime metadata 可 round-trip（HITL resume 保留）。
- Grok 4.5 `pong`：`enable_tools=true` ~4825 input_tokens；`false` ~**2689**（约 −44%）。
- Workflow `validateWorkflowDraft` 消息走 i18n（`validationEmpty*` / `validationMissing*`）；保存失败兜底 `validationFixBeforeSave`。

## 已完成：Chat 上下文瘦身（prompt 卫生 + 密钥不进模型）

- `security_operations.md`：去掉未安装 skill 路由与重复 SOP，改指向 progressive discovery（`get_skill_instructions`）；体量 ~2105→~1063 字符。
- Agent `role` 去掉冗余（description + prompt 已覆盖）；`add_dependencies_to_context=False`，飞书 Webhook **不再**注入每条 user 消息。
- `basic_send_feishu_notify`：`feishu_webhook_url` 可选，缺省读服务端配置；修复 `code == 0` 因 `or` 被当成 falsy 的成功判定 bug。
- 冒烟（xai-grok-4.5，`Reply with exactly: pong`，`search_knowledge=false`）：`input_tokens` ~5234 → **~4585**（仍含 Skills 摘要 + MCP 工具 schema + 模型侧开销）。
- 后续可继续：trivial turn 不挂 MCP/Skills、按意图绑定 skill（对齐 Workflow step skills）、MCP 工具表裁剪。


## 下一阶段（产品 P0，已对齐）

> 目标：把「安全模板 → 保存 → 发布 → Webhook/Cron → HITL → Trace/通知」做成 **10 分钟默认可走通路径**；并补齐 Workflow 与 Chat 的能力对齐（Step 级 Skill）。
>
> 原则：不扩新控制流节点类型；不换画布库；不回退 Memory/Trace legacy。

### 产品验收（总）

- 新用户（有 `workflows:write` + `run`）从空 Studio 出发，**不查文档** 可在 10 分钟内：
  1. 选用安全模板创建草稿并保存  
  2. 看懂 **草稿 vs 已发布**  
  3. Publish 后配置/复制 Webhook 或启用 Cron  
  4. 触发一次运行 → 如有 HITL 在 Approvals 处理 → 从 Studio/通知跳到 Trace  
- 值班路径：失败触发或待审批 **进通知中心**，不只埋在 Audit。

### 明确不做（本阶段）

- 新 DSL 节点类型 / 换 React Flow  
- 远程 Skill 市场、多租户计费  
- Dashboard 大重构（仅要求失败可发现，聚合下推可放 P1）  
- Parallel 内 HITL、全站 i18n 一次做完  

---

### PR-P0.1 主路径状态机（Draft / Published / 引导） ✅

**用户价值**：知道「线上跑的是哪一版」；空状态默认走模板。

| 项 | 说明 |
|----|------|
| Studio 顶栏 | 常驻：`draft vN` / `published vM @ time` / `未发布`；脏草稿徽标 ✅ |
| 未发布拦截 | Cron/Webhook 启用时 modal 引导 Publish/Save；`triggerEnableBlocked` + 文案 ✅ |
| 空状态 | 画布空态 CTA：**从模板开始**（IR triage 默认） ✅ |
| 模板动作 | 「载入草稿」+ **保存并打开**；未发布时 Publish 按钮高亮 ✅ |
| 验收 | 未 Publish 开 Cron → 明确错误；Publish 后顶栏版本变化；空画布 1 次点击进模板 |

**主要路径**：`WorkflowPage` / `useWorkflow` / `utils.fromRecord` / i18n

**完成要点**：
- `WorkflowState` 投影 `version` / `publishedVersion` / `publishedAt` / `hasPublished`
- 顶栏 Tag：草稿版本 + 发布状态（脏草稿徽标）
- 启用 webhook/cron：未发布 / 脏草稿 → warning modal，不直接打开
- 空画布 CTA → `startFromTemplate('ir-triage')`

---

### PR-P0.2 触发器运维可读（Webhook / Cron） ✅

**用户价值**：触发器像「服务」而不是「隐藏配置」。

| 项 | 说明 |
|----|------|
| Webhook | Studio 完整 URL、secret 复制/轮换、`curl -N` SSE 示例 ✅ |
| Cron | `last_run_at` + 服务端 `next_cron_at`；启用前发布校验（P0.1） ✅ |
| 历史 | 触发历史 + 失败徽标 + Trace 深链 ✅ |
| 通知 | webhook/cron 终态 `error` → owner（+admins）通知 + Trace path ✅ |
| 验收 | 复制 curl 可触发已发布流；失败后通知可见；Cron 卡片能回答「上次/下次」 |

**主要路径**：`workflow_cron` / `routes/workflows` webhook / `WorkflowPage` Definition / `notification_service`

**完成要点**：
- `next_cron_timestamp` + payload `next_cron_at`
- `notify_workflow_trigger_failure`（cron/webhook finally）
- Definition 面板：URL / secret 轮换 / curl / last·next cron

---

### PR-P0.3 Step 级 Skill 绑定（Chat/Workflow 对齐） ✅

**用户价值**：编排步骤可用与 Chat 相同的安全 Skill，模板可声明依赖。

| 项 | 说明 |
|----|------|
| DSL | Step：`skills?: string[]`；默认省略/空 = 不挂 skill ✅ |
| 编译/运行 | **Step 级**：Agent `skills=` = `resolve_enabled_skill_dirs(bound)`（启用 ∩ 绑定）✅ |
| Chat（最小） | 仍全局 `get_enabled_skill_dirs()`；本 PR 不改 session 覆盖 ✅ |
| Studio | Step Inspector 多选已启用 Skill；IR/fan-out 模板带推荐 skills ✅ |
| 审计 | `skill.load`：workflow_id / run_id / skill_names / loaded_skill_names ✅ |
| 验收 | 绑定后 Agent 可加载 skill；未绑定 steps `skills=None`；审计可见 |

**主要路径**：`workflow_compiler` / `workflow_run_runtime` / `skill_service` / Inspector / templates

**语义**：
- 未声明或 `[]` → 该 step 不加载任何 skill（与 Chat 全局启用不同）
- 声明 `["playbook-skill"]` → 仅当全局 enabled 时加载
- run 级并集仅用于审计 `skill.load`；实际挂载按 step 独立编译

---

### PR-P0.4 审批值班入口（薄） ✅

**用户价值**：HITL 从「列表功能」变成「待办」。

| 项 | 说明 |
|----|------|
| Approvals | Segmented：**工作流 HITL** / 上传 / Chat HITL / 全部；默认 **pending + 工作流** ✅ |
| 通知 | `notify_workflow_hitl_pending` → admins，path=`/approvals?approval_id=` ✅ |
| Studio | paused CTA「打开审批」保留；通知中心同深链 ✅ |
| 验收 | 暂停 run → 通知 → 打开表单 → 批准后 continue；列表可只看 workflow |

**主要路径**：`ApprovalsPage` / `getApprovals(kind)` / `notification_service` / `workflow_run_runtime`

---

### 建议实施顺序

```
P0.1 状态机 + 空态引导     ✅
P0.2 触发器运维 + 失败通知 ✅
P0.3 Step Skill 绑定       ✅
P0.4 审批值班薄入口        ✅
```

### P1（本阶段后，不阻塞 P0）

- Dashboard 聚合下推 / 可信失败列表  
- ~~Playbook 内容库扩充 + Executor 目录产品化~~ ✅（见上）  
- ~~角色预设（分析师 / 作者 / 审批 / 审计）~~ ✅  
- Skill 版本与「被引用」只读视图  
- i18n 与静默失败显性化（模型/Memory 后台错误）

---


## 已完成：画布默认节点名/副标题 i18n

- 控制流节点默认 `name` 置空，画布显示走 `defaultName_*`。
- 副标题：分支数/最大迭代/未配置 agent/嵌套 等用 i18n。

## 已完成：画布空槽/分支/工具栏 i18n + Grok 4.5 Chat 冒烟

- 空容器 CTA（添加分支/循环体/成立/否则/路径）与分支把手、节点工具栏、HITL 徽标接入 workflow i18n。
- 本机 `xai-grok-4.5`：`POST /api/chat` SSE `run.started → content.delta(pong) → run.completed` 通过。

## 已完成：Workflow/Chat 失败兜底文案 i18n

- `useWorkflow` 保存/发布/恢复/运行失败兜底文案走 i18n。
- Chat `network-error` 兜底文案走 i18n。

## 已完成：Approvals 详情/列表 i18n + Studio 运行态值班横幅

- Approvals：表格列、详情分区/字段标签、状态文案、Raw/Markdown 视图标签接入 i18n。
- Studio：运行中/暂停/失败/取消时顶栏横幅 + Trace / 审批 / 运行记录快捷入口。

## 已完成：工作流会话从最近对话进 Trace + Approvals 类型 i18n

- Session 投影 `workflow_id`/`agent_id`/`team_id`；历史 user 输入复用更宽的 preview 解析。
- 最近对话点击 `session_type=workflow` → Trace（`session_id`），不再误开空 Chat 转录。
- 直接打开 `/chat?session=` 若为 workflow：replace 到 Trace；并跳过 history 请求。
- Approvals 类型/标题/Workflow ID 标签接入 i18n；HITL notify 失败改 `logger.exception`。

## 已完成：Chat 最近对话 [WF] + 错误横幅 Trace + 预览/类型投影

- Session 列表投影 `session_type`；工作流空预览默认「工作流运行」；输入兼容 content/input_content。
- 最近对话对 workflow 前缀 `[WF]`（已带前缀不重复）。
- Chat 错误横幅：可打开 Trace；`lastAssistant` 取最近助手消息。
- Studio 多选「取消选择」改为图标按钮。

## 已完成：Trace 树与筛选更多 i18n

- Run/Span 树标签、状态筛选、Duration/Started 等接入 trace 命名空间。
- 单测按 zh-CN 文案匹配 Sessions/Runs/Detail/Run 根。

## 已完成：Trace/Dashboard 口径 i18n + Studio 取消选择 + Memory 回退日志

- Trace：状态筛选截断提示与 Sessions/Runs/Detail 等硬编码文案接入 i18n。
- Dashboard：Token KPI 增加「有界样本」Tooltip。
- Studio 多选：Inspector 提供「取消选择」+ 批量删除。
- Memory 状态 GROUP BY 失败：`logger.debug(..., exc_info=True)` 再回退 per-user stats。

## 已完成：Workflow 空库 CTA

- 库 Select 无结果且非搜索态时，提供「从 IR 分诊模板开始」链接，与画布空态引导一致。

## 已完成：Chat 消息打开 Trace

- 助手消息操作栏：有 `run_id`/`session_id` 时增加「打开 Trace」，深链与 Dashboard 一致（`session_id`/`run_id`/`selected_session`/`trace`）。
- 复制 Run ID 仍保留；操作栏 gap 略增并允许换行，降低图标拥挤。
- 暂停（HITL）消息不展示「重新生成」，避免绕过审批重跑。

## 已完成：Chat context bar 审批入口 + 多选 Inspector 收敛

- Chat 顶栏暂停态：与消息体一致的「打开审批」深链（`#/approvals?approval_id=`）；paused status-dot。
- Studio 多选：Inspector 仅展示批量删除提示，隐藏单节点编辑表单（避免误改最后选中节点）。
- `runStatus.test.ts`：去掉 `as never`，状态 map 使用 `WorkflowNodeRunStatus`。

## 已完成：Chat HITL 打开审批 + Memory 状态批量查询

- Chat 暂停态消息：`approval_id` 时提供「打开审批」深链。
- Memory 列表成长徽章：多用户页优先单次 GROUP BY；否则按页用户并行 `get_user_memory_stats`（不再盲扫 limit=500）。

## 已完成：Skill 引用截断提示

- `list_skill_workflow_references` 返回 `{data, truncated}`；候选或结果触顶时 `meta.truncated`。
- Skills Drawer「被引用」在截断时提示「仅显示部分结果」。

## 已完成：多选批量删除 / 加载 fitView / 会话搜索限长 / 重命名缓存

- Studio 多选：Inspector 批量删除按钮 + 提示（编辑仍针对最后选中节点）。
- 加载/模板应用：`focusEpoch` 触发画布 `fitView`。
- Chat 会话 `q`：`runs` 文本 `left(..., 4000)` 再 ILIKE，降低大 JSON 扫描成本。
- 重命名会话：`setQueriesData(sessionLists)` 覆盖含搜索 q 的 infinite query 缓存。

## 已完成：Chat 搜索 debounce 闪烁修复 + 多选计数

- 最近对话：仅在 `sessionSearch` 与 debounced 一致时做本地二次过滤，避免输入过程中列表被滤空。
- Studio Inspector：多选时显示「已选 N 个」。

## 已完成：Skill 引用 SQL 预筛 + 深链修复 + Studio 快捷键提示

- Skill 引用：`definition` 文本 ILIKE 预筛候选，再 DSL 树确认真实 `skills` 绑定（去掉全库分页扫）。
- Skill「打开」深链改为 `#/workflow?workflow_id=`（原先误写 workflows）。
- Studio 工具栏快捷键 Tooltip；Chat 新建会话清空搜索词。

## 已完成：Chat 预览搜索 / Escape 取消选择 / soft-error 自动关闭 / Skill 被引用

- Chat `q`：SQL 额外匹配 `runs` JSON 文本（预览输入）；占位文案同步。
- Workflow 画布：`Escape` 清空多选/选中。
- Chat soft-error（非 run failed）：8s 自动 `clear-error`；失败 run 横幅仍需手动关闭/重试。
- Skill 详情「被引用」：`GET /api/skills/{name}/references` 扫描可见工作流 definition 的 step skills；Drawer 表格 + 深链 Studio。

## 已完成：搜索截断提示 + Memory 后台失败跳转

- Workflow 库在搜索态不再显示「列表截断」Alert（总数相对当前 q 分页，避免误导）。
- `notify_background_task_failure`：task 名含 memory/memories 时通知 path=`/memory`、标题 Memory task failed。

## 已完成：Chat/Workflow 搜索空态与加载反馈

- 最近对话：无匹配时仍保留搜索框；`isFetching` 时 Search loading；`keepPreviousData` 避免切 q 闪空白。
- 区分「无对话」与「搜索无结果」空态。
- Workflow 库 Select：`notFoundContent` 区分搜索中 / 无匹配 / 库空；列表 query 同样 `keepPreviousData`。

## 已完成：Chat / Workflow 库服务端搜索

- `GET /api/chat/sessions?q=`：SQL 匹配 `session_id` 与 `metadata.agno_aios_title`；前端最近对话搜索 debounce 后走服务端分页，命中组自动展开。
- `GET /api/workflows?q=`：name / description / id ILIKE；Studio 库 Select 受控搜索 + infinite query 按 q 分页（不再只滤已加载页）。

## 已完成：Chat 错误横幅可关闭且仅失败可重试 / Dashboard 失败口径说明

- Chat soft-error：关闭按钮；仅当最后一条助手消息 failed/retryable 时显示 Retry（cancel soft-error 不再误导重试）。
- Dashboard 失败率 KPI：展示原生 ERROR 失败次数 + Tooltip 口径；最近失败表 extra 标明 ERROR + chat-audit 有界补充。

## 已完成：Workflow 校验→Inspector 聚焦 + Run 自动展开 / Chat soft-error 关闭

- Workflow 保存校验失败或点击 issue：右侧 Inspector 滚入视口，按 issue code 聚焦 executor / workflow_ref / children / name 字段。
- Run 面板改为受控 `activeKey`；`running` 时自动展开 Run 日志（折叠后重新运行仍可见）。
- Chat soft-error / 横幅错误：可关闭（`clear-error`），不必点 Retry 或等下次 start。
- `fieldForValidationIssue` 映射 + 单测；Chat reducer 单测。

## 已完成：Workflow 库无限分页 + Chat「回到最新」布局

- Workflow 库：`useInfiniteQuery` 按页拉列表，侧栏「加载更多」；截断 Alert 仅在无法继续翻页时显示。
- Chat「回到最新」：水平居中，并用 ResizeObserver 按输入区高度设置 `--chat-sender-offset`，避免挡住 Sender。

## 已完成：Chat 流式粘底去抖 + Workflow 库搜索 / Run 日志滚动

- Chat：流式期间 `scrollTo` 使用 `auto`（非 smooth），增大贴底阈值，减少 delta 抖动；「回到最新」仍 smooth。
- Workflow 库 Select：`showSearch` 按名称/ID 过滤；Run 日志列表限高并在运行时自动滚到底。

## 已完成：Workflow 校验聚焦节点 + Chat 会话搜索

- 保存校验失败：自动 `fitView` 到无效节点；重复保存用 `validationEpoch` 重新聚焦；列表点击节点同样居中。
- Chat 最近对话：标题/ID 本地搜索（`filterConversationItems`），无匹配空态。

## 已完成：Workflow 加载态 + Run 输出 Markdown / Chat 停止反馈

- Workflow：`loading` 状态（深链/库外 ID 拉取）；Studio 顶栏与库 Select 显示加载；Run 面板展示最新输出 Markdown，完成事件 content 就地渲染。
- Chat：停止原因 i18n（`stoppedGenerating`）；服务端 cancel 失败用 `soft-error` 横幅提示，不把消息标成 failed。

## 已完成：抽取 ``batch_traces_by_run_ids`` 公共查找

- 新增 `api/services/trace_lookup_service.py`：按 run_id 批量查最新 trace 行（DISTINCT ON）。
- Trace ERROR 补充与 Overview recent_failures 共用，去掉 overview → tracing_service 私有导入。
- 单测覆盖空 ID / 缺表 / 批量映射。

## 已完成：Dashboard recent_failures 合并 chat-audit ERROR

- `_fetch_recent_failures`：原生 `status=ERROR` + 近期 chat audit 失败 run 批量补 trace（有界），避免「审计终态失败不在 ERROR 列表」。
- 单测覆盖 audit-only 补充行仍带 `run_id`/`session_id` 供深链。

## 已完成：Workflow 列表 meta 与深链按 ID 加载

- `listWorkflows` 返回 `{data, meta}`（默认 limit=100，API 硬顶 100），Studio 在 `total_count > 当前页` 时 Alert。
- 深链 `workflow_id`：列表未命中时 `getWorkflow(id)` 拉取，避免「列表截断导致无法打开」。
- `listWorkflowVersions` 默认 limit 提到 100（后端 le=100）。
- Approvals `getApprovals` 去掉中间 `fetch*Page` 薄包装，upload/HITL/combined 直接 `normalizePaginatedList`。

## 已完成：Trace 列表 meta 类型别名共享 normalizer

- `TraceListMeta` / `TraceList` / `TraceSessionList` 对齐 `ListPaginationMeta`；Native 别名指向 UI 形状。
- `listTraces` / `listTraceSessions` 直接 `normalizePaginatedList(..., extras: true)`，去掉薄包装。

## 已完成：后端 PaginationMeta 共享 + Knowledge 列表 normalize

- `api/utils/pagination.PaginationMeta` TypedDict；Memory/Approvals 去掉重复 meta TypedDict。
- Knowledge `getKnowledge` 经 `normalizePaginatedList` 投影 Document，并保留 `status` 与 query/sort meta 扩展。
- 前端 `KnowledgeListMeta` 基于 `ListPaginationMeta`。

## 已完成：Catalog 列表与 meta 类型对齐共享 normalizer

- Chat / Memory / Approvals 的 `*ListMeta` 改为 `ListPaginationMeta` 别名。
- Workflow `listExecutors` / `listWorkflowVersions` / `listWorkflowTemplates` 走 `normalizePaginatedList`。
- Skills / MCP components·tokens / Eval suites·cases catalog 列表同样收口（仍返回数组给现有 UI）。

## 已完成：Workflow / Audit / Eval failures 列表 normalizer 收口

- `listWorkflows` 经 `normalizePaginatedList` + `normalizeWorkflow`（调用方仍要 `WorkflowRecord[]`）。
- Audit `getAuditLogs` 归一化 data/meta，丢弃畸形行；`AuditLogResponse.meta` 对齐 `ListPaginationMeta`。
- Eval `listFailures` 与 `EvalListMeta` 复用共享分页类型。

## 已完成：共享列表 normalizer 扩面（CVE / 通知 / Collect / Approvals / Knowledge）

- `normalizePaginatedList` extras 支持 `unread_count`（通知角标 meta）。
- 接入：CVE search、Notifications、Collect articles/sources、Approvals HITL/submissions/combined、Knowledge search 解析。
- AppFrame SSE 写入通知缓存时补齐 `search_time_ms`，满足 `ListPaginationMeta`。
- 相关单测 121 绿。

## 已完成：前端共享 ``normalizePaginatedList``

- 新增 `frontend/src/shared/lib/pagination.ts`：`normalizePaginatedList` / `listPaginationMeta`。
- Memory / Chat sessions / Eval runs / Trace lists / Approvals listMeta / Workflow trigger history 复用，去掉各 feature 内重复 meta 推导。
- 单测覆盖映射丢弃行、total_pages 推导、truncated extras。

## 已完成：listSessions 选项对象 API

- `listSessions(options)` 替代位置参数（`includeArchived` / `archivedOnly` / `page` / `limit` / `userId`）。
- Chat infinite query、Trace 归档窗与单测同步；去掉易错的五参数调用。

## 已完成：Approvals 前端去 offset-slice 死代码 + Workflow version 类型收窄

- `getApprovals`：upload/HITL 单页直调 page/limit；删除 `fetch*Slice` 虚拟 merge 残留。
- Workflow `listWorkflowVersions`：去掉 `as never`，用与 `normalizeWorkflow` 一致的 definition 投影。

## 已完成：Approvals kind=all 服务端合并分页

- `GET /api/approvals?combined=true`：upload submissions 优先，再 HITL；offset 真分页 + `data`/`meta`。
- 前端 `getApprovals({ kind: 'all' })` 改为单请求 `combined=true`，去掉客户端双源虚拟 merge。
- 单测：后端 uploads→HITL 顺序；前端 combined query 契约。

## 已完成：Chat sessions ``archived_only`` + Trace 归档窗

- `GET /api/chat/sessions?archived_only=true`：SQL 只返回 `metadata @> {agno_aios_archived:true}`。
- Trace 归档/活跃 Tab：单次有界 chat 窗口（`archived_only` 或默认排除归档）替代无限翻页 walk；窗口截断时 Alert。
- 列表合并仍以 Trace summaries 为主，chat 提供归档标记与标题。

## 已完成：Auth SSO / 通知中心 / Knowledge 检索失败显性化

- Auth：加载 SSO 提供方、启动 OAuth 失败 toast（`ssoLoadFailed` / `ssoStartFailed`）。
- Shell 通知：标已读 / 全部已读 / 删除 / 退出登录失败 toast；标已读失败仍继续深链导航。
- Knowledge Retrieval playground：搜索失败 `searchFailed` toast。

## 已完成：MCP 签发令牌 / 连接测试失败显性化

- 签发 Token 表单 `onFinish`：try/catch + `issueTokenFailed`。
- 添加 Server「连接测试」：try/catch + `testConnectionFailed`（表单校验失败不 toast）。

## 已完成：Memory 编辑 / Evaluations 运行失败显性化

- Memory 编辑表单 `onFinish`：try/catch + `updateFailed` toast（原先成功才提示）。
- Evaluations：run suite / run case / replay 提交失败 `message.error`（`suiteFailed` / `evalFailed` / `replayFailed`）。
- 补齐 `App.useApp()` message 与 i18n 键。

## 已完成：关键 mutation 失败显性化

- Approvals `resolve`：`onError` toast（`resolveFailed`），与 resume 失败路径对称。
- Memory 删除、CVE 搜索/库更新：失败时 `message.error`，不再静默。
- 单测：Approvals resolve 5xx 时展示错误文案。

## 已完成：Workflow pause → Approvals resolve 闭环 e2e

- `frontend/e2e/workflow.smoke.spec.ts`：Studio Run SSE 收到 `workflow.paused`（含 `approval_id`）→ 「打开审批」深链 → Drawer 批准 → `POST /api/approvals/{id}/resolve`。
- 覆盖跨页值班主路径（Studio CTA → Approvals），与既有 resolve smoke 互补。

## 已完成：Approvals resolve 严格归一化 + Dashboard 失败深链 e2e

- `resolveApproval` / `resumeApproval` / `resolveSubmissionApproval`：去掉 `normalize ?? (row as Approval)` 强制断言；无效载荷直接抛错。
- 单测覆盖成功归一化、缺 id 抛错、resume / submission resolve。
- Playwright `dashboard.smoke.spec.ts`：运行概览「最近失败」点击 → Trace 规范 query（`session_id`/`run_id`/`selected_session`/`trace`）并打开对应 Run/Span 详情。

## 已完成：静默异常可观测 + 死 CSS 清理

- `workflow_service._row_payload`：`next_cron_at` 计算失败改 `logger.debug(..., exc_info=True)`。
- `settings.run_model_connectivity_test`：连通性失败 `logger.warning`（仍返回 success=false 给前端）。
- 删除废弃 `.ant-list-sm` 与旧 Collect List 项样式（已改为 button 列表）。

## 已完成：去掉 antd 废弃 List（Workflow / Collect）

- Studio 运行历史 / 运行记录 / 触发历史：`List` → 轻量 `div` 列表 + CSS。
- Collect 文库列表：`List` → button 行 + `Pagination`。
- 消除 Playwright/Vite 中 `[antd: List] deprecated` 警告。

## 已完成：Workflow run SSE Playwright smoke

- `frontend/e2e/workflow.smoke.spec.ts`：深链加载后填写输入 → 点运行 → mock SSE（`workflow.started` / `step.completed` / `workflow.completed`）→ 运行记录出现 step/terminal 事件。
- 与既有 `workflow_id` 深链 smoke 并列。

## 已完成：Approvals resolve Playwright smoke

- `frontend/e2e/approvals.smoke.spec.ts`：Drawer 中对 confirmation HITL 点「批准」→ `POST /api/approvals/{id}/resolve`。
- 与既有 on-call 列表 + `approval_id` 深链 smoke 并列。

## 已完成：Trace sessions 真分页（去客户端多页 walk）

- `listTraceSessions`：去掉 200×5 客户端翻页 walk，单次透传 `page`/`limit`。
- `TracePage`：默认用服务端 `page` + `total_count` 分页；归档筛选仍有界拉 200 后本地过滤。
- unit/api/Playwright smoke 同步。

## 已完成：Trace 前端列表 data/meta 收口

- `listTraces` / `listTraceSessions` 归一化结果 `items`+扁平字段 → `{data, meta}`（含 `truncated`/`scanned_count`）。
- `TracePage` / unit / Playwright smoke 同步；无旧 `items` 兼容。

## 已完成：Memory / Eval runs 前端列表 data/meta 收口

- `getMemories`：`items`/`total`/`page`/`limit` → `{data, meta}`；`MemoryPage` 同步。
- `listRuns`（agno-runs）：同上；`EvaluationsPage` Runs 表同步。
- 无旧 `items`/`total` 兼容；补 `getMemories` envelope 单测。

## 已完成：Approvals 前端列表 data/meta 收口

- `getApprovals` 返回值 `items`/`total`/`page`/`limit` → `{data, meta}`（`total_count`/`total_pages`/`search_time_ms`）。
- `ApprovalsPage` / unit tests 同步；虚拟 merge（upload+HITL）逻辑不变。
- 无旧 `items`/`total` 兼容。

## 已完成：Eval suite 单 case 异常可观测

- `agent_eval_runner.run_suite`：单 case 抛错时 `logger.exception` 后计入 `errored` 并继续跑后续 case。
- 单测覆盖 exception → errored 计数。

## 已完成：Workflow trigger history meta + Chat cancel 可观测

- `GET /api/workflows/{id}/triggers/history`：`meta.total` → 标准 `pagination_meta`（`total_count`/`total_pages`/`search_time_ms`）。
- 前端 `listWorkflowTriggerHistory` 同步；无 `meta.total` 兼容。
- Chat `useChat.cancel`：server cancel 失败时 `console.warn`（客户端 SSE 仍先 abort）。

## 已完成：Knowledge search / Eval failures data/meta + Chat cancel e2e

- `POST /api/knowledge/search`：`{results}` → `{data, meta}`（`pagination_meta`，total=本批命中数）。
- `GET /api/agent-evals/failures`：裸数组 → `{data, meta}`；前端 `listFailures` 只解 `data`。
- `frontend/e2e/chat.smoke.spec.ts`：发送 → 挂起 SSE →「停止生成」→ `POST /api/chat/runs/{id}/cancel`。
- 无旧 envelope 兼容；全量 Playwright smoke 10 条绿。

## 已完成：Eval suites/cases + MCP components/tokens data/meta

- Agent Eval 定义列表 `list_suites` / `list_cases` 改为 `{data, meta}`；runner 读 `data`。
- MCP `GET /components` 与 `GET /tokens` 改为 `{data, meta}`；前端 list helpers 解包。
- 无旧裸数组兼容。

## 已完成：Skills / Notifications 列表 data/meta

- `GET /api/skills`：`{skills}` → `{data, meta}`（全量列表，meta.total_count=len）。
- `GET /api/notifications`：`{notifications, unread_count}` → `{data, meta}`，`meta.unread_count` 为全量未读。
- 前端 Skills/Notifications/AppFrame/e2e fixtures 同步；无旧 envelope 兼容。

## 已完成：CVE update 去 status 包装 + Workflow 深链 smoke

- `POST /api/cve/update` 成功体去掉 `status: 200`（失败仍 HTTPException）。
- `frontend/e2e/workflow.smoke.spec.ts`：`workflow_id` 深链加载已保存工作流名称与步骤节点。

## 已完成：Knowledge 列表 data/meta + Collect 错误收口

- `GET /api/knowledge`：`documents`/`pagination` → `data`/`meta`（`pagination_meta`，保留 query/sort 于 meta）；`status` 仍为 RAG/健康快照旁路字段。
- Collect：`GET articles/{id}` 直接返回行或 404；`crawl`/`parse` 失败改 `HTTPException`，成功体去掉包一层 `status`。
- 前端 Knowledge/Collect 与 e2e mock 同步；无旧 envelope 兼容。

## 已完成：CVE / Collect 列表 data/meta 对齐

- `POST /api/cve/search`、`POST /api/url2md/articles/search`、`GET /api/url2md/sources` 改为 `{data, meta}`；错误改 HTTPException（不再 `{status:400,message}` 包一层）。
- 前端 CVE/Collect 页与 api 类型同步；无旧 envelope 兼容。

## 已完成：Audit 列表 data/meta 对齐

- `GET /api/audit/logs` 从 `{items,total,page,limit}` 改为 Agno 风格 `{data, meta}`（`pagination_meta`）。
- 前端 `AuditLogResponse` / 页面 / 单测同步；无兼容旧 envelope。

## 已完成：antd Alert title + tracing 解析失败可观测

- Dashboard / Trace 残留 `Alert.message` → antd 6 `title`（全站 `Alert` 无 `message` prop）。
- `tracing_service`：JSON/时间解析失败改 `logger.debug`（取消静默 `pass`；`CancelledError` 仍忽略）。

## 已完成：model_factory 重试字段可观测 + Approvals on-call smoke

- `_retry_kwargs`：非法 `retries` / `delay_between_retries` 打 debug 并回退默认；非法 `http_max_retries` 打 warning 且不设置 `max_retries`（不再静默 `pass`）。
- Approvals 值班提示 `Alert`：`message` → antd 6 `title`。
- `frontend/e2e/approvals.smoke.spec.ts`：默认 pending + workflow HITL 列表；`approval_id` 深链打开 Drawer 与 `tool_args.message`。

## 已完成：Workflow 深链 deps + Knowledge 进度 smoke

- `useWorkflow.load` 改为 `useCallback`；Studio 深链 `workflow_id` effect 去掉 `eslint-disable`。
- `frontend/e2e/knowledge.smoke.spec.ts`：文本入库 `stream=true` SSE 完成后关 Drawer，列表出现文档（阶段 UI 由 unit test 覆盖）。

## 已完成：Playwright Trace Session→Run→Span smoke

- `frontend/e2e/trace.smoke.spec.ts`：深链 `selected_session` + `trace` 打开观测页，Session 选中、Runs/Spans 树与 Detail Input 可见；点 child span 切换详情。
- 忽略 legacy `session`/`run` query（输入框保持空）。
- `fixtures.mockApis` 支持 `handleApi` 覆盖特定 `/api/*` 响应。

## 已完成：Trace ERROR audit 补充批量查

- `_merge_audit_error_traces` 不再对每个 failed `run_id` 调 `get_trace`（N 次）。
- 新增 `_batch_traces_by_run_ids`：`run_id IN (...)` + `DISTINCT ON (run_id)` 一次取最新 trace 行。
- 失败打 `logger.exception`；列表仍只在 page=1 且有空位时补充。

## 已完成：oxlint 清零 + Trace list input 失败可观测

- `ChatPage.test`：`setSearchKnowledge` / `setLiveSearch` 补全 `vi.fn` 泛型，满足 `require-mock-type-parameters`。
- `TracePage`：session 预取 `useEffect` 解构 `hasNextPage`/`fetchNextPage` 等稳定字段，消除 exhaustive-deps 误报。
- Trace 列表 root input 批量查询失败：`logger.exception`（仍 `input=null`，不回退 N+1）。
- `bun run lint` 在上述修复后通过。

## 已完成：Playwright shell 关键路径 smoke

- `frontend/playwright.config.ts` + `frontend/e2e/shell.smoke.spec.ts`（API route mock，不依赖开发库）。
- 覆盖：登录 → `/dashboard`；Logo 为运行概览入口且侧栏无「运行概览」；权限不足空分组消失；智能体清除 `session`；深链 `/trace` 展开治理分组；侧栏折叠隐藏最近对话。
- 脚本：`cd frontend && bun run test:e2e`。

## 已完成：导航深链自动展开分组

- 深链进入 `/trace`、`/approvals`、`/cve` 等时，侧栏自动展开所属导航分组（桌面 + 移动 openKeys）。
- 纯函数：`navigationGroupKeyForItemPath` / `withOpenNavigationGroup`；默认仍展开前两个分组；不持久化 openKeys；移动端打开/路由切换 = 默认两组 + 当前路由分组。

## 已完成：antd 6 classNames + loguru 惰性格式

- Chat 模型选择器：`Popover.overlayClassName` / `Cascader.popupClassName` → antd 6 `classNames`（CSS 类名不变）。
- CVE 任务与数据源：去掉 logger f-string，统一 loguru `"{}"` 惰性格式。
- `api/main.py` 后台 Task 失败日志参数提取，避免在 logger 调用内嵌 f-string。

## 已完成：死代码删除 + progress/middleware 类型卫生

- 删除已无调用的 `KnowledgeBaseLifecycle._collect_all_content_rows_async`（clear 已流式）
- `knowledge_progress.emit_progress` 用 `isinstance(..., Awaitable)`；`stage_index` 线性匹配，去掉 type-ignore
- `main.py` CORS/JWT `add_middleware` 用 `cast(Any, ...)` 替代 type-ignore

相关：`knowledge_service.py` / `knowledge_progress.py` / `main.py`

---

## 已完成：Knowledge clear 流式删除

- `clear_knowledge_base_async` 不再 `_collect_all_content_rows_async` 全量装载；按 page 流式删除，删除后同页重取
- 跳过已删/失败 id；以 total 覆盖结束扫描，避免 mock/索引滞后死循环
- `_collect_all_content_rows_async` 加 50 页硬顶（其它潜在调用的安全网）

相关：`knowledge_service.py` / `test_knowledge_lifecycle.py`

---

## 已完成：Overview 去 type-ignore + Knowledge 全量 list 有界

- `get_runtime_overview` 对 `asyncio.gather` 结构化解包，去掉 7 处 `type: ignore[arg-type]`
- `list_documents_async` 改为分页拼装（100×50 页硬顶），避免单次无界 materialize；API/UI 仍优先 `list_documents_page_async`
- `model_config_file` 仅用于归档残留 JSON，永不导入（`TAIS_MODEL_CONFIG_FILE` 已移除）

相关：`overview_service.py` / `knowledge_service.py` / `config.py` / `model_config_service.py`

---

## 已完成：Eval suite/case run 真分页 data/meta

- `list_suite_run_rows_async` / `list_case_run_rows_async` 返回 `(rows, total)`，SQL `LIMIT/OFFSET` + count
- `list_suite_runs` / `list_case_runs` 统一 Agno 风格 `{data, meta}`（默认 page=1 limit=50，上限 100）
- 路由 `GET .../suites/{id}/runs` 与 `GET .../cases/{id}/runs` 接受 `page`/`limit` query

相关：`agent_evals.py` / `agent_eval_case_store.py` / `routes/agent_evals.py`

---

## 已完成：列表硬顶与 MCP enabled SQL 过滤

- `enabled_mcp_servers` 用 `list_server_rows(enabled=True)` 下推 SQL，避免全表再 Python filter
- upload approvals 无 `limit` 时硬顶 500，防止无界 dump
- eval suite/case **run 历史** list 默认 limit=100（可传；上限 500），suite/case 定义表仍全量（配置规模小）

相关：`api/persistence/mcp.py` / `upload_approvals.py` / `agent_evals.py` / `agent_eval_case_store.py`

---

## 已完成：model_config 空表不再 JSON 导入

- 空表只 seed `DEFAULT_MODELS`；存在 `model_config.json` 仅归档为 `*.imported`（warning），不写进 Postgres
- 去掉 `_load_legacy_or_default_store`；密钥与连接以 Settings/DB 为准
- MCP：无 external 条目且库中已有 server 时直接归档 leftover，不重放 builtin flags
- skills_config / front matter：解析异常类型收窄 + YAML 错误 debug 日志

相关：`model_config_service.py` / `mcp/config.py` / `skill_service.py` / tests

---

## 已完成：best-effort 静默 except 日志

- workflow 版本快照失败写 warning（仍不阻断 save）
- upload approval 归档删除失败写 warning
- knowledge upload 父目录 rmdir 失败写 debug
- `test_upload_approval_service` 对齐 list `page/limit` 断言（实现已真分页）

相关：`workflow_service.py` / `upload_approval_service.py` / `knowledge_upload_service.py`

---

## 已完成：model_config 残留 JSON 归档 + coerce_json 收窄

- 表非空时归档残留 `model_config.json` → `*.imported`（与 MCP `.migrated` 对齐），避免日后空表误回灌陈旧密钥
- 测试 fixture 隔离 `model_config_file` 路径，避免误归档开发机配置
- `coerce_json_value` 仅捕获 JSONDecodeError/TypeError/ValueError，并补 docstring

相关：`model_config_service.py` / `postgres_store.py` / `test_model_config_service.py`

---

## 已完成：删除 chat_settings re-export + 停 provider 热路径 rewrite

- 删除 `api/services/chat_settings.py` re-export；运行时仅 `chat_settings_service`
- `load_model_config_store` 不再因 Grok→xai / reasoning 启发式触发 `replace_model_config_rows`
- 读路径仍 `ModelConfig.normalized` 纠正 provider；显式 save / 完整性（多 active、非法 output mode、缺 builtin）仍会写库

相关：`chat_settings_service.py` / `model_config_service.py` / `test_model_config_service.py`

---

## 已完成：Chat settings 模块合并 + Trace 会话合并页数

- `ChatSettings` / `get_chat_settings_async` 并入 `chat_settings_service`；`chat_settings.py` 仅 re-export
- runtime 消费者改直接 import service；model config 行 rewrite 写 info 日志
- Trace 页 chat sessions 自动翻页 5→3（约 120 条，配合 limit=40）

相关：`chat_settings_service.py` / `chat_settings.py` / `TracePage.tsx` / `model_config_service.py`

---

## 已完成：ensure_*_table 进程内 AsyncOnce

- 抽取 `api/utils/async_once.AsyncOnce`（双检锁一次执行）
- 热路径 ensure：notifications / chat_settings / model_configs / audit / collect / cves / mcp / knowledge_sources / upload_approvals / workflows / agno postgres / app tables / agent_evals
- 避免每次 list/read 重复 `CREATE SCHEMA/TABLE/INDEX IF NOT EXISTS`

相关：`async_once.py` / 各 `api/persistence/*` / `postgres_store.py`

---

## 已完成：Chat settings / Skills config 短缓存

- `get_chat_settings` 5s TTL 进程缓存，update 时刷新；减轻 Chat 热路径重复读库
- `load_skills_config` 按文件 mtime 缓存；`save_skills_config` 写后更新缓存

相关：`chat_settings_service.py` / `skill_service.py`

---

## 已完成：MCP bootstrap 进程内只跑一次 + tokens 上限

- `bootstrap_mcp_config` 加 lock + `_BOOTSTRAP_DONE`，避免每次 `list_mcp_servers` 重复种子/扫表
- legacy `mcp_config.json`：迁移后归档 `.migrated`；若库中已有 external 也归档残留文件
- MCP tokens 列表默认 LIMIT 100（上限 200）

相关：`api/mcp/config.py` / `api/persistence/mcp.py` / `test_mcp_bootstrap.py`

---

## 已完成：model_config 进程内短缓存

- `load_model_config_store` 5s TTL 内存缓存，减轻 Chat/Settings 热路径重复读库与 normalize
- `save_model_config` / 测试 fixture 主动 invalidate

相关：`model_config_service.py` / `test_model_config_service.py`

---

## 已完成：MCP 按 name 定点查询

- 新增 `get_server_row_by_name` / `server_name_exists`，toggle/upload 查重/visibility 不再 `list_mcp_servers` 全表扫
- 列表仍走 `visible_mcp_servers` 全量（配置规模小）

相关：`api/persistence/mcp.py` / `mcp_config_service.py`

---

## 已完成：model_config 一次性导入归档 + Overview 采样 50 + SSE after 上限

- 空表 bootstrap：从 `model_config.json` 导入后重命名为 `model_config.json.imported`，避免反复空表回灌
- 无 legacy 文件时直接种子 defaults 并写库
- Overview token 样本 `_PAGE_LIMIT` 100→50
- `list_notifications_after` 单次上限与列表一致（max 200）

相关：`model_config_service.py` / `overview_service.py` / `notifications.py`

---

## 已完成：Knowledge getKnowledge 去掉 string 重载

- `getKnowledge` 仅接受 `GetKnowledgeParams` 对象；全站唯一调用方已是对象形式
- 去掉 “legacy string query” 兼容注释与分支

相关：`frontend/src/features/knowledge/api.ts`

---

## 已完成：Skills 列表去 markdown + 详情按需

- `list_skill_infos(include_detail=False)` 默认不读 SKILL.md / scripts / attachments；`has_scripts` 仅看 scripts 目录是否非空
- `GET /api/skills/{name}` 按需返回全文与文件清单；Skills 页选中后 `getSkill`
- Chat 会话默认 limit 前后端统一 40（硬顶仍 500）

相关：`skill_service.py` / `routes/skills.py` / `SkillsPage.tsx` / `chat_session_service.py`

---

## 已完成：Chat 会话页大小收紧 + Knowledge clear 日志

- Chat / Trace 共用 `SESSION_PAGE_SIZE` 100→40（侧栏与 infinite load-more 首屏更轻；Trace 自动合并窗口 5 页 ≈200 条）
- `listSessions` 默认 limit 同步 40；相关 api/trace 测试对齐
- Knowledge `clear_knowledge_base_async` 单条删除失败写 warning（仍收集 `failed_ids`）

相关：`chat/queries.ts` / `chat/api.ts` / `knowledge_service.py`

---

## 已完成：通知列表索引 + Trace audit 补充可观测

- `notifications` 表补 `user_id+created_at` / `user_id+id` / `user_id+read` 索引，覆盖抽屉列表、SSE 游标与未读计数
- Trace ERROR 列表 audit 补充路径：`get_trace` 失败写 debug 日志，不再静默 `continue`

相关：`api/persistence/notifications.py` / `tracing_service.py`

---

## 已完成：Evals failures 有界多页扫描

- `list_failed_eval_runs` 不再只取第一页后过滤；在最多 10 页 × page_size=50 的窗口内收集失败项直至 `limit`
- 覆盖「近期大量通过、失败落在后续页」的场景；仍无原生 `passed=false` 过滤时保持有界

相关：`agent_eval_result_service.py` / `test_agent_eval_result_service.py`

---

## 已完成：通知 SSE 缓存上限 + Overview token 采样 100 + README 对齐

- 通知中心 SSE 增量写入 Query 缓存时截断至 100 条，与 `list_notifications` 默认上限一致，避免长会话无界膨胀
- Overview `_PAGE_LIMIT` 200→100（latency/series 已 SQL；token 样本更小）
- README：Approvals `kind=all` 描述改为两路服务端分页虚拟合并（去掉过时「submissions 整表」）

相关：`AppFrame.tsx` / `overview_service.py` / `test_overview.py` / `README.md`

---

## 已完成：通知列表上限 + Evals 分页 + Collect 搜索防抖

- 通知：`list_notifications` 默认 LIMIT 100（上限 200），`unread_count` 仍全表计数，避免抽屉无界物化历史
- Evaluations：`listRuns({ page, limit })` 返回 `{ items, total, page, limit }`，Runs 表受控分页（20）；Failures 默认 limit=50
- Collect：检索词 300ms 防抖（`useDebouncedValue`），防抖/来源变更重置页码，去掉多余手动 refetch

相关：`api/persistence/notifications.py` / `frontend/src/features/evaluations/*` / `CollectPage.tsx`

---

## 已完成：Collect 源站爬虫入库

- `domain_rules` 配置站作为采集源；管理员「同步源站」爬列表页链接并解析 Markdown
- Postgres `collect_articles`；Collect 页以库检索为主，单 URL 采集仍写入库
- API：`GET /sources`、`POST /articles/search`、`GET /articles/{id}`、`POST /crawl`、`POST /parse`

相关：`collect_articles.py` / `collect_crawl_service.py` / `routes/collect.py` / `CollectPage`

---

---

## 已完成：Memory 服务端分页 + Knowledge 服务端排序

- Memory 列表：`page/limit=12` 受控分页 + 搜索 300ms 防抖（不再客户端切默认 20 条窗口）
- Knowledge 列表：title/created/updated 列 sorter 透传 `sort_by`/`sort_order`（去掉跨页不准的客户端 sort）

相关：`MemoryPage` / `KnowledgePage` / `DocumentsTable`

---

## 已完成：Knowledge 过滤防抖 + Feishu payload 日志

- `useDebouncedValue`：Knowledge 列表 filter 300ms 防抖后再请求
- 过滤变更通过 debounced 值重置 page；搜索框仍即时更新输入
- Feishu `_payload_size` 失败 debug 日志（仍按 oversized 截断）

相关：`useDebouncedValue.ts` / `KnowledgePage` / `DocumentsTable` / `basic.py`

---

## 已完成：Knowledge 服务端分页 + Overview 单页采样

- Knowledge 列表：`getKnowledge({ page, limit })` + Table 受控分页，默认 limit=12；过滤重置到第 1 页
- Overview `_fetch_traces` 去掉无用的多页循环（`_MAX_OVERVIEW_TRACE_PAGES` 已恒为 1）
- Feishu webhook 非 JSON 响应写 warning

相关：`knowledge/api.ts` / `KnowledgePage` / `DocumentsTable` / `overview_service.py` / `basic.py`

---

## 已完成：Approvals 后续页并行 + 配置/skill 可观测

- `getApprovals(kind=all)` 上传窗口内后续页也 `Promise.all` 并行 submissions + HITL
- model config 表空时从 legacy 导入写 `info` 日志
- intranet-ip-skill 外部查询失败写 `warning`（仍返回空列表）

相关：`approvals/api.ts` / `model_config_service.py` / `intranet-ip-skill/agent.py`

---

## 已完成：Approvals all 并行 + status counts 并行

- `getApprovals(kind=all)` 首页 `Promise.all` 并行拉 submissions + HITL；后续页先 probe upload total，越过上传区则只打 HITL
- `get_approval_status_counts` 并行 pending/approved/rejected；失败写 exception 日志

相关：`approvals/api.ts` / `approvals_service.py`

---

## 已完成：配置加载失败可观测 + Overview token 采样 200

- skills / legacy model_config JSON / MCP 文件迁移：解析失败写 warning，不再静默空配置
- Overview token 样本 `_PAGE_LIMIT` 1000→200（latency/series 已 SQL；失败回退样本也更小）

相关：`skill_service.py` / `model_config_service.py` / `mcp/config.py` / `overview_service.py`

---

## 已完成：MCP/知识库吞异常日志 + Overview token 样本去 reconcile

- Octomation playbook 参数拉取降级路径：`except pass` → warning/info 日志
- Feishu webhook 请求失败写 warning（仍返回错误码）
- knowledge chunk count / hydrate、vector reassign、best-effort remove：debug/warning 日志
- Overview `_fetch_traces` token 采样不再 `reconcile_trace_statuses`（失败数走窗口 ERROR + recent_failures）

相关：`playbook.py` / `basic.py` / `knowledge_service.py` / `knowledge_source_service.py` / `overview_service.py`

---

## 已完成：吞异常日志 + Overview token 采样 1k + resolveApproval 收窄

- `workflows` 列迁移、`knowledge_source` 选择性向量删除、workflow resume 终态写回：`except pass` → debug/warning/exception 日志
- Overview token 采样上限 2×1000→1×1000（latency/series/distributions 已 SQL）
- 前端 `resolveApproval` 去掉 string 重载，统一 options 对象

相关：`workflows.py` / `knowledge_source_service.py` / `workflow_run_runtime.py` / `overview_service.py` / `approvals/api.ts`

---

## 已完成：HITL 拒绝理由只读 note + Overview token 采样收窄

- HITL 读路径只使用 `resolution_data.note`：`chat_run_events` / `security_run_runtime` / `workflow_run_runtime` 去掉 `rejection_reason` 双读
- 写路径本就只写 `note`；upload submissions 顶层 `rejection_reason` 不变
- Overview `_fetch_traces` 采样上限 5×1000→2×1000（token / SQL 回退）；p50/p95/series/失败数仍走窗口 SQL

相关：`chat_run_events.py` / `security_run_runtime.py` / `workflow_run_runtime.py` / `overview_service.py`

---

## 已完成：Knowledge 注入路径真分页

- `list_documents_page_async` 在注入 `knowledge_content_rows_async` 时不再 `list_documents_async` 全量再内存 slice
- 无 owner/query：透传 `page/limit/total` 给依赖
- 仅 owner：流式拉 content 页，只保留当前窗口 + 匹配 total
- 有 query：流式匹配后 `paginate_documents`（搜索仍需扫匹配集）
- 生产 SQL 路径（无注入）不变，继续 `_knowledge_document_page_rows_async`

相关：`knowledge_service.py` / `test_knowledge_lifecycle.py`

---

## 已完成：Overview 延迟 / series SQL 聚合

- 窗口 p50/p95：`percentile_cont` over `duration_ms`（无 duration 时 end-start），全量窗口不落内存
- series：SQL `date_trunc` 分桶 + runs/failed_runs/p50/p95；token 仍用采样 spans 叠加到同 bucket
- distributions：agent/workflow/team SQL `GROUP BY`
- SQL 失败时回退既有 capped sample 路径；`sample_size`/`truncated` 仍描述 token 样本
- 失败计数与 recent_failures 继续走窗口 ERROR 查询

相关：`overview_service.py` / `test_overview.py`

---

## 已完成：Trace sessions SQL 分组分页

- `list_trace_sessions` 优先对 `agno_traces` 做 SQL `GROUP BY session_id`（count / distinct run / error_count / max start_time）
- 当前页用 `DISTINCT ON (session_id)` 投影最新 trace 行；仅对页内 latest run 做 status reconcile
- 表不可用或 SQL 异常时回退有界扫描 + Python group（`meta.truncated` 仍可能出现）
- 大窗口 sessions 列表不再必须把匹配 traces 全量载入内存

相关：`tracing_service.py` / `test_trace_permissions.py`

---

## 已完成：Trace 页 chat sessions 自动翻页上限

- Trace 合并归档/预览时后台 `listSessions` 最多 5 页（约 500 会话），避免用户会话很多时无限拉取

相关：`TracePage.tsx`

---

## 已完成：Overview 窗口失败计数 + 原生 recent failures

- `failed_runs` / `failure_rate` / `total_runs` 用 Agno 窗口 total（含 `status=ERROR` count），不再依赖采样切片
- `recent_failures` 直接 `get_traces(status=ERROR, limit=10)` + reconcile，避免「样本里碰巧没失败」
- metrics 仍带 `sample_size` / `truncated` / `sample_failed_runs`（延迟与 token 仍基于采样）

相关：`overview_service.py` / Dashboard types

---

## 已完成：Trace sessions 前端翻页上限

- `listTraceSessions` 客户端最多拉 5 页 ×200（1000 sessions），避免无界 while 打满大库
- 触顶时 `truncated=true`，与后端 sessions 有界扫描一致

相关：`trace/api.ts`

---

## 已完成：Trace 原生 status 过滤 + Approvals agent 真分页

- `list_traces(status=)` 走 Agno `get_traces(status=..., page/limit)` SQL 分页，不再全窗扫描
- ERROR 列表首页可补充 audit 中失败但 traces 仍为 OK/UNSET 的 run（`recent_failed_chat_run_ids_async`）
- sessions 分组扫描在 status 时也 SQL 预过滤，缩小窗口
- Approvals `kind=agent` 用 `source_type=agent` 真分页，去掉客户端密度扫描（最多 20 页）

相关：`tracing_service.py` / `audit_logs.py` / `approvals/api.ts`

---

## 已完成：Overview metrics 样本元数据

- `_fetch_traces` 返回 `(rows, {sample_size, window_total, truncated})`
- Dashboard metrics 暴露采样规模；截断时 KPI 旁标注 sample/window

相关：`overview_service.py` / Dashboard types+i18n

---

## 已完成：Trace status 流式过滤 + 后台 Task 失败通知

- Trace `status=` 列表按批 `get_traces` → reconcile → 只保留匹配行，避免整窗 2k 全量常驻
- `meta.truncated` / `meta.scanned_count` 在扫描达上限时标记（sessions 列表同样）
- asyncio 后台异常（如 `amake_memories`）除日志外通知 admins（`notify_background_task_failure`）
- Trace UI 在 status 过滤且 `meta.truncated` 时显示有界扫描警告

相关：`tracing_service.py` / `pagination.py` / `notification_service.py` / `main.py`

---

## 已完成：Approvals 拒绝理由字段收窄

- 前端 `rejectionReason` 只读 `resolution_data.note`（HITL）与顶层 `rejection_reason`（upload submissions）
- 不再读历史 `resolution_data.rejection_reason` 别名（写路径已只写 note）

相关：`ApprovalsPage.tsx`

---

## 已完成：Memory 列表 stats 去全局扫

- 管理端未指定 user 时，按当前页出现的 user_id 并发 `get_user_memory_stats(limit=1)`，不再 `limit=500` 全站 stats
- 有 user 作用域时仍单次 scoped stats

相关：`memory_service.py` / `test_memory_approval_permissions.py`

---

## 已完成：Knowledge 全量列表翻页

- `list_documents_async` / `clear_knowledge_base_async` 经 `_collect_all_content_rows_async` 按页拉取（page_size 200），去掉硬顶 500 窗口遗漏
- 注入 `knowledge_content_rows_async` 的依赖路径（测试/假实现）与生产一致；列表 API 仍走 `list_documents_page_async` SQL 分页

相关：`knowledge_service.py` / `test_knowledge_lifecycle.py`

---

## 已完成：Chat sessions 侧栏 load more

- `listSessions` 返回 `{ data, meta }`；`sessionsQuery` 改为 `useInfiniteQuery`（page size 100）
- 最近对话侧栏在有下一页时显示「加载更多」；乐观新建/重命名写入 infinite pages 缓存

相关：`chat/api.ts` / `queries.ts` / `useChat.ts` / `ChatTaskPanel.tsx`

---

## 已完成：热路径收紧（eval 采样 / knowledge status / sessions limit）

- Overview 评估快照：`list_agno_eval_runs(limit=20)`；`pass_rate` 基于近期样本，payload 含 `sample_size`；Dashboard 文案标注样本/总数
- Knowledge status：无预取时用 `list_documents_page_async(limit=1)` 取 total，不再 `list_documents_async` 全量
- Chat sessions 默认 `page/limit`：**100**（API / service / 前端 `listSessions` 一致；硬顶仍 500）

相关：`overview_service.py` / `knowledge_service.py` / `chat_session_service.py` / `routes/chat.py` / Dashboard i18n

---

## 已完成：workflow 死导出 + loguru 惰性日志

- 删除未使用的 `createStep` / `isEntranceHandle` / `isDefaultExitHandle`。
- `api/routes` 与 `api/tasks` 中 42 处 `logger.*(f"...")` 改为 loguru 惰性 `"{}", arg` 格式（避免无谓 f-string 求值/风格债）。

相关：`frontend/src/features/workflow/utils.ts` / `api/routes/*` / `api/tasks/*`

## 已完成：前后端无引用 API/helper 清理

- 后端 `page_payloads` 仅保留 `iso` / `now_utc` / `row_dict`，删除未用的 `metric`/`record`/`compact` 与 TypedDict。
- 前端删除未使用导出：`asArray`、`isAgentHitlApproval`、`mergeRunMetadata`、`getWorkflow`、`createSuite`/`createCase`、`getArticle`、`addFilePath`（及 `AddPathPayload` 类型）。

相关：`api/services/page_payloads.py` / `frontend/src/shared/lib/format.ts` / 各 feature `api.ts`

## 已完成：删除无引用 helpers + 去掉 TAIS_MODEL_CONFIG_FILE

- 删除死代码：`stage_index`/`active_stage_from_events`、`get_suite_run`/`get_suite_run_row_async`、`get_submission_approval`、`ensure_audit_log_table_async`、`server_rows()`、`count_collect_articles`、`upsert_cve_row`/`reset_cve_id_sequence`、`reset_token_id_sequence`、CVE `_process_codes`/`_process_file`。
- `model_config_file()` 固定归档 `CONFIG_DIR/model_config.json`；移除 Settings/`TAIS_MODEL_CONFIG_FILE` 覆盖（仍只归档、永不导入）。

相关：`knowledge_progress.py` / `agent_eval*` / `upload_approval_service.py` / `audit_service.py` / `mcp` / `cves` / `collect_articles` / `cve_sources.py` / `config.py` / `model_config_service.py`

## 已完成：删除死代码 + sessions 列表命名

- 删除未引用：`tracing_service._all_trace_items`、`knowledge_service._document_status_async`、`chat_session_service.is_session_archived_async`、`workflow_service.mark_cron_last_run`（cron 仅用原子 `try_claim_cron_run`）。
- `get_all_sessions_async` 重命名为 `list_sessions_async`（真实 SQL 分页，不再暗示全量扫描）；路由与测试同步。

相关：`tracing_service.py` / `knowledge_service.py` / `chat_session_service.py` / `workflow_service.py` / `routes/chat.py`

## 已完成：Knowledge SSE 进度去重 + 后台 task 命名

- `update` / `update/upload` 流式路径复用 `_run_progress_sse`（含 LookupError 阶段可选 `lookup_failed_stage`），去掉两段重复 worker/event_generator。
- Knowledge 与 security run 的 `asyncio.create_task` 补充 `name=`，便于 asyncio 异常处理定位。

相关：`api/routes/knowledge.py` / `api/services/security_run_runtime.py`

## 已完成：TTL 缓存共用 + Approvals slice 对齐 + Eval 列表安全上限

- 新增 `api/utils/ttl_cache.TtlCache`；`chat_settings` / `model_config` 短 TTL 缓存改用同一实现。
- 前端 `fetchSubmissionsSlice` 与 HITL slice 对齐：跨页 offset 不足时补拉下一页，避免截断。
- Eval suite/case 定义列表 persistence 默认 `limit=500`（硬顶沿用 `_list_rows_async`）。
- `schedule_workflow_resume` 后台 task 命名便于 asyncio 失败日志定位。

相关：`api/utils/ttl_cache.py` / `chat_settings_service.py` / `model_config_service.py` / `agent_evals.py` / `frontend/src/features/approvals/api.ts`

## 已完成：Knowledge 列表扫描页数收紧

- free-text / owner-filter list 路径将 content 扫描上限从 10_000 页降到 50 页（与 `list_documents_async` 同量级），超限写 warning。
- `clear_knowledge_base_async` 仍保留较高 `max_rounds` 以便流式清库扫完。

相关：`api/services/knowledge_service.py`

## 已完成：MCP bootstrap 统一 AsyncOnce

- `bootstrap_mcp_config` 用手写 `_BOOTSTRAP_LOCK/_DONE` 改为共用 `api.utils.async_once.AsyncOnce`。
- 测试通过 `reset()` 复位；行为仍为进程内只 seed 一次。

相关：`api/mcp/config.py` / `api/tests/test_mcp_bootstrap.py`

## 已完成：上传审批列表强制分页

- `list_upload_approvals` / `list_submission_approvals` 去掉 `limit=None` 全表回退；默认 `limit=100`，硬顶 200，始终 `LIMIT/OFFSET`。
- 页面路径仍走 `list_submission_approvals_page` 的 `{data, meta}`。
- 清理 `test_workflow_routes` 未使用 import。

相关：`api/persistence/upload_approvals.py` / `api/services/upload_approval_service.py`

## 已完成：生产路径 type-ignore 清理

- `security_run_runtime` 流式重试 patch 改用 `setattr`，去掉 `# type: ignore[method-assign]`。
- `workflow_run_runtime` 对 `workflow.arun(stream=True)` 统一 `isawaitable` + `cast(AsyncIterator)`，去掉 `# type: ignore[union-attr]`。
- 生产 `api/` 包内不再有 `# type: ignore`（测试仍可用 method-assign mock）。
- 顺手去掉 workflow 相关模块 docstring 中的内部 PR 编号噪音。

相关：`api/services/security_run_runtime.py` / `workflow_run_runtime.py` / workflow 模块 docstring

## 已完成：技术债收紧（Memory / Overview / 兼容）

- Memory 列表 `get_user_memory_stats` 按当前 user 作用域查询（`limit=1`），避免普通用户/单用户筛选触发 500 用户 stats 扫
- Dashboard overview 知识库文档数改为 `list_documents_page_async(limit=1)` 取 total，不再 `list_documents_async` 拉全量
- Chat sessions SQL 分页结果跳过二次内存排序（`already_sorted=True`）
- 删除 workflow `_is_workflow_step_approval` 兼容别名；Approvals 前端去掉 legacy `{approvals}` envelope
- Chat sessions 仅解析 `data/meta`；Live Search 开关只信 `capabilities.supports_live_search`

相关：`memory_service.py` / `overview_service.py` / `chat_session_service.py` / `workflow_run_runtime.py` / `approvals/api.ts`

---

## 已完成：模型设置精简

- 设置表单只保留：名称 / 供应商 / Model ID / API Key / Base URL / 启用
- 协议、structured output、reasoning、重试、parallel tools、Live Search 等走能力画像默认
- 保存时合并既有高级字段；切换供应商时重套最优默认

相关：`SettingsPage.tsx` / `model_capabilities.py`

---

## 已完成：模型能力画像（optimal + fallback）

- `model_capabilities.py`：各 provider 最优协议/structured/reasoning/Live Search
- xAI：无 `reasoning_effort`（按 model_id 推理/非推理）；支持 Live Search
- 解析链：请求覆盖 → 模型配置 → optimal → fallback；不支持则省略
- 公开 `capabilities` 字段；Chat/设置按能力收窄开关

相关：`model_capabilities.py` / `model_config_service.py` / `model_factory.py`

---

## 已完成：xAI Structured Output + Live Search / Knowledge 开关

- xAI 放开 `structured_output_mode`（native/json）；设置页可配 `live_search_enabled`
- Chat 输入区：联网搜索（Live Search）与知识库检索开关；Run 透传 `live_search` / `search_knowledge`
- 模型工厂：xAI `search_parameters`；OpenAI-compatible `extra_body.search_parameters`

相关：`model_factory.py` / `security_run_runtime.py` / `ChatPage.tsx` / `SettingsPage.tsx`

---

## 已完成：设置页删除模型

- 模型列表支持删除自定义模型（内置不可删、至少保留一个）
- 删除当前模型时自动切换到其它可用模型

相关：`SettingsPage.tsx`

---

## 已完成：xAI 官方 Agno 接入

- `provider=xai` → `agno.models.xai.xAI`（默认 `https://api.x.ai/v1`，Chat Completions）
- 内置模型 `xai-grok-4.5`；旧 Grok / `api.x.ai` 配置自动迁移，不再用 OpenAI Responses
- 设置页可选 xAI；不暴露 reasoning_effort

相关：`model_factory.py` / `model_config_service.py` / `SettingsPage.tsx`

## 已完成：Collect 规则修复与爬取性能

- 停用 `botcrawl.com` / `go.theregister.com` / `www.securitylab.ru`（`DISABLED_COLLECT_DOMAINS` + 从 `domain_rules` 移除）
- `resolve_domain_rule_key`：`www` 别名与 host 归一化，修复 `cybersecuritynews.com` / `dailydarkweb.net` 等「Rules not found」
- 多 class 正文选择器（BS4 `class_` 列表语义）+ debug 日志替代 print
- 列表发现 / 正文抓取并发（semaphore）；已入库 `status=ok` URL 跳过；批量 upsert

相关：`url2md_utils.py` / `url2md_service.py` / `collect_crawl_service.py` / `collect_articles.py`

---

## 已完成：React Flow skill 对齐（Studio canvas）

- Typed `WorkflowCanvasNode` + `NodeProps<…>`；Handles 透传 `isConnectable`
- 模块级稳定 `nodeTypes` / `defaultEdgeOptions` / `fitViewOptions` / MiniMap color
- `IsValidConnection` 校验 targetHandle；`onlyRenderVisibleElements` + `elevateNodesOnSelect`
- 首节点 drop 才 fitView；Controls 开 zoom/fitView

相关：`WorkflowCanvas.tsx` / `WorkflowFlowNode.tsx`

---

## 已完成：拖拽智能对齐 + Chat 操作位

- 拖拽时智能辅助线（左右/中/上下边对齐吸附）
- Chat 消息 Actions：右下角；复制内容 / 复制 Run ID 图标区分

相关：`utils.computeSmartSnap` / `WorkflowCanvas` / `ChatPage`

---

## 已完成：Workflow 文案与 Studio 布局 / antd 清理

- 中英文文案去 PR / 第三方产品名，聚焦安全运营业务用语
- Studio 顶栏与左右栏更紧凑；节点面板双列
- antd 6：Alert `title`/`closable.onClose`；AutoComplete `onOpenChange`；Collapse `destroyOnHidden`

相关：`workflow.*.json` / `WorkflowPage` / `CelExpressionField` / `global.css`

---

## 已完成：几何感知连线端口（L/R vs Top/Bottom）

- `pickConnectionHandles`：目标在右侧 → `out-right`/`*-right` + `in-left`；否则 top/bottom
- `layoutCanvas` 在节点坐标确定后二次选择 handle；根序列无坐标时默认横向排布
- 分支语义 id（`then`/`else`/`choice:…`）保留，仅切换 side alias
- 不改 DSL；用户拖拽连线仍以抓取的 handle 为准

相关：`utils.ts` / `utils.test.ts`

---

## 已完成：自动布局防重叠（pixel tree packer）

- `applyAutoLayout` 按节点高度 + sibling gap 堆叠 then/else
- 根节点横向排布；同列二次分离兜底；模板载入自动 layout

相关：`utils.ts` / `useWorkflow` applyTemplate

---

## 已完成：产品 P0.4 审批值班入口

- Approvals 默认：`kind=workflow` + `status=pending`
- Tab：工作流 HITL / 上传 / Chat HITL / 全部
- 工作流暂停创建审批时通知 admins（深链 `approval_id`）
- Studio openApproval + 通知中心深链不变

相关：`ApprovalsPage.tsx` / `approvals/api.ts` / `notification_service.py` / `workflow_run_runtime.py`

---

## 已完成：产品 P0.3 Step 级 Skill 绑定

- DSL `skills: string[]` 规范化；编译时按 step 加载 `enabled ∩ bound`
- `resolve_enabled_skill_dirs`；`skill.load` 审计 + `workflow.started` 携带 skills
- Studio Inspector 多选已启用 Skill；IR / alert-fanout 模板推荐绑定
- Chat 路径不变（全局 enabled）

相关：`workflow_compiler.py` / `skill_service.py` / `workflow_run_runtime.py` / `WorkflowPage.tsx`

---

## 已完成：产品 P0.2 触发器运维（Webhook / Cron）

- Studio：Webhook URL、secret 复制/轮换、`curl -N` SSE 示例
- Cron：上次触发 + 服务端 `next_cron_at` 下次预计
- 失败通知：`notify_workflow_trigger_failure` → owner + admins，深链 Trace
- 触发历史失败徽标保留 Trace 跳转

相关：`workflow_cron.py` / `notification_service.py` / `routes/workflows.py` / `WorkflowPage.tsx`

---

## 已完成：产品 P0.1 Draft/Published 状态机 + 空态引导

- 顶栏：`draft vN` / `published vM @ time` / `未发布` + dirty `*`
- 触发器启用守卫：`triggerEnableBlocked` + modal 引导 Save/Publish
- 空画布 CTA：从 IR triage 模板开始；模板「载入草稿 / 保存并打开」
- Publish 在「已保存未发布」时 primary+ghost 高亮

相关：`types.ts` / `utils.ts` / `useWorkflow.ts` / `WorkflowPage.tsx` / `WorkflowCanvas.tsx` / i18n

---

## 已完成：Studio 性能（SSE 增量 + 选中/高亮 patch）

- Run SSE：`applyNodeRunStatusEvent` 增量更新 `nodeRunStatus`（不再每次全量 replay log）。
- `runLog` 上限 200（`appendRunLog`），控制内存。
- 画布：点击选中 / drop·connect 高亮只 patch `selected` 与 data flags，不触发 `layoutCanvas`。
- runStatus 仅对 **变更节点** 调 `updateNodeData`。

相关：`runStatus.ts`、`useWorkflow.ts`、`WorkflowCanvas.tsx`



## 已完成：Studio P0（RF updateNodeData + antd-in-canvas）

- 画布：`topologyKey` / `contentKey` 拆分；SSE `runStatus` 走 `updateNodeData` + data patch，避免全量 `buildGraph`。
- Inspector/CEL：`nodrag`/`nowheel`/`nopan`；Select/Tooltip/`AutoComplete` `getPopupContainer` → `.workflow-studio`。
- MiniMap 按 run 状态上色；RF / ant-design skill 补充 Studio 共存门禁。

相关：`WorkflowCanvas`、`CelExpressionField`、`WorkflowPage`、skill 附录



## 已完成：Workflow PR9（模板 / run scope / CEL 提示）

- **权限**：`workflows:run`（user 默认具备）；`POST .../runs` 仅需 run，编辑仍需 write。
- **模板**：`GET /api/workflows/templates` + Studio 左侧模板卡片一键载入草稿（IR / fan-out / patrol / severity router）。
- **CEL**：Inspector Condition/Loop/Router 使用 `CelExpressionField` 自动完成提示。

相关：`api/auth/claims.py`、`workflow_templates.py`、`routes/workflows.py`、`CelExpressionField`/`celHints`、`WorkflowPage`/`useWorkflow`



## 已完成：PR8c 触发器生产化 + PR8d 画布性能 + Metadata Drawer

### PR8c（触发器）
- Cron：`claim_cron_last_run` 行锁 + CAS `last_run_at`（多实例防双发）
- Cron/Webhook 审计：`workflow.trigger.cron` / `workflow.trigger.webhook`（started + 终态）
- `GET /api/workflows/{id}/triggers/history` → Studio Definition 触发历史 + Trace 跳转

### PR8d（画布）
- Run 状态：`nodeRunStatus` 用 data patch 更新，避免每次 SSE 全量 `buildGraph`
- Inspector 字段编辑：按节点 burst 写入 undo（600ms 合并）

### Metadata Drawer
- Skills / MCP / Memory：侧栏 Metadata 改为 Drawer，主区全宽表格

相关：`workflow_cron.py`、`workflows.py` routes/persistence、`WorkflowCanvas`/`useWorkflow`/`WorkflowPage`、`SkillsPage`/`McpPage`/`MemoryPage`


## 已完成：Workflow 画布 PR8b（打磨）

- 保存前校验：空 Parallel/Loop/Condition/Router、缺 executor / workflow_ref → 节点标红 + Inspector 列表可点击定位。
- 连线中高亮目标节点；合法/非法连接沿用 handle 规则。
- 运行中 `fitView` 聚焦 running/paused 节点。
- 选中 NodeToolbar：Copy / Dup / Del。

相关入口：`validateWorkflowDraft`、`WorkflowCanvas`/`FlowNode`、`useWorkflow.save`


## 已完成：Workflow 画布 PR8a（多 Handle 分支边）

- Condition：`then` / `else` 双 source Handle；Router：每个 choice 独立 Handle。
- `layoutCanvas` 边带 `sourceHandle` / `targetHandle`；分支边样式区分。
- 从分支 Handle 连线 → reparent 到对应 `thenSteps` / `elseSteps` / `choices`。
- CTA / 连接校验：`nodrag`、禁自环与非法 handle。

相关入口：`WorkflowFlowNode`、`utils.branchHandlesFor`/`reparentTargetFromHandle`、`WorkflowCanvas`


## 已完成：Workflow PR7（Publish + Cron 真调度）

- **Publish**：`POST /api/workflows/{id}/publish` 将 draft definition 固化为 `published_definition`；webhook/cron **只跑 published**。
- **Cron**：进程内 ticker（30s）+ `croniter`；`triggers.cron.{enabled,expression,last_run_at}`；防重入先写 last_run_at。
- Studio：Publish 按钮、Cron 开关与表达式、提示「触发器走已发布版本」。
- RF skill 小修：CTA `nodrag`、`isValidConnection` 禁自环。

相关入口：`workflow_cron.py`、`workflow_service.publish_*`、`routes/workflows.py`、`main.py` lifespan、`WorkflowPage`


## 已完成：Workflow PR6（运行态可视化 + Approvals 闭环 + schema 表单）

- 画布节点 run 状态：`running / ok / error / paused`（SSE 归约 + 脉冲高亮）。
- SSE：`workflow.paused` 附带 `step_id` / `approval_id` / `pause_type`；stream 将 pause 视为终端。
- Studio：最近 runs 历史、Open Trace / Open approval 深链；`#/workflow?workflow_id=` 回跳。
- Approvals：`user_input_schema` 动态表单 → `resolution_data.user_input`；output_review 编辑；Open workflow。
- Inspector：Step 可配置 `user_input_schema` JSON。

相关入口：`runStatus.ts`、`WorkflowCanvas`/`FlowNode`/`Page`、`ApprovalsPage`、`workflow_run_runtime.py`


## 已完成：Workflow Studio 编辑深化（reparent / history / layout / HITL 表单）

- 画布：**拖入容器 reparent**（节点拖到 Parallel/Condition/Loop/Router 上嵌套）；调色板 drop 到容器同理。
- 空容器 **CTA**（+ Add then/else/branch/body）一键补 Agent step。
- **Undo/Redo**、Delete/Backspace、Ctrl/Cmd+C/V、Shift 多选、Ctrl/Cmd+L 整理布局。
- **一键整理**：树形 auto-layout 写回 `position`（层次 packer，无额外 dagre 依赖）。
- Approvals：`user_input` / `output_review` 批准弹窗写 `resolution_data`；后端 tool_args 附带 output 种子。

相关入口：`frontend/src/features/workflow/*`、`ApprovalsPage`/`approvals/api`、`workflow_run_runtime.py`


## 已完成：Workflow Studio Dark Mode

- Studio / 画布 / 节点 / MiniMap / Controls 使用 `--tais-*` 与 `html.dark` 变量。
- React Flow `colorMode` 跟随应用主题开关。


## 已完成：Workflow 画布优先 Studio（画布优先编排）

- 主区域为全高 React Flow 画布；左侧节点面板拖入/双击添加，右侧 Inspector + 运行日志。
- 自定义节点卡片、拖放落点坐标、顶栏 Save/Run/模型。
- 不再以列表为主编辑面。


## 已完成：Workflow PR4（Router / 嵌套 / 版本触发器 / 画布编辑 / 完整 HITL）

- DSL：`router`（CEL selector + choices）、`workflow_ref`；Step 支持 confirmation / user_input / output_review。
- 画布：拖拽落盘 `position`、按 Y 重排顶层；连线调整顶层顺序。
- 版本：保存时快照 `workflow_versions`；`GET .../versions` + restore。
- 触发器：`triggers.webhook`（secret + `POST .../hooks/webhook` SSE）；cron 配置落库（调度器后续）。
- SSE：`router.*`；暂停审批区分 pause_type 并在 resume 时 confirm/set_user_input/edit。


## 已完成：Workflow PR3（画布 + Step HITL + workflows scope）

- 独立权限：`workflows:read` / `workflows:write`（菜单 / API 不再复用 sessions）。
- Step `requires_confirmation`（禁止 Parallel 内 HITL）；暂停时写入 Approvals（`source_type=workflow`），批准后 `acontinue_run`。
- 前端 React Flow 画布（层次布局 + 选中联动 Inspector）；导出代码含 HITL 字段。

相关入口：`api/auth/claims.py`、`workflow_compiler.py`、`workflow_run_runtime.py`、`routes/approvals.py`、`frontend/src/features/workflow/*`


## 已完成：Workflow PR2（Parallel / Condition / Loop）

- DSL 递归校验：`step | parallel | condition | loop`（深度/节点/叶子上限；唯一 id；CEL 语法校验）。
- `workflow_compiler` → Agno `Parallel` / `Condition(CEL)` / `Loop`；依赖 `cel-python`。
- SSE 投影：`parallel.*` / `condition.*` / `loop.*` / `loop.iteration.*`。
- 前端：嵌套节点列表 + Inspector（CEL / max_iterations / then-else / 子步骤）。
- 编译期拒绝 HITL 字段；Parallel 内禁止 executor HITL。

相关入口：`api/services/workflow_compiler.py`、`workflow_run_runtime.py`、`frontend/src/features/workflow/*`


## 已完成：设置页帮助文案改为 Tooltip

- 模型高级表单项（并行工具、重试相关）去掉 `Form.Item extra`，改用 `tooltip` 图标提示。
- Chat 设置长文 `privacyNote` 收成短链 + Tooltip。

相关入口：`frontend/src/features/settings/SettingsPage.tsx`

## 已完成：Workflow PR1（线性 Step + Save/Run SSE）

- `app.workflows` 表 + CRUD（`{data,meta}`）；定义 DSL 仅 `type=step` + 内置 agent ref。
- `workflow_compiler` → Agno `Workflow`/`Step`；`POST /api/workflows/{id}/runs` SSE（`workflow.*` / `step.*`）。
- 前端：库加载、保存、运行日志、导出参考代码、Trace session 深链；菜单 scope 改为 `sessions:write`。
- README 新增「工作流编排技术架构」路线图（PR2–PR4）。

相关入口：

- `api/persistence/workflows.py`、`api/services/workflow_*.py`、`api/routes/workflows.py`
- `frontend/src/features/workflow/*`

## 已完成：Chat / Markdown LaTeX 公式渲染

- 抽出共享 `Markdown` 组件，启用 `@ant-design/x-markdown/plugins/Latex`（KaTeX）。
- Chat、Approvals、Knowledge、Collect、Skills、PayloadViewer、FormattedContentCard 统一使用。
- 支持 `$...$`、`$$...$$`、`\(...\)`、`\[...\]`；流式与最终消息均可渲染。

相关入口：

- `frontend/src/shared/ui/Markdown.tsx`
- `frontend/src/features/chat/ChatPage.tsx`

## 已完成：Chat 模型重试 UI + Dashboard Trace 深链

- Chat：`security_run_runtime` 包装 Agno `_ainvoke_stream_with_retry`，流式重试时发 SSE `run.retrying`；前端清空 partial content/tools，状态 `retrying` 并展示「第 n/m 次重试」。
- Dashboard「最近失败」跳转使用 Trace 规范 query：`session_id` / `run_id` / `selected_session` / `trace`（不再写 `session`/`run` legacy 别名）。

相关入口：

- `api/services/security_run_runtime.py`、`api/services/chat_run_events.py`
- `frontend/src/features/chat/*`、`frontend/src/features/dashboard/DashboardPage.tsx`

## 已完成：模型重试参数（Chat Completions + Responses）

- `build_agno_model` 对 DeepSeek / OpenAI Chat / OpenAI Responses / OpenAILike 统一注入 Agno `retries` / `delay_between_retries` / `exponential_backoff`，可选 SDK `max_retries`（配置键 `http_max_retries`）。
- 模型设置表单与 `model_configs` 表持久化上述字段；默认 retries=4、delay=1、exponential_backoff=true。
- 503/429 等可恢复错误由 Agno `_ainvoke_with_retry` 重试；400 等 non-retryable 不重试。

相关入口：

- `api/services/model_factory.py`、`model_config_service.py`、`api/persistence/model_configs.py`
- `frontend/src/features/settings/SettingsPage.tsx`

## 已完成：性能热路径收紧

- Chat sessions：DB 级 `page`/`limit` + SQL 归档过滤（`metadata @> agno_aios_archived`），去掉 500 窗后内存分页。
- Overview：traces 最多 5 页 ×1000（5000）采样，超出打 warning，避免 7d 全量加载。
- Trace status 过滤：扫描上限 2000 条；list root input batch 失败不再 per-trace `get_spans`（input=null）。
- Approvals submissions：`GET /api/approvals/submissions` 改为 `{data,meta}` + page/limit；前端按 offset 切片合并 HITL。
- Memory list：本已透传 Agno `page`/`limit`；stats 查询单独有界。

相关入口：

- `api/services/chat_session_service.py`、`overview_service.py`、`tracing_service.py`
- `api/persistence/upload_approvals.py`、`api/routes/approvals.py`、`frontend/src/features/approvals/api.ts`

## 已完成：可靠性 / 可观测性收紧

- overview snapshots 各子块异常改为 `logger.exception`（不再静默 `pass`），缺键仍表示该能力不可用。
- 进程 lifespan 安装 asyncio exception handler，捕获 Agno `amake_memories` 等 fire-and-forget Task 失败（含 Grok metadata 类错误）写入结构化日志。
- HITL resume：approval 缺失 / 失败后无法加载记录时增加 error 日志；既有 submitter+admin 通知路径不变。
- Knowledge SSE 入库/更新/上传增加 15 分钟 `wait_for` 超时，超时发 `progress.failed`（code 504）；阶段失败与前端 toast 路径保持。

相关入口：

- `api/services/overview_service.py`、`api/main.py`、`api/services/security_run_runtime.py`、`api/routes/knowledge.py`

## 已完成：代码卫生清理（分页 helper / 注释 / 兼容）

- 抽取共用 `api/utils/pagination.py::pagination_meta`，memory/approvals/chat/trace/evals list 去掉重复实现。
- Memory `_memory_text` 注释与「只读 `memory` 字段」实现对齐。
- 前端 `getApprovals` 去掉 `string` 状态别名兼容（仅对象参数）。
- Trace status reconcile 文档标明已是 audit `IN (...)` 批量查询（无需再改实现）。

相关入口：

- 代码：`api/utils/pagination.py`、各 `*_service.py`、`frontend/src/features/approvals/api.ts`

## 已完成：Chat sessions 列表对齐 data/meta

- `GET /api/chat/sessions` 返回 `{ data, meta }`（`page`/`limit`/`total_pages`/`total_count`/`search_time_ms`），不再直接返回数组。
- 支持可选 `page`/`limit`（默认 1/500）；归档过滤后内存分页，meta 反映过滤后总数。
- 前端 `listSessions` 解析 envelope 后仍返回 `ChatSession[]`（React Query cache 形状不变）。

相关入口：

- API：`GET /api/chat/sessions`
- 代码：`api/services/chat_session_service.py`、`api/routes/chat.py`、`frontend/src/features/chat/api.ts`

## 已完成：Trace list root input 批量加载

- `_root_inputs_for_trace_ids` 改为 spans 表 `trace_id IN (...)` 单次查询（优先 root / `parent_span_id IS NULL`），替换 list 页 per-trace `get_spans` N+1。
- 批量失败时回退到原 per-trace `get_spans`；input 仍 best-effort（可空）。
- 响应契约不变：`{data,meta}`、`duration`、可选 `input`。

相关入口：

- 代码：`api/services/tracing_service.py`（`_batch_root_spans_by_trace_ids`）
- 测试：`api/tests/test_trace_permissions.py`

## 已完成：Approvals 列表真分页

- 前端 `getApprovals({ status, page, limit })` 读 HITL `data`/`meta`，不再 `limit=100` 客户端切页。
- 表格受控分页；上传 submissions 仍全量拉取，与 HITL 按「submissions 优先」合并后分页。
- 深链 `approval_id` 不在当前页时 `GET /api/approvals/{id}` 拉详情。

相关入口：

- 代码：`frontend/src/features/approvals/api.ts`、`ApprovalsPage.tsx`

## 已完成：Approvals email/拒绝理由字段收窄

- HITL list/detail 不再输出 `submitted_by_email` / `resolved_by_email`，只 enrich `submitted_by` / `resolved_by` 对象。
- resolve 拒绝时仅写 `resolution_data.note`（不再 dual-write `rejection_reason` 键）；读路径优先 `note`，历史行仍可读旧键。
- 请求体 `rejection_reason` 与 submissions 顶层 `rejection_reason` 保留（产品表单 / 上传审批）。

相关入口：

- 代码：`api/services/approvals_service.py`、`api/routes/approvals.py`、`frontend/src/features/approvals/*`

## 已完成：Memory 字段收窄 + Trace URL 去 legacy

- Memory list 投影只认 `memory_id` / `memory` / `topics`；缺 `memory_id` 的行丢弃，不再用 `id`/`content`/`topic` 兜底。
- Trace `parseTraceSearch` 只读 `session_id`/`run_id`，忽略旧别名 `session`/`run`。

相关入口：

- 代码：`api/services/memory_service.py`、`frontend/src/features/trace/utils.ts`

## 已完成：去掉 overview pending_approvals 别名

- Dashboard / overview 仅使用 `snapshots.approvals.{pending,approved,rejected}`。
- 导航 badge 继续走 `GET /api/approvals/count`，不依赖 overview 别名。

## 已完成：Dashboard 待审批 / 已审批快照

- overview `snapshots.approvals = { pending, approved, rejected }`（不保留 `pending_approvals` 别名）。
- Dashboard 治理卡片展示 `待审批 / 已审批`，hint 含已拒绝数。
- 计数：pending 走 Agno `get_pending_approval_count`，approved/rejected 走 list total（limit=1）。

相关入口：

- API：`GET /api/overview` snapshots；`GET /api/approvals/count` 仍仅 pending（badge）
- 代码：`api/services/approvals_service.py`、`frontend/src/features/dashboard/*`

## 已完成：Approvals pending count 端点

- 新增 `GET /api/approvals/count` → Agno 风格 `{ count }`，scopes + user isolation 与列表一致。
- overview `snapshots.approvals` 复用 status counts service；侧栏 Approvals 导航用 `/api/approvals/count` badge。

相关入口：

- API：`GET /api/approvals/count`
- 代码：`api/services/approvals_service.py`、`frontend/src/features/approvals/api.ts`、`frontend/src/app/shell/AppFrame.tsx`

## 已完成：模型 structured output 标记与 API metadata 解耦

- `build_agno_model` 使用私有属性 `_tais_structured_output_mode`，不再写入 `model.metadata`。
- 避免 Grok/xAI 等 OpenAI-compatible Responses 网关因 `metadata` 参数 400；`get_request_params()` 不再携带该字段。
- 新增工厂单测：Responses/Chat 请求参数不含 `metadata`。

相关入口：

- 代码：`api/services/model_factory.py`、`api/tests/test_model_factory.py`

## 已完成：Evals 读路径对齐 Agno 分页 envelope

- `GET /api/agent-evals/agno-runs` 返回 `{ data, meta }`，行主键 `id`、载荷 `eval_data`（Agno EvalSchema 命名），去掉 list 内嵌 `items`/`trends`/`total`。
- `/trends` 仍为工作台聚合；`/failures` 仍为失败过滤 + case_run replay 关联；suites/cases/run/replay 自研不变。
- overview 快照与前端 `listRuns` 改读 `data`/`meta`；`normalizeEvalRun` 接受 `eval_data`。

相关入口：

- API：`GET /api/agent-evals/agno-runs`、`/failures`、`/trends`；suites/cases 不变
- 代码：`api/services/agent_eval_result_service.py`、`frontend/src/features/evaluations/api.ts`

## 已完成：Approvals 列表对齐 Agno 分页 envelope

- `GET /api/approvals` 返回 `{ data, meta }`（`page` / `limit` / `total_pages` / `total_count` / `search_time_ms`），去掉 workbench `module`/`metrics`/`records`/`approval_meta` 大包。
- 保留 scopes、user isolation、actor email enrich；resolve / resume / submissions 不变。
- 前端 `getApprovals` 从 `data` 读取 HITL 列表，`normalizeApproval` 统一行形状；submissions 仍走 `/api/approvals/submissions`。

相关入口：

- API：`GET /api/approvals`、`GET|POST /api/approvals/{id}`、`POST .../resolve|resume`、`/submissions*`
- 代码：`api/services/approvals_service.py`、`frontend/src/features/approvals/api.ts`

## 已完成：Trace 列表/会话对齐 Agno 分页 envelope

- `GET /api/traces` 与 `GET /api/traces/sessions` 返回 `{ data, meta }`，继续走 status reconcile。
- list/detail 对外只暴露 Agno 风格 `duration`（存储仍为 Agno `duration_ms`，API 层投影），list best-effort 附带 root `input`。
- sessions 经 `data/meta` 归一化；detail tree/spans 仍为工作台自研节点形状，但 duration 字段与 Agno 一致。

相关入口：

- API：`GET /api/traces`、`GET /api/traces/sessions`
- 代码：`api/services/tracing_service.py`、`frontend/src/features/trace/api.ts`

## 已完成：Memory 对齐 Agno 原生列表协议

- 唯一 REST 前缀：`GET/PATCH/DELETE /api/memories*`，Agno 风格 `data`/`meta` 分页 envelope。
- 已移除 `/api/memory` 工作台大包与 list dual-write；响应主键仅 `memory_id`。
- 列表查询使用 `search_content`；保留 scopes、user isolation、policy 审计。
- 前端 `normalizeMemory` 仅接受 `memory_id`，UI 内将 `id` 镜像为 `memory_id`。

相关入口：

- API：`GET /api/memories`、`PATCH|DELETE /api/memories/{memory_id}`
- 代码：`api/routes/memory.py`、`api/services/memory_service.py`、`frontend/src/features/memory/api.ts`

## 已完成：Agno 原生 HITL 与通知闭环

- 高影响工具迁入 FastMCP `hitl` namespace；仅 `hitl_*` Function 使用 Agno required approval。
- 审批、同一 session RunOutput、RunRequirement 与 `acontinue_run()` 成为唯一运行状态源；已移除 `hitl_paused_runs` 持久化与启动建表。
- 初始 Run 记录版本化运行时 metadata，审批解析后异步恢复同一 Run；启动恢复 `PAUSED` / `RUNNING` 任务，失败状态支持手动重试。
- 管理员和提交者通知通过带鉴权、游标补发的 SSE 双向推送；Chat 与 Trace 均投影同一 Run 的最终输出和状态。

## 已完成：模型并行工具调用配置

- 模型配置新增可空 `parallel_tool_calls`，数据库启动时自动补列，旧配置保持提供商默认行为。
- 设置页提供启用、禁用、留空三态；非 DeepSeek 模型的 Responses 和 Chat Completions 均可配置。
- Responses 通过 Agno `OpenAIResponses.parallel_tool_calls` 传递；Chat Completions 通过 Agno `request_params` 传递，聊天与会话摘要共用该设置。

## 已完成：Knowledge 进度与安全更新

- 创建/更新统一四阶段进度协议：`upload → parse → vectorize → cleanup`，SSE 推送短文案阶段状态。
- 前端 `DocumentDrawer` / `UpdateDocumentDrawer` 使用 Ant Design `Steps` 展示进度，处理中锁定关闭。
- 安全更新：先写入 shadow `content_id`，成功后再切换到稳定文档 ID；失败只清理 shadow，旧文档与旧向量保持可检索。
- 自动按后缀识别 Reader/Profile，支持 Markdown、TXT、JSON、CSV、代码、PDF/DOCX 同类型与跨类型替换，并保持文档 ID、可见性与选中状态。
- 成功后清理旧 managed 上传文件；后端/前端单测覆盖进度流与失败回滚路径。

相关入口：

- API：`POST /api/knowledge/documents/upload|text|file`、`/documents/{id}/update`、`/documents/{id}/update/upload`（`stream=true`）
- 代码：`api/services/knowledge_progress.py`、`knowledge_source_service.py`、`frontend/src/features/knowledge/components/UpdateProgress.tsx`

## 已完成：治理前端测试耗时

- Vitest：`css: false`、`pool: 'forks'`、`maxWorkers: 4`、`testTimeout/hookTimeout: 8s`，去掉易超时的 `timeout 90s` 外壳。
- 测试夹具：`ConfigProvider` 关闭 motion/hashed；QueryClient `retry: false` + `gcTime: 0`。
- 交互：统一 `src/test/user.ts`（`delay: null`、`pointerEventsCheck: 0`），重型页面用 `setupUser()` / 共享 `user`。
- 脚本：`bun run test`、`bun run test:profile`（verbose + 单 worker 便于定位慢用例）。
- 全量 Vitest 墙钟约 20–30s 级（此前常见 60s+ 抖动），仍可继续拆 Knowledge 等整页套件或接 Playwright E2E。

## 已完成：环境变量命名分层

- 应用配置使用 `TAIS_*` / 领域名（`POSTGRES_*`、`AUTH_*`、`MCP_*`）；`AGNO_*` 仅用于引擎耦合（如 `AGNO_DB_SCHEMA`）。
- Settings、`.env.example`、Knowledge 运行时 RAG 键、CVE skill / update lock 使用 `TAIS_*`；不保留应用侧 `AGNO_*` / `APP_*` 别名。
- 版本号仍以 `pyproject.toml` 为准；OpenAPI title / `APP_NAME` 对齐 `T.A.I.S API`；CVE 源配置文件为 `cve_sources.toml`。

## 已完成：前端 i18n 全量接入

- 按 feature 拆分命名空间：`common/auth/shell/chat/dashboard/knowledge/settings/mcp/approvals/...`（`shared/i18n/namespaces/*.json`）。
- P0：Chat、Dashboard、通用按钮/空态/Toast 文案接入 `react-i18next`。
- P1：Knowledge（含 Drawer/Progress/IngestOptions/文件校验与 Reader 说明）、Settings、MCP、Approvals。
- P1 外壳：通知中心标题/未读数/全部已读/相对时间与 `shell` 命名空间对齐。
- 通知中心：已读消息支持删除（`DELETE /api/notifications/{id}`，仅本人数据）。
- P2：Trace、Audit、CVE、Collect、Memory、Skills、Evaluations、Workflow 页面标题与主操作。
- 工程化：`formatDate`/`useFormatDate` 跟随当前 locale；测试 setup 初始化 i18n；语言切换仍由 `AppProviders` + Ant Design locale 驱动。
- 已知边界：表格列名/部分运维字段仍可保留英文；后端 `detail` 与 SSE 进度原文尚未做后端 i18n。

## P1：建立关键流程 E2E

已落地 shell / Trace / Knowledge / Approvals / Workflow / Chat cancel Playwright smoke（`frontend/e2e/*.smoke.spec.ts`）。

建议首先覆盖：

1. 登录后 Logo 跳转 `/dashboard`，侧栏不出现“运行概览”。
2. 默认展开“工作台”和“能力与数据”，权限不足时空分组消失。
3. 点击“智能体”清除 `session` 参数；点击最近对话进入指定 Session。
4. 264px/76px 侧栏切换、最近对话持久化和移动端抽屉默认状态。
5. Knowledge 创建/更新进度流和 Trace Session → Run → Span 的主路径。

测试应通过 API mock 或独立测试数据隔离运行，避免依赖开发数据库中已有的 Session 和文档。

## P2：导航与治理能力补强

- 深链进入 `/trace`、`/approvals`、`/cve` 等页面时，在默认两个分组之外自动展开当前路由所属分组。 ✅
- 决定桌面导航分组状态是否需要跨刷新持久化；移动端继续保持每次打开的可预测默认值。
- 审计能力按“导出 → 规则告警 → Webhook → SIEM”顺序评估，任何外发接口都必须包含 scope、租户/owner 边界、脱敏和审计闭环。

## 推荐实施顺序

1. 用 Knowledge 更新矩阵与 Trace 三个 Session 做数据对照，关闭剩余 P0 边界。
2. 将复现路径固化为后端 fixture、前端单测和 Playwright E2E。
3. 再处理导航深链体验；前端 Vitest 耗时治理已落地，后续按慢用例继续拆分即可。
4. 最后设计审计外部集成，避免在核心数据一致性尚未稳定时扩大数据出口。
