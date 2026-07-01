## 前端

1. Trace页面中无法根据session_id进行查询，其余查询参数似乎也无法使用
2. 修复点击复制按钮出现“复制失败（请检查浏览器权限）”的问题
3. 更新Chat/MCP/SKills页面右侧内容栏的色调，与替他页面风格一致
4. SKills页面Light模式下内容栏没有边框，区分度不足
5. 删掉右侧内容栏中间的介绍，如：MCP 工具中枢（基于 FastMCP 的服务控制、访问 Token 与外部 Hi-Agent 接入）、TRACE CONSOLE Agent 观测中心（会话记录、Trace 队列、Span 瀑布与错误上下文统一查看 ），每个标签页只保留最上层即可，如：Skills （安全 Skills 模块开关）
6. Chat 页面优化，参考下面的优化方向，提升Agent对话体验：

* 自动滚动到底部
* Token Streaming 动画
* Markdown Loading Skeleton
* Code Block Copy
* Mermaid 支持
* 图片缩放
* 引用来源折叠
* Thinking Collapse
* Tool Call Timeline

---

## 后端

1. 多用户系统（P0）

目前：

所有用户共享：

Session

Chat

Trace

修改：

实现真正多用户隔离。

要求：

所有数据增加：

user_id

所有查询：

自动：

WHERE user_id = current_user

Session：

完全隔离。

用户不能：

查看：

删除：

修改：

其他用户数据。

2. RBAC 权限系统（P0）

增加：

Role：

admin

user

guest

权限：

Admin：

全部。

User：

自己的。

Guest：

只读。

采用：

RBAC。

避免：

if admin。

3. Trace 权限（P0）

Trace：

仅：

Admin：

可见。

管理员：

查看：

全部：

Trace

Session

Conversation

普通用户：

仅：

自己的：

Trace。

后台接口：

同样校验。

不要：

只隐藏菜单。

4. Session 权限（P0）

Session：

必须：

绑定：

user_id

禁止：

猜测：

Session ID。

增加：

Permission Check。

5. Audit Log（P1）

新增：

审计日志。

记录：

Login

Logout

Delete

Knowledge

MCP

Skill

Admin Operation

方便追踪。

---

## 项目结构优化

1. 清理项目（P1）

检查：

unused pages

unused hooks

unused utils

unused api

unused css

unused icons

unused assets

删除：

Dead Code。

2. 前端状态管理统一（避免页面各自维护状态）
3. 前端设计语言要统一，如

* Background
* Border
* Radius
* Padding
* Shadow

等，保持整个系统一致。

5. 引入国际化（i18n），统一中英文文案
6. 依赖升级，前后端依赖升级，删除无效依赖，使用业界最佳实现，减少重复造轮


**设计参考[docs.agno.com/agent-os/control-plane.md](https://docs.agno.com/agent-os/control-plane.md)，阅读里面的内容和图像视频，对齐设计语言，减少臃肿的表达，实现简洁的设计**
