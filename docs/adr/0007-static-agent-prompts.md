# 由代码管理并动态加载 Agent prompts

Agno AIOS 把安全运营 Agent prompts 保存在仓库文件中，并在每次构建 Agent 时由运行时读取，而不是把长 prompt 文本嵌入 Python 代码、在模块 import 时固化，或通过控制面做在线编辑。

这样做让 prompt 变更可 review、可 test、可 version，并且容易 rollback；同时允许部署后的进程在下一次 Agent 构建时看到代码文件中的 prompt 更新。中台不提供 prompt 编辑入口或写入 API，避免把 prompt 变更变成权限、审计、越权修改和线上漂移问题。未来如果要把 prompts 移入运行时配置，必须先明确这些控制规则。
