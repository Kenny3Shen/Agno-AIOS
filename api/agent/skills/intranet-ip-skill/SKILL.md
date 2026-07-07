---
name: intranet-ip-skill
description: 查询内网 IP 地址相关资产和受攻击信息，专注于处理内网 IP 资产数据库查询、NDR 数据查询和分析报告任务。
visibility: public
---
# 基本能力

围绕 NDR 告警研判提供数据拉取、字段清洗与结论输出能力。

- `get_alarm_by_doc_id(doc_id)` 根据 doc_id 拉取告警原始数据并清洗
- `search_alarm_list(time_range_start, time_range_end, ...)` 检索告警列表

## 可执行脚本

当需要访问 NDR 平台时，优先使用脚本（通过 `get_skill_script` 执行）：

- `get_alarm.py --doc-id "<doc_id>"`
  - 说明：按 doc_id 拉取单条告警，并输出清洗后的结构化 JSON
  - 输出字段：`name`、`msg`、`cve_list`、`attacker_ip_port`、`victim_ip_port`、`payload`、`http_details` 等
- `search_alarm.py --start <epoch_ms> --end <epoch_ms> [--offset 0] [--count 1000] [--advanced "..."] [--ignore-dns] [--ignore-scan] [--ignore-attack-failed]`
  - 说明：按时间范围检索告警列表，可通过高级查询过滤
  - 输出字段：NDR 原始告警列表（JSON 数组）

## 研判 SOP（标准作业流程）

### 1. 取数

- 如果用户提供 `doc_id`：先调用 `get_alarm.py` 获取结构化告警详情
- 如果用户只给出时间范围：调用 `search_alarm.py` 获取候选告警，再提示用户选择目标 `doc_id`

### 2. 研判三步法

1. **攻击特征匹配**
	- 根据 `payload` 或 `http_details` 中的请求内容判断是否符合 `name` 或 CVE 描述
2. **响应分析**
	- `status=200` 且响应包含敏感数据或预期回显 → 可能攻击成功
	- `status=403/404/500` → 可能失败，但仍需判断是否为扫描
3. **上下文分析**
	- 结合源/目的 IP、端口、协议判断攻击意图与真实度

### 3. 输出格式

请使用 Markdown 输出，包含以下字段：

- `verdict`: 结论（真实 / 误报 / 可疑）
- `confidence`: 置信度评分（0-100）
- `analysis`: 研判过程
- `evidence`: 关键证据（如匹配的 payload 片段）
- `suggestion`: 处置建议

## 行为准则

- **依数行事**：仅基于 NDR 告警与脚本返回信息研判
- **信息不足先澄清**：缺少 doc_id 或必要上下文时先提问
- **安全合规**：不输出敏感凭据与原始密钥