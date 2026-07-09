# Frontend Modular Atomic Redesign

## Goal

Refactor the frontend page layer so large Vue single-file components become small workflow-focused modules, and repeated scoped CSS is replaced by shared UnoCSS utility-first primitives. This redesign does not preserve old page-local class names or source-contract tests that only existed to protect the previous DOM/CSS shape.

## Non-Goals

- Do not change backend APIs or payload formats.
- Do not change package dependencies or `frontend/package.json`.
- Do not rewrite the entire application shell or router.
- Do not force complex Trace timelines, tree connectors, Markdown bodies, or Element Plus deep overrides into utility class strings when semantic CSS or a focused component is clearer.

## Current Constraints

The current frontend already has a first utility-first layer:

- `frontend/uno.config.ts` defines `ag-metric-chip`, `ag-status-chip`, `ag-empty-state`, `ag-panel-header`, and related shortcuts.
- `frontend/src/components/common/MetricChip.vue`, `StatusChip.vue`, `EmptyState.vue`, and `PanelHeader.vue` are the canonical shared primitives.
- `Skills.vue` and `Workflow.vue` already consume some shared primitives and should guide the migration style.
- `Knowledge.vue` has already been split into `components/knowledge/*`; it is no longer the largest modularization target.
- Existing source-contract tests may assert old class names and should be rewritten around the new module and primitive contracts.

## Architecture

The redesign has three layers.

### 1. Atomic Presentation Layer

`frontend/uno.config.ts` owns reusable shortcuts for common visual atoms and page scaffolding. Shortcuts should use existing `--ag-*` design tokens and remain descriptive enough to read at the call site.

Add or refine shortcuts for:

- `ag-data-chip`: compact label/value chip used by metrics and metadata rows.
- `ag-status-dot`: small semantic status indicator.
- `ag-section-header`: title/subtitle/action row for inner panels.
- `ag-surface-row`: selectable row/card surface with stable spacing and border.
- `ag-field-label`: compact form label treatment.
- `ag-code-panel`: code/payload shell, not rich Markdown typography.
- `ag-empty-compact`: small empty state variant for short panels.

Avoid new one-off page aliases such as `--memory-*`, `--kn-*`, or `--trace-*` when they only mirror existing `--ag-*` tokens.

### 2. Shared Component Layer

Shared components wrap repeated structure, behavior, or accessibility. Atomic classes alone are used for simple layout and spacing; components are used where props, slots, ARIA, or state variants matter.

Add or refine:

- `SectionHeader.vue`: reusable inner section heading with optional count/status/actions.
- `DataChip.vue`: label/value display that can replace local metric/context chip markup.
- `StatusDot.vue`: status dot with semantic tone and accessible label.
- `MarkdownViewer.vue`: shared Markdown rendering surface for Chat, Skills, Memory, and Trace payloads.
- `PayloadViewer.vue`: JSON/text/Markdown viewer with copy, expand, empty state, and consistent content CSS.

Existing shared primitives remain:

- `MetricChip.vue`
- `StatusChip.vue`
- `EmptyState.vue`
- `PanelHeader.vue`
- `ResourceVisibilityTabs.vue`

`ResourceVisibilityTabs.vue` stays a component because its ARIA tab behavior, loading/disabled states, and sizing variables are clearer as a focused component than inline utilities.

### 3. Page Workflow Layer

Large pages become orchestration shells plus workflow components and composables. Page shells own route-level wiring only; child components own view-specific templates; composables own state transitions and API orchestration.

Preferred boundaries:

```text
frontend/src/components/memory/
  MemoryQueryPanel.vue
  MemoryUserQueue.vue
  MemoryListPanel.vue
  MemoryDetailPanel.vue
  MemoryEditDialog.vue

frontend/src/components/evals/
  AgentEvalsCommandBar.vue
  EvalCasesTab.vue
  EvalRunsTab.vue
  EvalFailuresTab.vue
  EvalTrendsPanel.vue
  AgentEvalDetailPanel.vue

frontend/src/components/settings/
  SettingsRuntimePanel.vue
  SettingsModelPanel.vue
  SettingsNavigationPanel.vue

frontend/src/components/workflow/
  WorkflowPalette.vue
  WorkflowCanvas.vue
  WorkflowInspector.vue
  WorkflowStepCard.vue

frontend/src/components/chat/
  ChatMessageList.vue
  ChatMessageCard.vue
  ChatComposer.vue
  ChatModelSelect.vue

frontend/src/composables/
  useMemoryWorkbenchController.ts
  useAgentEvalsWorkbench.ts
  useSettingsNavigationLayout.ts
  useChatScrollState.ts
  useChatMarkdownRenderer.ts
```

## Refactor Order

Use a phased full refactor so multiple agents can work in parallel without overlapping write sets.

### Phase 1: Shared Atomic Foundation

Write failing source-contract tests for the new shared primitive requirements. Then update `uno.config.ts`, common components, and source-contract tests. This phase is the dependency for all page refactors.

