/** CEL autocomplete hints for the workflow inspector. */

export type CelHint = {
  value: string
  label: string
  detail?: string
  /** condition | loop | router | any */
  kind: 'condition' | 'loop' | 'router' | 'any'
}

export const CEL_HINTS: CelHint[] = [
  {
    value: 'input',
    label: 'input',
    detail: 'Workflow run input string',
    kind: 'any',
  },
  {
    value: 'input.contains("critical")',
    label: 'input.contains("critical")',
    detail: 'Substring check on run input',
    kind: 'condition',
  },
  {
    value: 'input.contains("high")',
    label: 'input.contains("high")',
    detail: 'Severity keyword in input',
    kind: 'condition',
  },
  {
    value: 'input.size() > 0',
    label: 'input.size() > 0',
    detail: 'Non-empty input',
    kind: 'condition',
  },
  {
    value: 'last_step_content',
    label: 'last_step_content',
    detail: 'Last step output text (loop end / selectors)',
    kind: 'loop',
  },
  {
    value: 'last_step_content.contains("DONE")',
    label: 'last_step_content.contains("DONE")',
    detail: 'Stop loop when step prints DONE',
    kind: 'loop',
  },
  {
    value: 'current_iteration',
    label: 'current_iteration',
    detail: '1-based loop iteration index',
    kind: 'loop',
  },
  {
    value: 'current_iteration >= 3',
    label: 'current_iteration >= 3',
    detail: 'End after N iterations',
    kind: 'loop',
  },
  {
    value: 'session_state',
    label: 'session_state',
    detail: 'Session state map (if set by steps)',
    kind: 'any',
  },
  {
    value:
      'input.contains("critical") ? "path_a" : (input.contains("high") ? "path_b" : "path_c")',
    label: 'severity → path_a/b/c',
    detail: 'Router selector returning choice name',
    kind: 'router',
  },
  {
    value: '"path_a"',
    label: '"path_a"',
    detail: 'Constant choice name',
    kind: 'router',
  },
]

export function celHintsFor(mode: 'condition' | 'loop' | 'router'): CelHint[] {
  return CEL_HINTS.filter((h) => h.kind === 'any' || h.kind === mode)
}

export function filterCelHints(hints: CelHint[], query: string): CelHint[] {
  const q = query.trim().toLowerCase()
  if (!q) return hints
  return hints.filter(
    (h) =>
      h.value.toLowerCase().includes(q) ||
      h.label.toLowerCase().includes(q) ||
      (h.detail ?? '').toLowerCase().includes(q)
  )
}
