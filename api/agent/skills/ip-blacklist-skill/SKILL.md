---
name: ip-blacklist-skill
description: 查询 IP/CIDR 是否命中威胁情报黑名单（FireHOL 等聚合源），用于外联 IP 研判、封禁参考与告警溯源。
metadata:
  visibility: public
---
# 基本能力

围绕公网 IP / CIDR 黑名单命中提供检索与结论输出。

- 精确匹配：查询库中是否收录某 IP 或某 CIDR 字符串
- 关键词检索：按源名称、描述模糊搜索相关条目

## 可执行脚本

优先通过 `get_skill_script` 执行：

- `scripts/ip_blacklist_intel.py --query "1.2.3.4" [--limit 10]`
  - 说明：按 IP/CIDR 或关键词检索本地黑名单库，输出结构化 JSON
  - 输出字段：`query`、`matched_total`、`hits[]`（`indicator`、`indicator_type`、`source`、`list_name`、`description`、`last_seen`）

## 研判 SOP

1. 从用户输入提取 **公网 IP 或 CIDR**（不要把内网地址当威胁情报主查询）
2. 调用脚本获取命中列表
3. 输出 Markdown：
   - `verdict`: 命中 / 未命中 / 可疑（仅部分描述相关）
   - `confidence`: 0–100
   - `hits`: 命中指标与来源
   - `suggestion`: 是否建议进一步 WHOIS/威胁情报平台交叉验证或临时封禁（需 HITL 时引导审批）

## 行为准则

- **依数行事**：仅基于库内指标；未命中不代表安全
- **内网分流**：内网 IP / NDR 告警优先 `intranet-ip-skill`
- **合规**：不输出无关隐私与凭据
