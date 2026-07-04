# Stat Chip 是页面摘要基础元素

Agno AIOS 使用 **Stat Chip** 表示页面标题或 header 与主内容之间的紧凑统计行。共享实现是 `ag-stat-chip`，通常由 `ag-stat-strip` 分组。

选择这个术语和基础元素，是因为这些元素不是完整 cards：它们只是短状态事实、计数、URL 或健康信号，应当能快速扫读，且不应与主要工作面板竞争视觉重量。页面可以保留领域特定 class name，例如 `knowledge-stat-chip`、`mcp-summary-chip` 或 `trace-stat-card`，但也应应用 `ag-stat-chip`，让 border radius、padding、light-mode colors 和 overflow 行为保持一致。

设计规则是：Stat Chips 是紧凑矩形 chip，使用 8px radius，label 和 value 尽量单行展示，长值使用 ellipsis。避免 pill-shaped summary metrics，也避免让这些元素比页面主面板更重。
