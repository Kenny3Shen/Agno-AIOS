---
name: playbook-skill
description: 使用安全自动化剧本完成处置、排查与验证任务（W5 / Octomation）。
metadata:
  visibility: public
---
# 安全自动化剧本（Playbook）

通过 MCP 工具编排 SOAR 剧本：先列剧本 → 取参数 → 执行 → 查结果。默认支持平台：`w5`、`octomation`。

## MCP 工具（命名以实际挂载为准，常带 `playbook_` 前缀）

| 步骤 | 工具 | 作用 |
|------|------|------|
| 1 | `list_workflows(platform)` | 列出在线/可用剧本 |
| 2 | `get_method_params(platform, method_id)` | 拉取参数定义（必填/说明） |
| 3 | `invoke_method(platform, method_id, params?)` | 发起执行（有副作用） |
| 4 | `get_exec_result(platform, exec_id)` | 查询执行状态与输出 |

信息不足时先提 1–3 个关键澄清问题，再执行。

## 常见处置场景（内容库）

按用户意图映射到剧本选择关键词；无精确匹配时列出候选并请用户确认。

### 1. 主机/终端遏制
- **意图**：隔离主机、断网、停服、杀进程、隔离终端
- **关键词**：isolate / quarantine / containment / EDR / 主机隔离
- **必填信息**：主机标识（hostname / asset_id / agent_id）、范围、是否可回滚
- **注意**：破坏性操作应走 HITL 确认；先模拟/只读查询再执行

### 2. 账号与身份
- **意图**：禁用账号、强制下线、重置会话、吊销 Token
- **关键词**：disable user / lock account / revoke session / MFA
- **必填信息**：user_id / upn / 租户、紧急程度
- **注意**：区分临时锁定与永久禁用；记录审批人

### 3. 网络封禁
- **意图**：封 IP/域名、加黑名单、ACL/防火墙策略
- **关键词**：block ip / deny / firewall / WAF / DNS sinkhole
- **必填信息**：IOC、方向（入/出）、TTL/持续时间、设备范围
- **注意**：内网 vs 公网；误封业务地址需快速回滚剧本

### 4. 邮件与钓鱼
- **意图**：召回邮件、隔离投递、封发件人/URL
- **关键词**：phishing / purge mail / quarantine message
- **必填信息**：message_id / 发件人 / 主题时间窗、影响邮箱列表

### 5. 云资源
- **意图**：停实例、撤密钥、改安全组、快照取证
- **关键词**：disable key / stop instance / security group / snapshot
- **必填信息**：云账号/区域、resource_id、是否保留磁盘

### 6. 取证与加固（只读优先）
- **意图**：采集日志、内存/磁盘快照、基线核对
- **关键词**：forensics / collect logs / snapshot / baseline
- **注意**：优先只读工具；写操作需单独确认

### 7. 验证与收尾
- **意图**：确认 IOC 已清除、服务恢复、关闭工单
- **关键词**：verify / restore / reopen access / close ticket
- **输出**：成功/失败、关键输出字段、是否需人工复核

## 标准作业流程

1. **解析任务**：意图、目标对象、平台偏好、成功标准  
2. **选平台**：用户指定 > 环境默认 > 询问 `w5` / `octomation`  
3. **列剧本**：`list_workflows` → 按名称/描述匹配；多候选时展示 top-N  
4. **拉参数**：`get_method_params` → 校验必填；可默认参数需向用户说明  
5. **执行**：`invoke_method` → 返回 `exec_id` / 任务 ID（务必保留）  
6. **查结果**：`get_exec_result`（可轮询）→ 结构化摘要  
7. **收尾**：成功/失败、副作用、回滚建议、是否需要审批记录  

## 异常处理

| 情况 | 处理 |
|------|------|
| 平台未配置 / 鉴权失败 | 说明缺 `W5_*` 或 `OCTOMATION_*` 配置，给备选路径 |
| 参数接口不可用 | 允许人工填参；不要伪造参数 schema |
| 无匹配剧本 | 说明已检索结果，请用户改关键词或换平台 |
| 执行失败 | 展示错误/日志要点 + 下一步（重试 / 人工 / 回滚） |
| 破坏性操作 | 先确认影响面；工作流中优先 `requires_confirmation` |

## 输出模板（建议）

```markdown
### 剧本执行摘要
- 平台 / 剧本：…
- 任务 ID：…
- 状态：成功 | 失败 | 进行中
- 关键输出：…
- 建议下一步：…
```

## 与工作流编排

- Workflow 步骤绑定本 Skill 时，只暴露剧本相关工具面（配合意图/绑定过滤）。  
- 高风险 `invoke_method` 建议步骤开启「需要确认」或用户输入 schema 收集目标字段。  
- 不要在未确认的情况下对生产资产批量执行遏制类剧本。
