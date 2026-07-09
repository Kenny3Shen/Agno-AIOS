import assert from "node:assert/strict"
import {
  readOptionalSource,
  readSource,
  skills,
  workflow,
} from "./testSource.mjs"

const unoConfig = readSource("../uno.config.ts")
const metricChip = readOptionalSource("components/common/MetricChip.vue")
const statusChip = readOptionalSource("components/common/StatusChip.vue")
const emptyState = readOptionalSource("components/common/EmptyState.vue")
const panelHeader = readOptionalSource("components/common/PanelHeader.vue")

for (const shortcut of [
  "ag-metric-chip",
  "ag-metric-label",
  "ag-metric-value",
  "ag-status-chip",
  "ag-empty-state",
  "ag-panel-header",
  "ag-icon-button-compact",
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
]) {
  assert.ok(source.length > 0, `${name}.vue must exist in components/common`)
  assert.match(source, /<script setup lang="ts">/, `${name}.vue must use typed script setup`)
}

assert.match(metricChip, /defineProps<\{[\s\S]*label: string[\s\S]*value: string \| number/, "MetricChip must accept label and value props")
assert.match(metricChip, /ag-metric-chip/, "MetricChip must consume the shared metric shortcut")
assert.match(statusChip, /ag-status-chip/, "StatusChip must consume the shared status shortcut")
assert.match(emptyState, /ag-empty-state/, "EmptyState must consume the shared empty state shortcut")
assert.match(panelHeader, /ag-panel-header/, "PanelHeader must consume the shared panel header shortcut")

assert.match(skills, /import MetricChip from "\.\/common\/MetricChip\.vue"/, "Skills page must consume MetricChip")
assert.match(skills, /import StatusChip from "\.\/common\/StatusChip\.vue"/, "Skills page must consume StatusChip")
assert.match(skills, /import EmptyState from "\.\/common\/EmptyState\.vue"/, "Skills page must consume EmptyState")
assert.doesNotMatch(skills, /\.skill-context-chip\s*\{/, "Skills page must not keep duplicated metric chip CSS")
assert.doesNotMatch(skills, /\.skills-state\s*\{/, "Skills page must not keep duplicated empty state CSS")

assert.match(workflow, /import MetricChip from "\.\/common\/MetricChip\.vue"/, "Workflow page must consume MetricChip")
assert.match(workflow, /import StatusChip from "\.\/common\/StatusChip\.vue"/, "Workflow page must consume StatusChip")
assert.match(workflow, /ag-panel-header/, "Workflow page must use shared panel header utilities")
assert.doesNotMatch(workflow, /\.workflow-context-chip\s*\{/, "Workflow page must not keep duplicated metric chip CSS")
