# 路线图

本文是 docs 中唯一放未来规划和未实现想法的位置。其他文档应只描述当前代码事实。

## 当前状态

仓库中没有已承诺的产品 roadmap。下面条目只是候选工作，不代表已实现行为或交付承诺。

## 候选工作

- 增加显式数据库迁移，替代只依赖懒创建 tables 的方式。
- 增加反向代理、TLS、进程托管、备份和恢复相关部署文档。
- 增加 traces、spans、audit logs 和安全数据缓存的保留策略控制。
- 增加登录、Chat、Trace、MCP、Knowledge 和 Settings 的自动化端到端 Playwright flows。
- Scheduler 路径生产化后，增加 scheduler persistence 和 worker operations 文档。
- 增加初始用户审批、role 变更和紧急访问恢复的 admin workflows。
- 增加 PostgreSQL、vector tables 和 MCP configuration 的灾难恢复 runbooks。

## 暂存区

当条目变得可执行时，把具体实现任务移动到项目 issue tracker 或 `TODOs.md`。
