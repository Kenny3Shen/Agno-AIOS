# Frontend Utility-First Primitives Design

## Goal

Reduce repeated scoped CSS in low-risk frontend pages by introducing shared UnoCSS shortcuts and small reusable UI primitives.

## Scope

This first pass targets `Skills.vue` and `Workflow.vue` only. It does not restructure `Knowledge.vue`, `Chat.vue`, `MemoryControl.vue`, or the shell.

## Architecture

UnoCSS shortcuts provide shared visual primitives for page panels, workspace panels, metric chips, status chips, empty states, and icon buttons. Vue common components wrap recurring template structures where a component boundary is clearer than another CSS class. Page components keep their business logic and only replace repeated presentation markup/styles.

## Components

- `frontend/uno.config.ts`: owns reusable utility-first shortcuts.
- `frontend/src/components/common/MetricChip.vue`: renders label/value metrics with optional semantic tone.
- `frontend/src/components/common/StatusChip.vue`: renders compact status badges with optional semantic tone.
- `frontend/src/components/common/EmptyState.vue`: renders consistent loading/empty feedback.
- `frontend/src/components/common/PanelHeader.vue`: renders panel title/subtitle/action rows.
- `frontend/src/components/Skills.vue`: consumes common primitives and removes duplicated chip/state CSS.
- `frontend/src/components/Workflow.vue`: consumes common primitives and removes duplicated metric chip CSS.

## Testing

Add a frontend source-contract test that verifies the shortcuts and common components exist and that `Skills.vue` and `Workflow.vue` consume them. Run existing shell/build verification after implementation.

## Constraints

- Do not change `frontend/package.json`.
- Use existing Vue, Element Plus, and UnoCSS stack.
- Keep changes behavior-neutral.
- Do not migrate high-risk large pages in this pass.