Owned files:

- `frontend/uno.config.ts`
- `frontend/src/components/common/*`
- `frontend/src/modules/*SourceContracts.test.mjs` tests that describe primitive contracts

### Phase 2: Memory And Evaluation Pages

These are high payoff and can run in parallel after Phase 1.

Memory owner:

- `frontend/src/components/MemoryControl.vue`
- `frontend/src/components/memory/*`
- `frontend/src/composables/useMemoryWorkbenchController.ts`
- `frontend/src/modules/memoryControl*.mjs`

Evaluation owner:

- `frontend/src/components/AgentEvals.vue`
- `frontend/src/components/evals/*`
- `frontend/src/composables/useAgentEvalsWorkbench.ts`
- `frontend/src/modules/agentEvalsWorkbench*`

### Phase 3: Settings And Workflow Pages

These can run in parallel after Phase 1. They should consume the same shared primitives and avoid adding new local chip/empty/header CSS.

Settings owner:

- `frontend/src/components/Settings.vue`
- `frontend/src/components/settings/*`
- `frontend/src/composables/useSettingsNavigationLayout.ts`

Workflow owner:

- `frontend/src/components/Workflow.vue`
- `frontend/src/components/workflow/*`
- `frontend/src/modules/workflowBuilder*`

### Phase 4: Chat Page

Chat is high risk because Markdown rendering, DOM enhancement, streaming, copy buttons, image zoom, model selection, and scroll behavior are interdependent. Refactor it after the shared Markdown/Payload primitives exist and after lower-risk pages prove the pattern.

Owned files:

- `frontend/src/components/Chat.vue`
- `frontend/src/components/chat/*`
- `frontend/src/composables/useChatScrollState.ts`
- `frontend/src/composables/useChatMarkdownRenderer.ts`
- tests covering message rendering, copy/zoom hooks, and scroll state source contracts

### Phase 5: Style Debt Sweep

Migrate remaining repeated chip/status/empty/header CSS from `MCP.vue`, `Dashboard.vue`, `page-workbench.css`, and Knowledge child components to shared primitives where the result is clearer.

Owned files:

- `frontend/src/components/MCP.vue`
- `frontend/src/components/Dashboard.vue`
- `frontend/src/components/knowledge/*`
- `frontend/src/styles/page-workbench.css`
- related source-contract tests

Trace should be handled conservatively: keep timeline, tree, inspector, and payload layout CSS semantic unless a focused component reduces duplication.

## Testing Strategy

Use TDD for each phase.

1. Write failing source-contract tests first.
2. Verify they fail for the expected reason.
3. Implement minimal refactor to pass.
4. Run focused tests.
5. Run frontend shell/auth/build verification.
6. Run visual verification for touched pages.

Required commands after each implemented phase:

```bash
cd frontend && bun run test:shell
cd frontend && bun run test:auth
cd frontend && bun run build
```

For UI phases, also start the app and use Playwright at 1920x1080 to screenshot touched pages. For pages with responsive layout risk, capture a narrow/mobile viewport too.

## New Contract Test Direction

Remove tests that require old local class names. Replace them with tests that enforce:

- large page shells import their extracted child components,
- page shells delegate state/API orchestration to composables,
- `uno.config.ts` exposes shared shortcuts used by common primitives,
- pages do not define duplicate local chip/status/empty/header CSS when a shared primitive exists,
- shared layout shells use `ag-page-flow`, `ag-content-panel`, `ag-workspace-panel`, and `ag-right-panel` only where semantically appropriate,
- complex content viewers use `MarkdownViewer` or `PayloadViewer` rather than repeating renderer CSS.

## Parallel Agent Plan

Use multiple agents only after Phase 1 is complete or has a stable branch-ready patch. Parallel agents must have disjoint write scopes.

Recommended worker split:

- Worker A: shared atomic foundation and tests.
- Worker B: Memory page after Worker A foundation lands.
- Worker C: Agent evaluations page after Worker A foundation lands.
- Worker D: Settings and Workflow pages after Worker A foundation lands.
- Worker E: Chat page after Markdown/Payload primitives are stable.
- Worker F: style debt sweep after high-risk pages are green.

Workers must not edit each other's owned files. Integration happens in the main session, with review after each worker result.

## Acceptance Criteria

- `MemoryControl.vue`, `AgentEvals.vue`, `Settings.vue`, `Workflow.vue`, and `Chat.vue` are reduced to orchestration shells with focused child components.
- Repeated chip/status/empty/header styles are replaced by common primitives or Uno shortcuts.
- Local scoped CSS remains only for complex layout, deep third-party overrides, Markdown/Payload content, Trace visualization, or page-specific interactions that would be less readable as utility strings.
- Old source-contract tests tied to removed class names are replaced with new modular/atomic contracts.
- Frontend test and build scripts pass.
- Playwright screenshots show no obvious layout overlap or UI regression on touched pages.
