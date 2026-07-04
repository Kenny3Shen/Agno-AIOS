# Stat Chip as the page summary primitive

Agno AIOS uses **Stat Chip** for the compact statistics row between a page title or header and the main content. The shared implementation is `ag-stat-chip`, usually grouped by `ag-stat-strip`.

We choose this term and primitive because the affected elements are not full cards: they are short status facts, counts, URLs, or health signals that should scan quickly without competing with the main workflow panels. Pages may keep domain-specific class names such as `knowledge-stat-chip`, `mcp-summary-chip`, or `trace-stat-card`, but they should also apply `ag-stat-chip` so border radius, padding, light-mode colors, and overflow behavior remain consistent.

The design rule is: Stat Chips are compact rectangular chips with an 8px radius, single-line labels and values, and ellipsis for long values. Avoid pill-shaped summary metrics and avoid making these elements visually heavier than the page's primary panels.
