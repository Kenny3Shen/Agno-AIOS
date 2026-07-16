# 下一步工作

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
- Playbook 内容库扩充 + Executor 目录产品化  
- 角色预设（分析师 / 作者 / 审批 / 审计）  
- Skill 版本与「被引用」只读视图  
- i18n 与静默失败显性化（模型/Memory 后台错误）

---


## 已完成：Collect 源站爬虫入库

- `domain_rules` 配置站作为采集源；管理员「同步源站」爬列表页链接并解析 Markdown
- Postgres `collect_articles`；Collect 页以库检索为主，单 URL 采集仍写入库
- API：`GET /sources`、`POST /articles/search`、`GET /articles/{id}`、`POST /crawl`、`POST /parse`

相关：`collect_articles.py` / `collect_crawl_service.py` / `routes/collect.py` / `CollectPage`

---

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

仓库已安装 `@playwright/test`，但目前没有提交到仓库的 Playwright spec。手工 CLI 验证无法持续保护导航与跨页面流程。

建议首先覆盖：

1. 登录后 Logo 跳转 `/dashboard`，侧栏不出现“运行概览”。
2. 默认展开“工作台”和“能力与数据”，权限不足时空分组消失。
3. 点击“智能体”清除 `session` 参数；点击最近对话进入指定 Session。
4. 264px/76px 侧栏切换、最近对话持久化和移动端抽屉默认状态。
5. Knowledge 创建/更新进度流和 Trace Session → Run → Span 的主路径。

测试应通过 API mock 或独立测试数据隔离运行，避免依赖开发数据库中已有的 Session 和文档。

## P2：导航与治理能力补强

- 深链进入 `/trace`、`/approvals`、`/cve` 等页面时，在默认两个分组之外自动展开当前路由所属分组。
- 决定桌面导航分组状态是否需要跨刷新持久化；移动端继续保持每次打开的可预测默认值。
- 审计能力按“导出 → 规则告警 → Webhook → SIEM”顺序评估，任何外发接口都必须包含 scope、租户/owner 边界、脱敏和审计闭环。

## 推荐实施顺序

1. 用 Knowledge 更新矩阵与 Trace 三个 Session 做数据对照，关闭剩余 P0 边界。
2. 将复现路径固化为后端 fixture、前端单测和 Playwright E2E。
3. 再处理导航深链体验；前端 Vitest 耗时治理已落地，后续按慢用例继续拆分即可。
4. 最后设计审计外部集成，避免在核心数据一致性尚未稳定时扩大数据出口。
