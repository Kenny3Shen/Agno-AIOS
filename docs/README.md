# T.A.I.S 文档

| 文档 | 说明 | 图例（Mermaid） |
|------|------|----------------|
| [系统架构](./architecture.md) | 分层总览图、运行时数据流、仓库布局、导航外壳、Knowledge | 工作台 → FastAPI → Agno 运行时 flowchart |
| [内置 Agents 与 Agno 对齐](./agents.md) | Catalog、Team beta、Data/Deep Research、运行隔离 | Catalog ↔ Chat / Studio / Team |
| [HITL 人机审批](./hitl.md) | Agno approvals 暂停/恢复、审批中心、权限边界 | 端到端 sequence + Run 状态机 |
| [工作流编排](./workflows.md) | DSL、编译、SSE、Studio 契约与路线图 | DSL → 编译 → SSE → Trace |
| [配置与运维](./operations.md) | 环境变量、Alembic、Jobs Worker、模型策略 | API / Worker / Postgres 拓扑 |
| [安全与审计](./security.md) | JWT scopes、审计查询 | 授权边界与审计路径 |
| [安全防护评估](./safety-eval.md) | 安全测试数据集分层、指标、Agent Evals 映射，以及 Pack 导入/受控移除 | 被测链路 · L1–L3 · 单 case 判定 |
| [评估基线记录](./eval-baseline-notes.md) | 本地/预发实跑数字与 UI 对比说明 | — |
| [开发与验证](./development.md) | 前端 e2e / Vitest、后端 pytest 与门禁 | 前后端门禁流水线 |
| [术语](./glossary.md) | Session / Trace / Skill / HITL 等 | — |

架构总览图资源：`docs/assets/tais-architecture.svg` / `.png`（对外演示）；各技术页内嵌 **Mermaid** 便于 GitHub / 编辑器内联渲染与 diff。产品入口见仓库根 [README.md](../README.md)。
