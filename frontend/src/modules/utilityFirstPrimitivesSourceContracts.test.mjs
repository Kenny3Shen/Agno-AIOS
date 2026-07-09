import assert from "node:assert/strict"
import {
  existsSync,
  readOptionalSource,
  readSource,
  skills,
  sourcePath,
  workflow,
} from "./testSource.mjs"

const unoConfig = readSource("../uno.config.ts")
const metricChip = readOptionalSource("components/common/MetricChip.vue")
const statusChip = readOptionalSource("components/common/StatusChip.vue")
const emptyState = readOptionalSource("components/common/EmptyState.vue")
const panelHeader = readOptionalSource("components/common/PanelHeader.vue")
const dataChip = readOptionalSource("components/common/DataChip.vue")
const statusDot = readOptionalSource("components/common/StatusDot.vue")
const sectionHeader = readOptionalSource("components/common/SectionHeader.vue")
const markdownViewer = readOptionalSource("components/common/MarkdownViewer.vue")
const payloadViewer = readOptionalSource("components/common/PayloadViewer.vue")
const workflowPalette = readOptionalSource("components/workflow/WorkflowPalette.vue")
const workflowCanvas = readOptionalSource("components/workflow/WorkflowCanvas.vue")
const workflowInspector = readOptionalSource("components/workflow/WorkflowInspector.vue")
const workflowStepCard = readOptionalSource("components/workflow/WorkflowStepCard.vue")
const workflowChildren = [
  workflowPalette,
  workflowCanvas,
  workflowInspector,
  workflowStepCard,
].join("\n")

for (const shortcut of [
  "ag-metric-chip",
  "ag-metric-label",
  "ag-metric-value",
  "ag-status-chip",
  "ag-empty-state",
  "ag-panel-header",
  "ag-icon-button-compact",
  "ag-data-chip",
  "ag-status-dot",
  "ag-section-header",
  "ag-surface-row",
  "ag-field-label",
  "ag-code-panel",
  "ag-empty-compact",
]) {
  assert.match(
    unoConfig,
    new RegExp(`['"]${shortcut}['"]`),
    `UnoCSS config must expose the shared ${shortcut} shortcut`,
  )
}

for (const [name, source] of [
  ["MetricChip", metricChip],
  ["StatusChip", statusChip],
  ["EmptyState", emptyState],
  ["PanelHeader", panelHeader],
  ["DataChip", dataChip],
  ["StatusDot", statusDot],
  ["SectionHeader", sectionHeader],
  ["MarkdownViewer", markdownViewer],
  ["PayloadViewer", payloadViewer],
]) {
  assert.ok(source.length > 0, `${name}.vue must exist in components/common`)
  assert.match(source, /<script setup lang="ts">/, `${name}.vue must use typed script setup`)
}

