---
name: playbook-skill
description: 使用安全自动化剧本完成处置、排查与验证任务。
metadata:
  visibility: public
---
# 基本能力

  1. `playbook_list_workflows(platform)` 获取候选剧本
  2. `playbook_get_method_params(method_id)` 获取参数定义
  3. `playbook_invoke_method(method_id, params)` 发起执行
  4. `playbook_get_exec_result(exec_id)` 获取结果
  
## 任务解析

- 能从用户描述中抽取意图、目标对象、条件与期望输出
- 能判断是否需要剧本支持（不是所有任务都要执行）
- 信息不足时先提1-3个关键澄清问题再执行

## 剧本选择

- 先调用 `list_workflows(platform: str)` 获取候选剧本
- 根据名称或描述匹配最合适的剧本
- 无匹配时向用户说明，并请求补充或改用其他平台

## 参数理解与校验

- 必须调用 `get_method_params(method_id: str)` 获取参数定义
- 对必填参数进行校验，不完整则向用户提问
- 提供默认值的参数可自行填写并说明

## 执行与结果处理

- 通过 `invoke_method(method_id: str, params: dict | None = None)` 发起执行
- 使用 `get_exec_result(exec_id: str)` 获取结果
- 结果需要结构化摘要给用户（成功/失败 + 关键输出 + 下一步建议）

## 异常处理

- 平台未实现或不可用：明确提示 + 备选方案
- 参数不足：明确列出缺失项
- 执行失败：提供日志或错误信息并建议下一步

## 注意事项

你通常需要返回 `任务ID` 以便用户后续查询执行结果。
