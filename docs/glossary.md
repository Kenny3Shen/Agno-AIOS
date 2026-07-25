# 术语

- **Chat Session**：归属于用户的一段连续对话历史；一次执行称为 **Run**。
- **Trace / Span**：一次完整执行的可观测记录及其内部操作。
- **Skill**：可按需启用并加载到运行时的本地能力包。
- **MCP Service**：通过 MCP endpoint 暴露工具的服务；**MCP Token** 用于其访问授权。
- **Knowledge Base**：可供 Agent 检索的内部文档集合，不等同于长期 **Memory**。
- **Audit Log**：安全相关用户动作的追加式记录。
- **HITL / Approval**：人机审批门闩；Agent 工具 HITL 暂停 run 直至管理员解析，上传审批则控制 Skill/MCP 入库。详见 [HITL 人机审批技术架构](./hitl.md)。
- **RunRequirement**：Agno 暂停 run 的确认/输入要求；恢复时 `confirm()` / `reject(note=...)` 后 `acontinue_run`。
- **Agent Eval / Suite / Case**：工作台「评估」中的套件与用例；跑批经 `SecurityRunRuntime` 与 Agno eval 类型（accuracy / judge / reliability / performance）。
- **Safety Eval Pack**：安全防护评估用的策展数据集版本（L1 拒答 / L2 越狱 / L3 注入与 SOC）；导入为 Eval Suite。管理员可按 `pack_id` 受控移除其数据库导入内容，保留本地数据与缓存。指标含 ASR、Refusal、Over-refusal。详见 [安全防护评估](./safety-eval.md)。
- **ASR（Attack Success Rate）**：攻击/有害请求中模型给出可操作有害内容的比例；越低越好。