assert.match(metricChip, /defineProps<\{[\s\S]*label: string[\s\S]*value: string \| number/, "MetricChip must accept label and value props")
assert.match(metricChip, /ag-metric-chip/, "MetricChip must consume the shared metric shortcut")
assert.match(statusChip, /ag-status-chip/, "StatusChip must consume the shared status shortcut")
assert.match(emptyState, /ag-empty-state/, "EmptyState must consume the shared empty state shortcut")
assert.match(panelHeader, /ag-panel-header/, "PanelHeader must consume the shared panel header shortcut")
assert.match(dataChip, /defineProps<\{[\s\S]*label: string[\s\S]*value: string \| number/, "DataChip must accept label and value props")
assert.match(dataChip, /ag-data-chip/, "DataChip must consume the shared data chip shortcut")
assert.match(statusDot, /ag-status-dot/, "StatusDot must consume the shared status dot shortcut")
assert.match(statusDot, /aria-label/, "StatusDot must expose an accessible label")
assert.match(sectionHeader, /ag-section-header/, "SectionHeader must consume the shared section header shortcut")
assert.match(sectionHeader, /\$slots\.actions/, "SectionHeader must provide an actions slot")
assert.match(markdownViewer, /import MarkdownIt from "markdown-it"/, "MarkdownViewer must centralize markdown-it rendering")
assert.match(markdownViewer, /v-html="renderedHtml"/, "MarkdownViewer must render markdown output through a computed value")
assert.match(payloadViewer, /import MarkdownViewer from "\.\/MarkdownViewer\.vue"/, "PayloadViewer must reuse MarkdownViewer for markdown mode")
assert.match(payloadViewer, /copyToClipboard/, "PayloadViewer must expose copy behavior")
assert.match(payloadViewer, /type PayloadViewMode = "text" \| "json" \| "markdown"/, "PayloadViewer must support text, json, and markdown modes")
assert.match(payloadViewer, /ag-code-panel/, "PayloadViewer must consume the shared code panel shortcut")
assert.match(payloadViewer, /ag-empty-compact/, "PayloadViewer must use the compact empty primitive")

assert.match(skills, /import MetricChip from "\.\/common\/MetricChip\.vue"/, "Skills page must consume MetricChip")
assert.match(skills, /import StatusChip from "\.\/common\/StatusChip\.vue"/, "Skills page must consume StatusChip")
assert.match(skills, /import EmptyState from "\.\/common\/EmptyState\.vue"/, "Skills page must consume EmptyState")
assert.doesNotMatch(skills, /\.skill-context-chip\s*\{/, "Skills page must not keep duplicated metric chip CSS")
assert.doesNotMatch(skills, /\.skills-state\s*\{/, "Skills page must not keep duplicated empty state CSS")

assert.match(workflow, /import MetricChip from "\.\/common\/MetricChip\.vue"/, "Workflow page must consume MetricChip")
assert.match(workflow, /import StatusChip from "\.\/common\/StatusChip\.vue"/, "Workflow page must consume StatusChip")
assert.match(workflowChildren, /ag-panel-header/, "Workflow page must use shared panel header utilities")
assert.doesNotMatch(workflow, /\.workflow-context-chip\s*\{/, "Workflow page must not keep duplicated metric chip CSS")

for (const componentName of [
  "WorkflowPalette",
  "WorkflowCanvas",
  "WorkflowInspector",
]) {
  assert.ok(
    existsSync(sourcePath(`components/workflow/${componentName}.vue`)),
    `Workflow page must provide components/workflow/${componentName}.vue`,
  )
  assert.match(
    workflow,
    new RegExp(`import ${componentName} from "\\./workflow/${componentName}\\.vue"`),
    `Workflow shell must import ${componentName}`,
  )
  assert.match(
    workflow,
    new RegExp(`<${componentName}\\b`),
    `Workflow shell must render ${componentName}`,
  )
}

assert.ok(
  existsSync(sourcePath("components/workflow/WorkflowStepCard.vue")),
  "Workflow page must provide components/workflow/WorkflowStepCard.vue",
)

assert.match(
  workflowCanvas,
  /import WorkflowStepCard from "\.\/WorkflowStepCard\.vue"/,
  "WorkflowCanvas must import WorkflowStepCard",
)

assert.match(
  workflowCanvas,
  /<WorkflowStepCard\b/,
  "WorkflowCanvas must render WorkflowStepCard",
)

assert.match(
  workflowChildren,
  /DataChip/,
  "Workflow child components must use DataChip for compact workflow facts",
)

assert.match(
  workflowChildren,
  /StatusDot/,
  "Workflow child components must use StatusDot for validation and runtime status",
)

assert.match(
  workflowChildren,
  /SectionHeader/,
  "Workflow child components must use SectionHeader for panel headings",
)

assert.match(
  workflowChildren,
  /PayloadViewer/,
  "Workflow inspector must use PayloadViewer for generated workflow code",
)

assert.doesNotMatch(
  workflow,
  /<aside class="workflow-palette|<main class="workflow-canvas|<article[\s\S]*workflow-board-step|<el-tabs[\s\S]*workflow-tabs/,
  "Workflow shell must delegate palette, canvas, step cards, and inspector tabs to child components",
)

assert.doesNotMatch(
  workflow,
  /\.(workflow-(config|palette-section|library-item|badge|canvas-head|flow|board-step|connector|step-copy|step-meta|branch-rail|step-actions|result-strip|output|tabs|inspector-section|editor|editor-grid|run-options|option-field|check-list|code-panel|code-head|muted))\s*\{/,
  "Workflow shell must not keep old page-local duplicate Workflow styles",
)

assert.doesNotMatch(
  workflowChildren,
  /\.(workflow-(config|palette-section|library-item|badge|canvas-head|flow|board-step|connector|step-copy|step-meta|branch-rail|step-actions|result-strip|output|tabs|inspector-section|editor|editor-grid|run-options|option-field|check-list|code-panel|code-head|muted))\s*\{/,
  "Workflow child components must use Atomic CSS/shared primitives instead of old duplicate Workflow style blocks",
)
