import { jsonInit, requestJson } from '@/shared/api/client'
import { asRecord } from '@/shared/lib/format'
import { normalizePaginatedList, type ListPaginationMeta } from '@/shared/lib/pagination'

export type EvalTargetKind = 'agent' | 'team'

/** A concrete Agno component evaluated by one Suite. */
export interface EvalTarget {
  kind: EvalTargetKind
  id: string
}

/** Server-authoritative catalog entry used by the Suite authoring selector. */
export interface EvalTargetOption extends EvalTarget {
  name: string
  description?: string
  available: boolean
  unavailable_reason?: string
}

export interface Suite {
  id: string
  name: string
  description?: string
  target: EvalTarget
  enabled: boolean
  tags: string[]
}

export type EvalType = 'accuracy' | 'agent_as_judge' | 'reliability' | 'performance'
/** Agno Case.judge_mode; numeric enables the 1–10 threshold. */
export type JudgeMode = 'binary' | 'numeric'

/** Complete, bounded configuration for one repeated Agno PerformanceEval. */
export interface EvalPerformanceConfig {
  warmup_runs: number
  num_iterations: number
  measure_runtime: boolean
  measure_memory: boolean
}

export const DEFAULT_EVAL_PERFORMANCE_CONFIG: EvalPerformanceConfig = {
  warmup_runs: 1,
  num_iterations: 3,
  measure_runtime: true,
  measure_memory: false,
}

export interface EvalCase {
  id: string
  suite_id: string
  name: string
  description?: string
  input: string
  expected_output?: string
  criteria?: string
  judge_mode: JudgeMode
  /** Ordered evaluator instructions shared by Accuracy and Agent-as-Judge checks. */
  additional_guidelines: string[]
  threshold: number
  eval_types: EvalType[]
  expected_tool_calls: string[]
  expected_tool_call_arguments: Record<string, unknown>
  allow_additional_tool_calls: boolean
  performance_config: EvalPerformanceConfig
  /** Optional Agno Case.timeout_seconds override; absent uses Suite default. */
  timeout_seconds?: number
  enabled: boolean
  metadata?: Record<string, unknown>
  tags: string[]
}

export interface EvalSuiteWrite {
  name: string
  description: string
  target: EvalTarget
  enabled: boolean
  tags: string[]
}

export type EvalSuiteUpdate = Omit<EvalSuiteWrite, 'target'>

export interface EvalCaseWrite {
  suite_id: string
  name: string
  description: string
  input: string
  expected_output: string
  criteria: string
  judge_mode: JudgeMode
  additional_guidelines: string[]
  threshold: number
  eval_types: EvalType[]
  expected_tool_calls: string[]
  expected_tool_call_arguments: Record<string, unknown>
  allow_additional_tool_calls: boolean
  performance_config: EvalPerformanceConfig
  /** Explicit null clears an existing Case timeout override. */
  timeout_seconds: number | null
  metadata: Record<string, unknown>
  tags: string[]
  enabled: boolean
}

export interface EvalRun {
  id: string
  name?: string
  eval_type?: string
  passed?: boolean | null
  score?: number
  agent_id?: string
  created_at?: string | number
  eval_data?: Record<string, unknown>
  eval_input?: Record<string, unknown>
  case_run_id?: string
  case_id?: string
  suite_run_id?: string
}

export type SafetyGateStatus = 'passed' | 'failed' | 'not_evaluated'

export interface SafetyGateCheck {
  id: string
  status: SafetyGateStatus
  actual?: number
  threshold?: number
  baseline?: number
  tolerance?: number
}

/** Machine-readable aggregate safety policy verdict persisted with a Suite run. */
export interface SafetyGate {
  version?: string
  status: SafetyGateStatus
  policy?: {
    max_over_refusal_rate?: number
    asr_regression_tolerance?: number
    refusal_regression_tolerance?: number
  }
  baseline_suite_run_id?: string
  checks: SafetyGateCheck[]
}

/** Safety metrics on suite_run.summary (docs/safety-eval.md §6 / Phase 1–2). */
export interface SafetySummary {
  pack_id?: string
  pack_version?: string
  /** SHA-256 of the imported cases.jsonl used by this run. */
  pack_cases_sha256?: string
  /** Optional fetch-manifest sampling metadata, safe to include in reports. */
  pack_sample_seed?: number
  pack_cases_count?: number
  pack_source_kind?: string
  judge_id?: string
  eval_profile?: string
  asr: number | null
  refusal_rate: number | null
  over_refusal_rate: number | null
  guardrail_trip_rate?: number | null
  n_harmful?: number
  n_benign?: number
  n_unsafe?: number
  n_refuse?: number
  n_over_refuse?: number
  n_guardrail_blocked?: number
  n_error?: number
  n_partial?: number
  n_total?: number
  gate?: SafetyGate
}

/** Safe, structured Agno ReliabilityResult evidence (never tool arguments). */
export interface ReliabilityEvidence {
  failed_tool_calls: string[]
  passed_tool_calls: string[]
  additional_tool_calls: string[]
  missing_tool_calls: string[]
  failed_argument_checks: string[]
  passed_argument_checks: string[]
}

/** Privacy-safe aggregate from Agno PerformanceEval (individual samples omitted). */
export interface PerformanceAggregate {
  avg: number
  median: number
  p95: number
}

/** Bounded execution configuration plus performance aggregates for one Case. */
export interface PerformanceEvidence {
  warmup_runs: number
  num_iterations: number
  runtime_seconds?: PerformanceAggregate
  memory_mib?: PerformanceAggregate
}

/** Privacy-safe Agno SuiteResult.cases-compatible CaseRun projection. */
export interface SuiteCaseResultLite {
  name: string
  case_id?: string
  case_run_id?: string
  session_id?: string
  duration_seconds?: number
  /** Actual per-Case timeout used for this Suite run. */
  timeout_seconds?: number
  status: string
  passed?: boolean
  skipped?: boolean
  timed_out?: boolean
  error?: string
  /** Agno AccuracyEval aggregate verdict (avg_score >= 8). */
  accuracy_passed?: boolean
  accuracy_reason?: string
  /** Average AccuracyEval score (1--10) across its iterations. */
  accuracy_score?: number
  judge_passed?: boolean
  judge_reason?: string
  /** Numeric judge score (1--10); omitted for binary/no judge checks. */
  judge_score?: number
  reliability_passed?: boolean
  reliability_evidence?: ReliabilityEvidence
  performance?: PerformanceEvidence
  judge_id?: string
  eval_profile?: string
}

export interface SuiteRunSummary {
  /** Number of Cases with a terminal result so far; updated while a SuiteRun is active. */
  completed_cases?: number
  passed?: number
  failed?: number
  errored?: number
  skipped?: number
  cancelled?: number
  /** True after an operator asks the durable worker to stop this SuiteRun. */
  cancel_requested?: boolean
  total?: number
  concurrency?: number
  /** Agno-compatible default per-Case timeout selected for this run. */
  default_timeout?: number
  /** Agno-style single-tag selector used to create this run, if any. */
  selected_tag?: string
  /** Agno-style exact Case-name selector used to create this run, if any. */
  selected_name?: string
  /** Number of cases selected before disabled cases were skipped. */
  selected_cases?: number
  /** Immutable Agent/Team identity that actually executed this Suite run. */
  target?: EvalTarget
  safety?: SafetySummary
}

/** Durable SuiteRun lifecycle returned by the asynchronous execution API. */
export type SuiteRunStatus =
  | 'queued'
  | 'running'
  | 'cancelling'
  | 'cancelled'
  | 'passed'
  | 'failed'
  | 'error'
  | 'errored'
  | 'completed'
  | 'success'
  | 'pending'

/** A run remains pollable until it reaches one of the terminal states. */
export const isActiveSuiteRun = (status: string | null | undefined): boolean => {
  const normalized = String(status ?? '').trim().toLowerCase()
  return normalized === 'queued' || normalized === 'running' || normalized === 'cancelling'
}

/** A cancellation request is meaningful only before it has already been requested. */
export const isCancellableSuiteRunStatus = (status: string | null | undefined): boolean => {
  const normalized = String(status ?? '').trim().toLowerCase()
  return normalized === 'queued' || normalized === 'running'
}

export interface SuiteRun {
  id: string
  suite_id: string
  status: SuiteRunStatus
  started_by?: string
  error_summary?: string
  summary: SuiteRunSummary
  started_at?: string | number
  completed_at?: string | number
}

/** Privacy-preserving JSON artifact for one persisted suite run. */
export interface SuiteRunReport {
  format: 'tais.eval-suite-report.v1'
  suite_run: {
    id: string
    suite_id: string
    status: string
    started_at?: string | number
    completed_at?: string | number
  }
  summary: SuiteRunSummary & { status: string }
  cases: SuiteCaseResultLite[]
  case_results_available: boolean
  privacy: {
    inputs_included: boolean
    outputs_included: boolean
    note?: string
  }
}

/** T.A.I.S case_run row (GET suite-runs/{id}/case-runs). */
export interface CaseRun {
  id: string
  suite_run_id?: string
  case_id: string
  status: string
  agent_run_id?: string
  session_id?: string
  trace_id?: string
  error_type?: string
  error_summary?: string
  replay_of_case_run_id?: string
  /** Safe result fields derived from this CaseRun's write-once checkpoint. */
  result?: SuiteCaseResultLite
  started_at?: string | number
  completed_at?: string | number
}

const RATE_PLACEHOLDER = '—'

/** Format a rate in [0,1] for UI; null/undefined/non-finite → placeholder (not fake 0). */
export const formatSafetyRate = (value: number | null | undefined, placeholder = RATE_PLACEHOLDER): string => {
  if (value == null || typeof value !== 'number' || !Number.isFinite(value)) {
    return placeholder
  }
  // Show up to 1 decimal percent for readability (0.5 → 50%, 0.125 → 12.5%)
  const pct = value * 100
  const rounded = Math.round(pct * 10) / 10
  return `${rounded % 1 === 0 ? String(Math.trunc(rounded)) : String(rounded)}%`
}

/**
 * Semantic color for safety rates.
 * - lowerIsBetter (ASR, over-refusal): green when low, red when high
 * - higherIsBetter (refusal on harmful): green when high, red when low
 */
export const safetyRateTone = (
  value: number | null | undefined,
  mode: 'lowerIsBetter' | 'higherIsBetter'
): 'success' | 'warning' | 'danger' | 'muted' => {
  if (value == null || typeof value !== 'number' || !Number.isFinite(value)) return 'muted'
  const v = Math.min(1, Math.max(0, value))
  if (mode === 'lowerIsBetter') {
    if (v <= 0.15) return 'success'
    if (v <= 0.4) return 'warning'
    return 'danger'
  }
  // higherIsBetter
  if (v >= 0.85) return 'success'
  if (v >= 0.6) return 'warning'
  return 'danger'
}

export const toneToCssColor = (tone: ReturnType<typeof safetyRateTone>): string | undefined => {
  switch (tone) {
    case 'success':
      return 'var(--ant-color-success)'
    case 'warning':
      return 'var(--ant-color-warning)'
    case 'danger':
      return 'var(--ant-color-error)'
    default:
      return undefined
  }
}

export const isSafetySuite = (suite: { tags?: unknown } | null | undefined): boolean => {
  const tags = suite?.tags
  if (!Array.isArray(tags)) return false
  return tags.some((tag) => {
    const text = String(tag).trim().toLowerCase()
    return text === 'safety' || text.startsWith('pack:')
  })
}

export interface ImportedPackIdentity {
  pack_id: string
  pack_version: string
}

/** Read the strict pack/version ownership tags written by the importer. */
export const getImportedPackIdentity = (suite: { tags?: unknown } | null | undefined): ImportedPackIdentity | undefined => {
  const tags = suite?.tags
  if (!Array.isArray(tags)) return undefined
  const packIds = new Set<string>()
  const versions = new Set<string>()
  for (const tag of tags) {
    const text = String(tag).trim()
    if (text.startsWith('pack:')) {
      const packId = text.slice('pack:'.length).trim()
      if (packId) packIds.add(packId)
    }
    if (text.startsWith('pack_version:')) {
      const version = text.slice('pack_version:'.length).trim()
      if (version) versions.add(version)
    }
  }
  if (packIds.size !== 1 || versions.size !== 1) return undefined
  const packId = [...packIds][0]
  const packVersion = [...versions][0]
  if (!packId || !packVersion) return undefined
  return {
    pack_id: packId,
    pack_version: packVersion,
  }
}

export const caseIsBenign = (metadata: Record<string, unknown> | undefined): boolean | null => {
  if (!metadata || typeof metadata !== 'object') return null
  if (typeof metadata.benign === 'boolean') return metadata.benign
  const expected = metadata.expected_behavior ?? metadata.safety_expected
  if (expected == null) return null
  const text = String(expected).trim().toLowerCase()
  if (text === 'answer' || text === 'benign_ok' || text === 'help') return true
  if (text === 'refuse' || text === 'refuse_injection') return false
  return null
}

export const caseLayer = (metadata: Record<string, unknown> | undefined): string => {
  if (!metadata || typeof metadata !== 'object') return ''
  const layer = metadata.layer
  return layer != null ? String(layer).trim() : ''
}

const parseOptionalNumber = (value: unknown): number | undefined => {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const n = Number(value)
    if (Number.isFinite(n)) return n
  }
  return undefined
}

const parseStringTags = (value: unknown): string[] => {
  if (!Array.isArray(value)) return []
  const tags: string[] = []
  const seen = new Set<string>()
  for (const raw of value) {
    const tag = String(raw ?? '').trim()
    if (tag && !seen.has(tag)) {
      tags.push(tag)
      seen.add(tag)
    }
  }
  return tags
}

const isEvalType = (value: string): value is EvalType =>
  value === 'accuracy' || value === 'agent_as_judge' || value === 'reliability' || value === 'performance'

const parseEvalTypes = (value: unknown, context: string): EvalType[] => {
  const values = parseStringTags(value).filter(isEvalType)
  if (!values.length) throw new Error(`${context}: invalid eval_types`)
  return values
}

const parseRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}

const isJsonObject = (value: unknown): value is Record<string, unknown> =>
  value != null && typeof value === 'object' && !Array.isArray(value)

const PERFORMANCE_CONFIG_FIELDS = new Set<keyof EvalPerformanceConfig>([
  'warmup_runs',
  'num_iterations',
  'measure_runtime',
  'measure_memory',
])

/**
 * Keep the browser authoring contract identical to the server's bounded
 * PerformanceEval schema.  A benchmark can make many target calls, so fail
 * locally before sending an accidental unbounded or no-op configuration.
 */
export const normalizePerformanceConfig = (value: unknown, context: string): EvalPerformanceConfig => {
  if (value != null && !isJsonObject(value)) {
    throw new Error(`${context}: performance_config must be an object`)
  }
  const raw: Record<string, unknown> = value == null ? {} : (value as Record<string, unknown>)
  const unsupported = Object.keys(raw).filter((key) => !PERFORMANCE_CONFIG_FIELDS.has(key as keyof EvalPerformanceConfig))
  if (unsupported.length) {
    throw new Error(`${context}: performance_config contains unsupported fields: ${unsupported.sort().join(', ')}`)
  }
  const integer = (field: 'warmup_runs' | 'num_iterations', minimum: number, maximum: number): number => {
    const candidate = raw[field]
    if (candidate == null) return DEFAULT_EVAL_PERFORMANCE_CONFIG[field]
    if (typeof candidate !== 'number' || !Number.isInteger(candidate) || candidate < minimum || candidate > maximum) {
      throw new Error(`${context}: performance_config.${field} must be an integer between ${minimum} and ${maximum}`)
    }
    return candidate
  }
  const boolean = (field: 'measure_runtime' | 'measure_memory'): boolean => {
    const candidate = raw[field]
    if (candidate == null) return DEFAULT_EVAL_PERFORMANCE_CONFIG[field]
    if (typeof candidate !== 'boolean') {
      throw new Error(`${context}: performance_config.${field} must be a boolean`)
    }
    return candidate
  }

  const normalized: EvalPerformanceConfig = {
    warmup_runs: integer('warmup_runs', 0, 100),
    num_iterations: integer('num_iterations', 1, 100),
    measure_runtime: boolean('measure_runtime'),
    measure_memory: boolean('measure_memory'),
  }
  if (!normalized.measure_runtime && !normalized.measure_memory) {
    throw new Error(`${context}: performance_config must enable measure_runtime or measure_memory`)
  }
  return normalized
}

const RELIABILITY_EVIDENCE_FIELDS = [
  'failed_tool_calls',
  'passed_tool_calls',
  'additional_tool_calls',
  'missing_tool_calls',
  'failed_argument_checks',
  'passed_argument_checks',
] as const satisfies readonly (keyof ReliabilityEvidence)[]

const parseReliabilityEvidenceItems = (value: unknown): string[] => {
  if (!Array.isArray(value)) return []
  const items: string[] = []
  for (const raw of value) {
    if (typeof raw !== 'string') continue
    const item = raw.trim()
    if (!item) continue
    items.push(item.length > 500 ? `${item.slice(0, 499)}…` : item)
    if (items.length >= 50) break
  }
  return items
}

const parseReliabilityEvidence = (value: unknown): ReliabilityEvidence | undefined => {
  if (!isJsonObject(value)) return undefined
  const evidence: ReliabilityEvidence = {
    failed_tool_calls: parseReliabilityEvidenceItems(value.failed_tool_calls),
    passed_tool_calls: parseReliabilityEvidenceItems(value.passed_tool_calls),
    additional_tool_calls: parseReliabilityEvidenceItems(value.additional_tool_calls),
    missing_tool_calls: parseReliabilityEvidenceItems(value.missing_tool_calls),
    failed_argument_checks: parseReliabilityEvidenceItems(value.failed_argument_checks),
    passed_argument_checks: parseReliabilityEvidenceItems(value.passed_argument_checks),
  }
  return RELIABILITY_EVIDENCE_FIELDS.some((field) => evidence[field].length) ? evidence : undefined
}

const parsePerformanceMetric = (value: unknown): number | undefined => {
  const metric = parseOptionalNumber(value)
  return metric != null && metric >= 0 ? metric : undefined
}

const parsePerformanceAggregate = (value: unknown): PerformanceAggregate | undefined => {
  if (!isJsonObject(value)) return undefined
  const avg = parsePerformanceMetric(value.avg)
  const median = parsePerformanceMetric(value.median)
  const p95 = parsePerformanceMetric(value.p95)
  if (avg == null || median == null || p95 == null) return undefined
  return { avg, median, p95 }
}

/** Parse only the compact, non-sensitive PerformanceEval evidence shape. */
const parsePerformanceEvidence = (value: unknown): PerformanceEvidence | undefined => {
  if (!isJsonObject(value)) return undefined
  const warmupRuns = parseOptionalNumber(value.warmup_runs)
  const numIterations = parseOptionalNumber(value.num_iterations)
  if (
    warmupRuns == null ||
    !Number.isInteger(warmupRuns) ||
    warmupRuns < 0 ||
    warmupRuns > 100 ||
    numIterations == null ||
    !Number.isInteger(numIterations) ||
    numIterations < 1 ||
    numIterations > 100
  ) {
    return undefined
  }
  const runtimeSeconds = parsePerformanceAggregate(value.runtime_seconds)
  const memoryMib = parsePerformanceAggregate(value.memory_mib)
  if (!runtimeSeconds && !memoryMib) return undefined
  return {
    warmup_runs: warmupRuns,
    num_iterations: numIterations,
    ...(runtimeSeconds ? { runtime_seconds: runtimeSeconds } : {}),
    ...(memoryMib ? { memory_mib: memoryMib } : {}),
  }
}

const MAX_TOOL_ARGUMENT_CONTRACT_TOOLS = 50
const MAX_TOOL_ARGUMENT_SPECS_PER_TOOL = 20
const MAX_TOOL_ARGUMENT_CONTRACT_BYTES = 32_000
const MAX_TOOL_NAME_CHARS = 160

const assertJsonValue = (value: unknown, context: string): void => {
  if (value == null || typeof value === 'string' || typeof value === 'boolean') return
  if (typeof value === 'number') {
    if (Number.isFinite(value)) return
    throw new Error(`${context}: tool argument specs must contain JSON values`)
  }
  if (Array.isArray(value)) {
    value.forEach((item) => assertJsonValue(item, context))
    return
  }
  if (isJsonObject(value)) {
    Object.values(value).forEach((item) => assertJsonValue(item, context))
    return
  }
  throw new Error(`${context}: tool argument specs must contain JSON values`)
}

const canonicalJsonObject = (value: unknown, context: string): Record<string, unknown> => {
  if (!isJsonObject(value)) {
    throw new Error(`${context}: each tool argument spec must be a JSON object`)
  }
  try {
    assertJsonValue(value, context)
    const encoded = JSON.stringify(value)
    if (!encoded) throw new Error('empty JSON')
    const decoded: unknown = JSON.parse(encoded)
    if (!isJsonObject(decoded)) throw new Error('not an object')
    return decoded
  } catch {
    throw new Error(`${context}: tool argument specs must contain JSON values`)
  }
}

/**
 * Canonicalize Agno ReliabilityEval argument-subset contracts before a Case is
 * persisted. A tool maps to one object or a non-empty list of objects; each
 * object is a subset expected on one clean execution of that tool.
 */
export const normalizeExpectedToolCallArguments = (value: unknown, context: string): Record<string, unknown> => {
  if (value == null) return {}
  if (!isJsonObject(value)) {
    throw new Error(`${context}: expected_tool_call_arguments must be a JSON object`)
  }
  const entries = Object.entries(value)
  if (entries.length > MAX_TOOL_ARGUMENT_CONTRACT_TOOLS) {
    throw new Error(`${context}: expected_tool_call_arguments supports at most ${MAX_TOOL_ARGUMENT_CONTRACT_TOOLS} tools`)
  }

  const normalized: Record<string, unknown> = {}
  for (const [rawToolName, rawSpecs] of entries) {
    const toolName = rawToolName.trim()
    if (!toolName) {
      throw new Error(`${context}: expected_tool_call_arguments tool names must not be blank`)
    }
    if (toolName.length > MAX_TOOL_NAME_CHARS) {
      throw new Error(`${context}: expected_tool_call_arguments tool names must be at most ${MAX_TOOL_NAME_CHARS} characters`)
    }
    if (toolName in normalized) {
      throw new Error(`${context}: duplicate tool names after trimming`)
    }

    const specs = Array.isArray(rawSpecs) ? rawSpecs : [rawSpecs]
    if (!specs.length) {
      throw new Error(`${context}: tool argument spec lists must not be empty`)
    }
    if (specs.length > MAX_TOOL_ARGUMENT_SPECS_PER_TOOL) {
      throw new Error(`${context}: each tool supports at most ${MAX_TOOL_ARGUMENT_SPECS_PER_TOOL} argument specs`)
    }
    const canonicalSpecs = specs.map((spec) => canonicalJsonObject(spec, context))
    normalized[toolName] = Array.isArray(rawSpecs) ? canonicalSpecs : canonicalSpecs[0]
  }

  try {
    const encoded = JSON.stringify(normalized)
    if (!encoded || new TextEncoder().encode(encoded).byteLength > MAX_TOOL_ARGUMENT_CONTRACT_BYTES) {
      throw new Error('oversized JSON')
    }
  } catch {
    throw new Error(`${context}: expected_tool_call_arguments must be valid JSON within ${MAX_TOOL_ARGUMENT_CONTRACT_BYTES} bytes`)
  }
  return normalized
}

const parseBoolean = (value: unknown, defaultValue: boolean): boolean => (typeof value === 'boolean' ? value : defaultValue)

/** Parse rate fields: missing key → null (show —); invalid non-null → null. */
const parseRateField = (value: unknown): number | null => {
  if (value == null) return null
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string' && value.trim()) {
    const n = Number(value)
    return Number.isFinite(n) ? n : null
  }
  return null
}

const isSafetyGateStatus = (value: unknown): value is SafetyGateStatus =>
  value === 'passed' || value === 'failed' || value === 'not_evaluated'

const parseSafetyGateRate = (value: unknown): number | null => {
  const rate = parseRateField(value)
  return rate != null && rate >= 0 && rate <= 1 ? rate : null
}

const parseSafetyGate = (value: unknown): SafetyGate | undefined => {
  if (value == null || typeof value !== 'object' || Array.isArray(value)) return undefined
  const row = value as Record<string, unknown>
  if (!isSafetyGateStatus(row.status)) return undefined
  const policyRaw = row.policy
  const policyRecord =
    policyRaw && typeof policyRaw === 'object' && !Array.isArray(policyRaw) ? (policyRaw as Record<string, unknown>) : undefined
  const maxOverRefusalRate = parseSafetyGateRate(policyRecord?.max_over_refusal_rate)
  const asrTolerance = parseSafetyGateRate(policyRecord?.asr_regression_tolerance)
  const refusalTolerance = parseSafetyGateRate(policyRecord?.refusal_regression_tolerance)
  const policy =
    maxOverRefusalRate == null && asrTolerance == null && refusalTolerance == null
      ? undefined
      : {
          ...(maxOverRefusalRate == null ? {} : { max_over_refusal_rate: maxOverRefusalRate }),
          ...(asrTolerance == null ? {} : { asr_regression_tolerance: asrTolerance }),
          ...(refusalTolerance == null ? {} : { refusal_regression_tolerance: refusalTolerance }),
        }
  const checks = Array.isArray(row.checks)
    ? row.checks.flatMap((rawCheck): SafetyGateCheck[] => {
        if (rawCheck == null || typeof rawCheck !== 'object' || Array.isArray(rawCheck)) return []
        const check = rawCheck as Record<string, unknown>
        const id = typeof check.id === 'string' ? check.id.trim() : ''
        if (!id || !isSafetyGateStatus(check.status)) return []
        const actual = parseSafetyGateRate(check.actual)
        const threshold = parseSafetyGateRate(check.threshold)
        const baseline = parseSafetyGateRate(check.baseline)
        const tolerance = parseSafetyGateRate(check.tolerance)
        return [
          {
            id,
            status: check.status,
            ...(actual == null ? {} : { actual }),
            ...(threshold == null ? {} : { threshold }),
            ...(baseline == null ? {} : { baseline }),
            ...(tolerance == null ? {} : { tolerance }),
          },
        ]
      })
    : []
  const baselineSuiteRunId =
    typeof row.baseline_suite_run_id === 'string' && row.baseline_suite_run_id.trim() ? row.baseline_suite_run_id.trim() : undefined
  return {
    version: typeof row.version === 'string' && row.version.trim() ? row.version.trim() : undefined,
    status: row.status,
    ...(policy ? { policy } : {}),
    ...(baselineSuiteRunId ? { baseline_suite_run_id: baselineSuiteRunId } : {}),
    checks,
  }
}

export const parseSafetySummary = (value: unknown): SafetySummary | undefined => {
  if (value == null || typeof value !== 'object' || Array.isArray(value)) return undefined
  const row = value as Record<string, unknown>
  const gate = parseSafetyGate(row.gate)
  // Require at least one known safety key so empty {} is not treated as safety block
  const keys = [
    'asr',
    'refusal_rate',
    'over_refusal_rate',
    'n_harmful',
    'n_benign',
    'pack_id',
    'pack_cases_sha256',
    'judge_id',
    'n_guardrail_blocked',
    'eval_profile',
  ]
  if (!keys.some((k) => k in row)) return undefined
  return {
    pack_id: row.pack_id != null ? String(row.pack_id) : undefined,
    pack_version: row.pack_version != null ? String(row.pack_version) : undefined,
    pack_cases_sha256: row.pack_cases_sha256 != null ? String(row.pack_cases_sha256) : undefined,
    pack_sample_seed: parseOptionalNumber(row.pack_sample_seed),
    pack_cases_count: parseOptionalNumber(row.pack_cases_count),
    pack_source_kind: row.pack_source_kind != null ? String(row.pack_source_kind) : undefined,
    judge_id: row.judge_id != null ? String(row.judge_id) : undefined,
    eval_profile: row.eval_profile != null ? String(row.eval_profile) : undefined,
    asr: parseRateField(row.asr),
    refusal_rate: parseRateField(row.refusal_rate),
    over_refusal_rate: parseRateField(row.over_refusal_rate),
    guardrail_trip_rate: parseRateField(row.guardrail_trip_rate),
    n_harmful: parseOptionalNumber(row.n_harmful),
    n_benign: parseOptionalNumber(row.n_benign),
    n_unsafe: parseOptionalNumber(row.n_unsafe),
    n_refuse: parseOptionalNumber(row.n_refuse),
    n_over_refuse: parseOptionalNumber(row.n_over_refuse),
    n_guardrail_blocked: parseOptionalNumber(row.n_guardrail_blocked),
    n_error: parseOptionalNumber(row.n_error),
    n_partial: parseOptionalNumber(row.n_partial),
    n_total: parseOptionalNumber(row.n_total),
    ...(gate ? { gate } : {}),
  }
}

/** Shorten long judge_id for table cells (full string remains in title/tooltip). */
export const formatJudgeIdShort = (judgeId: string | undefined | null, max = 28): string => {
  const text = String(judgeId ?? '').trim()
  if (!text) return RATE_PLACEHOLDER
  if (text.length <= max) return text
  return `${text.slice(0, Math.max(8, max - 1))}…`
}

const parseSuiteCaseResultLite = (value: unknown): SuiteCaseResultLite | null => {
  if (value == null || typeof value !== 'object' || Array.isArray(value)) return null
  const row = value as Record<string, unknown>
  const name = row.name != null ? String(row.name) : ''
  const status = row.status != null ? String(row.status) : ''
  if (!name && !status && row.case_id == null) return null
  return {
    name: name || String(row.case_id ?? ''),
    case_id: row.case_id != null ? String(row.case_id) : undefined,
    case_run_id: row.case_run_id != null ? String(row.case_run_id) : undefined,
    session_id: row.session_id != null ? String(row.session_id) : undefined,
    duration_seconds: parseOptionalNumber(row.duration_seconds),
    timeout_seconds: parseOptionalNumber(row.timeout_seconds),
    status,
    passed: typeof row.passed === 'boolean' ? row.passed : undefined,
    skipped: typeof row.skipped === 'boolean' ? row.skipped : undefined,
    timed_out: typeof row.timed_out === 'boolean' ? row.timed_out : undefined,
    error: row.error != null ? String(row.error) : undefined,
    accuracy_passed: typeof row.accuracy_passed === 'boolean' ? row.accuracy_passed : undefined,
    accuracy_reason: row.accuracy_reason != null ? String(row.accuracy_reason) : undefined,
    accuracy_score: parseOptionalNumber(row.accuracy_score),
    judge_passed: typeof row.judge_passed === 'boolean' ? row.judge_passed : undefined,
    judge_reason: row.judge_reason != null ? String(row.judge_reason) : undefined,
    judge_score: parseOptionalNumber(row.judge_score),
    reliability_passed: typeof row.reliability_passed === 'boolean' ? row.reliability_passed : undefined,
    reliability_evidence: parseReliabilityEvidence(row.reliability_evidence),
    performance: parsePerformanceEvidence(row.performance),
    judge_id: row.judge_id != null ? String(row.judge_id) : undefined,
    eval_profile: row.eval_profile != null ? String(row.eval_profile) : undefined,
  }
}

export const parseSuiteRunSummary = (value: unknown): SuiteRunSummary => {
  if (value == null || typeof value !== 'object' || Array.isArray(value)) {
    return {}
  }
  const row = value as Record<string, unknown>
  const safety = parseSafetySummary(row.safety)
  const target = row.target == null ? undefined : parseEvalTarget(row.target, 'suiteRunSummary.target')
  return {
    completed_cases: parseOptionalNumber(row.completed_cases),
    passed: parseOptionalNumber(row.passed),
    failed: parseOptionalNumber(row.failed),
    errored: parseOptionalNumber(row.errored),
    skipped: parseOptionalNumber(row.skipped),
    cancelled: parseOptionalNumber(row.cancelled),
    cancel_requested: typeof row.cancel_requested === 'boolean' ? row.cancel_requested : undefined,
    total: parseOptionalNumber(row.total),
    concurrency: parseOptionalNumber(row.concurrency),
    default_timeout: parseOptionalNumber(row.default_timeout),
    selected_tag: typeof row.selected_tag === 'string' && row.selected_tag.trim() ? row.selected_tag.trim() : undefined,
    selected_name: typeof row.selected_name === 'string' && row.selected_name.trim() ? row.selected_name.trim() : undefined,
    selected_cases: parseOptionalNumber(row.selected_cases),
    ...(target ? { target } : {}),
    ...(safety ? { safety } : {}),
  }
}

export const parseCaseRun = (value: unknown, context: string): CaseRun => {
  const row = asRecord(value)
  const id = String(row.id ?? '').trim()
  if (!id) throw new Error(`${context}: invalid case run payload`)
  return {
    id,
    suite_run_id: row.suite_run_id != null ? String(row.suite_run_id) : undefined,
    case_id: String(row.case_id ?? ''),
    status: row.status != null ? String(row.status) : '',
    agent_run_id: row.agent_run_id != null ? String(row.agent_run_id) : undefined,
    session_id: row.session_id != null ? String(row.session_id) : undefined,
    trace_id: row.trace_id != null ? String(row.trace_id) : undefined,
    error_type: row.error_type != null ? String(row.error_type) : undefined,
    error_summary: row.error_summary != null ? String(row.error_summary) : undefined,
    replay_of_case_run_id: row.replay_of_case_run_id != null ? String(row.replay_of_case_run_id) : undefined,
    result: row.result == null ? undefined : parseSuiteCaseResultLite(row.result) ?? undefined,
    started_at: row.started_at as string | number | undefined,
    completed_at: row.completed_at as string | number | undefined,
  }
}

/** Parse canonical suite-run rows for the UI (GET /agent-evals/suites/{id}/runs). */
export const parseSuiteRun = (value: unknown, context: string): SuiteRun => {
  const row = asRecord(value)
  const id = String(row.id ?? '').trim()
  if (!id) throw new Error(`${context}: invalid suite run payload`)
  const suiteId = String(row.suite_id ?? '').trim()
  return {
    id,
    suite_id: suiteId,
    status: String(row.status ?? '').trim().toLowerCase() as SuiteRunStatus,
    started_by: row.started_by != null ? String(row.started_by) : undefined,
    error_summary: row.error_summary != null ? String(row.error_summary) : undefined,
    summary: parseSuiteRunSummary(row.summary),
    started_at: row.started_at as string | number | undefined,
    completed_at: row.completed_at as string | number | undefined,
  }
}

/** Parse the server's stable, privacy-preserving Suite JSON export. */
export const parseSuiteRunReport = (value: unknown, context: string): SuiteRunReport => {
  const row = asRecord(value)
  if (row.format !== 'tais.eval-suite-report.v1') {
    throw new Error(`${context}: invalid suite report format`)
  }
  const suiteRun = asRecord(row.suite_run)
  const id = String(suiteRun.id ?? '').trim()
  const suiteId = String(suiteRun.suite_id ?? '').trim()
  const status = String(suiteRun.status ?? '').trim()
  const summaryRaw = asRecord(row.summary)
  const summaryStatus = String(summaryRaw.status ?? '').trim()
  const privacy = asRecord(row.privacy)
  if (!id || !suiteId || !status || !summaryStatus || typeof row.case_results_available !== 'boolean') {
    throw new Error(`${context}: invalid suite report payload`)
  }
  if (typeof privacy.inputs_included !== 'boolean' || typeof privacy.outputs_included !== 'boolean') {
    throw new Error(`${context}: invalid suite report privacy metadata`)
  }
  const cases = Array.isArray(row.cases)
    ? row.cases.map(parseSuiteCaseResultLite).filter((item): item is SuiteCaseResultLite => item != null)
    : []
  return {
    format: 'tais.eval-suite-report.v1',
    suite_run: {
      id,
      suite_id: suiteId,
      status,
      started_at: suiteRun.started_at as string | number | undefined,
      completed_at: suiteRun.completed_at as string | number | undefined,
    },
    summary: { ...parseSuiteRunSummary(summaryRaw), status: summaryStatus },
    cases,
    case_results_available: row.case_results_available,
    privacy: {
      inputs_included: privacy.inputs_included,
      outputs_included: privacy.outputs_included,
      note: privacy.note != null ? String(privacy.note) : undefined,
    },
  }
}

/** Parse canonical Agno eval-run rows for the UI. */
const parseEvalRun = (value: unknown, context: string): EvalRun => {
  const row = asRecord(value)
  const id = String(row.id ?? '').trim()
  if (!id) throw new Error(`${context}: invalid eval run payload`)
  const evalDataRaw = row.eval_data
  const evalData =
    evalDataRaw && typeof evalDataRaw === 'object' && !Array.isArray(evalDataRaw) ? (evalDataRaw as Record<string, unknown>) : undefined
  const evalInputRaw = row.eval_input
  const evalInput =
    evalInputRaw && typeof evalInputRaw === 'object' && !Array.isArray(evalInputRaw) ? (evalInputRaw as Record<string, unknown>) : undefined
  const passedRaw = row.passed
  const passed = typeof passedRaw === 'boolean' ? passedRaw : passedRaw == null ? null : undefined
  const scoreRaw = row.score
  const score = typeof scoreRaw === 'number' ? scoreRaw : typeof scoreRaw === 'string' && scoreRaw.trim() ? Number(scoreRaw) : undefined
  return {
    id,
    name: row.name != null ? String(row.name) : undefined,
    eval_type: row.eval_type != null ? String(row.eval_type) : undefined,
    passed,
    score: score != null && Number.isFinite(score) ? score : undefined,
    agent_id: row.agent_id != null ? String(row.agent_id) : undefined,
    created_at: row.created_at as string | number | undefined,
    eval_data: evalData,
    eval_input: evalInput,
    case_run_id: row.case_run_id != null ? String(row.case_run_id) : undefined,
    case_id: row.case_id != null ? String(row.case_id) : undefined,
    suite_run_id: row.suite_run_id != null ? String(row.suite_run_id) : undefined,
  }
}

const parseEvalTarget = (value: unknown, context: string): EvalTarget => {
  const row = asRecord(value)
  const kind = row.kind === 'agent' || row.kind === 'team' ? row.kind : null
  const id = typeof row.id === 'string' ? row.id.trim() : ''
  if (!kind || !id) throw new Error(`${context}: invalid eval target`)
  return { kind, id }
}

const parseEvalTargetOption = (value: unknown, context: string): EvalTargetOption => {
  const row = asRecord(value)
  const target = parseEvalTarget(row, context)
  const name = typeof row.name === 'string' ? row.name.trim() : ''
  if (!name || typeof row.available !== 'boolean') {
    throw new Error(`${context}: invalid eval target option`)
  }
  return {
    ...target,
    name,
    description: typeof row.description === 'string' && row.description.trim() ? row.description : undefined,
    available: row.available,
    unavailable_reason:
      typeof row.unavailable_reason === 'string' && row.unavailable_reason.trim()
        ? row.unavailable_reason
        : undefined,
  }
}

const parseEvalCase = (value: unknown, context: string): EvalCase => {
  const row = asRecord(value)
  const id = String(row.id ?? '').trim()
  if (!id) throw new Error(`${context}: invalid eval case payload`)
  const metadata = parseRecord(row.metadata)
  const threshold = parseOptionalNumber(row.threshold)
  const judgeMode: JudgeMode | null = row.judge_mode === 'binary' || row.judge_mode === 'numeric' ? row.judge_mode : null
  if (!judgeMode) throw new Error(`${context}: invalid judge_mode`)
  return {
    id,
    suite_id: String(row.suite_id ?? ''),
    name: String(row.name ?? ''),
    description: row.description != null ? String(row.description) : undefined,
    input: String(row.input ?? ''),
    expected_output: row.expected_output != null ? String(row.expected_output) : undefined,
    criteria: row.criteria != null ? String(row.criteria) : undefined,
    judge_mode: judgeMode,
    additional_guidelines: parseStringTags(row.additional_guidelines),
    threshold: threshold != null && threshold >= 1 && threshold <= 10 ? Math.trunc(threshold) : 7,
    eval_types: parseEvalTypes(row.eval_types, `${context}: eval_types`),
    expected_tool_calls: parseStringTags(row.expected_tool_calls),
    expected_tool_call_arguments: normalizeExpectedToolCallArguments(
      row.expected_tool_call_arguments,
      `${context}: expected_tool_call_arguments`
    ),
    allow_additional_tool_calls: parseBoolean(row.allow_additional_tool_calls, true),
    performance_config: normalizePerformanceConfig(row.performance_config, `${context}: performance_config`),
    timeout_seconds: parseOptionalNumber(row.timeout_seconds),
    enabled: parseBoolean(row.enabled, true),
    metadata: Object.keys(metadata).length ? metadata : undefined,
    tags: parseStringTags(row.tags),
  }
}

const parseSuite = (value: unknown, context: string): Suite => {
  const row = asRecord(value)
  const id = String(row.id ?? '').trim()
  const name = String(row.name ?? '').trim()
  if (!id || !name) throw new Error(`${context}: invalid eval suite payload`)
  return {
    id,
    name,
    description: row.description != null ? String(row.description) : undefined,
    target: parseEvalTarget(row.target, `${context}.target`),
    enabled: parseBoolean(row.enabled, true),
    tags: parseStringTags(row.tags),
  }
}

export interface EvalPack {
  id: string
  title: string
  layer?: string
  status: string
  suite_name?: string
  pack_version?: string
  license?: string
  tags?: string[]
  notes?: string
  importable: boolean
  has_local_cases?: boolean
}

export interface PackImportResult {
  pack_id: string
  pack_version?: string
  pack_cases_sha256?: string
  pack_sample_seed?: number
  pack_cases_count?: number
  pack_source_kind?: string
  suite_id: string
  suite_name?: string
  created_suite?: boolean
  cases_total?: number
  cases_created?: number
  cases_updated?: number
  cases_in_suite?: number
}

export interface PackRemovalResult {
  pack_id: string
  pack_version: string
  suite_ids: string[]
  suites_deleted: number
  cases_deleted: number
  suite_runs_deleted: number
  case_runs_deleted: number
}

/** Result of permanently removing an author-owned Suite and its history. */
export interface SuiteRemovalResult {
  suite_ids: string[]
  suites_deleted: number
  cases_deleted: number
  suite_runs_deleted: number
  case_runs_deleted: number
}

/** A Case definition can be removed without mutating historical Suite reports. */
export interface CaseRemovalResult {
  case_id: string
  suite_id: string
  run_history_retained: boolean
}

const parseEvalPack = (value: unknown, context: string): EvalPack => {
  const row = asRecord(value)
  const id = String(row.id ?? '').trim()
  if (!id) throw new Error(`${context}: invalid eval pack payload`)
  return {
    id,
    title: row.title != null ? String(row.title) : id,
    layer: row.layer != null ? String(row.layer) : undefined,
    status: row.status != null ? String(row.status) : '',
    suite_name: row.suite_name != null ? String(row.suite_name) : undefined,
    pack_version: row.pack_version != null ? String(row.pack_version) : undefined,
    license: row.license != null ? String(row.license) : undefined,
    tags: Array.isArray(row.tags) ? row.tags.map((t) => String(t)) : undefined,
    notes: row.notes != null ? String(row.notes) : undefined,
    importable: Boolean(row.importable),
    has_local_cases: row.has_local_cases != null ? Boolean(row.has_local_cases) : undefined,
  }
}

const parsePackImportResult = (value: unknown, context: string): PackImportResult => {
  const row = asRecord(value)
  const packId = String(row.pack_id ?? '').trim()
  const suiteId = String(row.suite_id ?? '').trim()
  if (!packId || !suiteId) throw new Error(`${context}: invalid pack import result`)
  return {
    pack_id: packId,
    pack_version: row.pack_version != null ? String(row.pack_version) : undefined,
    pack_cases_sha256: row.pack_cases_sha256 != null ? String(row.pack_cases_sha256) : undefined,
    pack_sample_seed: parseOptionalNumber(row.pack_sample_seed),
    pack_cases_count: parseOptionalNumber(row.pack_cases_count),
    pack_source_kind: row.pack_source_kind != null ? String(row.pack_source_kind) : undefined,
    suite_id: suiteId,
    suite_name: row.suite_name != null ? String(row.suite_name) : undefined,
    created_suite: row.created_suite != null ? Boolean(row.created_suite) : undefined,
    cases_total: typeof row.cases_total === 'number' ? row.cases_total : undefined,
    cases_created: typeof row.cases_created === 'number' ? row.cases_created : undefined,
    cases_updated: typeof row.cases_updated === 'number' ? row.cases_updated : undefined,
    cases_in_suite: typeof row.cases_in_suite === 'number' ? row.cases_in_suite : undefined,
  }
}

const parsePackRemovalResult = (value: unknown, context: string): PackRemovalResult => {
  const row = asRecord(value)
  const packId = String(row.pack_id ?? '').trim()
  const packVersion = String(row.pack_version ?? '').trim()
  if (!packId || !packVersion) throw new Error(`${context}: invalid pack removal result`)
  const deletionCount = (field: string) => {
    const count = parseOptionalNumber(row[field])
    if (count == null || count < 0 || !Number.isInteger(count)) {
      throw new Error(`${context}: invalid ${field}`)
    }
    return count
  }
  return {
    pack_id: packId,
    pack_version: packVersion,
    suite_ids: Array.isArray(row.suite_ids) ? row.suite_ids.map((id) => String(id)) : [],
    suites_deleted: deletionCount('suites_deleted'),
    cases_deleted: deletionCount('cases_deleted'),
    suite_runs_deleted: deletionCount('suite_runs_deleted'),
    case_runs_deleted: deletionCount('case_runs_deleted'),
  }
}

const parseSuiteRemovalResult = (value: unknown, context: string): SuiteRemovalResult => {
  const row = asRecord(value)
  const deletionCount = (field: string) => {
    const count = parseOptionalNumber(row[field])
    if (count == null || count < 0 || !Number.isInteger(count)) {
      throw new Error(`${context}: invalid ${field}`)
    }
    return count
  }
  const suiteIds = Array.isArray(row.suite_ids) ? row.suite_ids.map((id) => String(id).trim()).filter(Boolean) : []
  if (!suiteIds.length || deletionCount('suites_deleted') !== suiteIds.length) {
    throw new Error(`${context}: invalid suite deletion result`)
  }
  return {
    suite_ids: suiteIds,
    suites_deleted: suiteIds.length,
    cases_deleted: deletionCount('cases_deleted'),
    suite_runs_deleted: deletionCount('suite_runs_deleted'),
    case_runs_deleted: deletionCount('case_runs_deleted'),
  }
}

const parseCaseRemovalResult = (value: unknown, context: string): CaseRemovalResult => {
  const row = asRecord(value)
  const caseId = String(row.case_id ?? '').trim()
  const suiteId = String(row.suite_id ?? '').trim()
  if (!caseId || !suiteId || row.run_history_retained !== true) {
    throw new Error(`${context}: invalid case deletion result`)
  }
  return {
    case_id: caseId,
    suite_id: suiteId,
    run_history_retained: true,
  }
}

const requireText = (value: string, context: string, field: string): string => {
  const text = value.trim()
  if (!text) throw new Error(`${context}: ${field} is required`)
  return text
}

const normalizeSuiteWrite = (value: EvalSuiteWrite, context: string): EvalSuiteWrite => ({
  name: requireText(value.name, context, 'name'),
  description: value.description.trim(),
  target: parseEvalTarget(value.target, `${context}.target`),
  enabled: Boolean(value.enabled),
  tags: parseStringTags(value.tags),
})

const normalizeSuiteUpdate = (value: EvalSuiteUpdate, context: string): EvalSuiteUpdate => ({
  name: requireText(value.name, context, 'name'),
  description: value.description.trim(),
  enabled: Boolean(value.enabled),
  tags: parseStringTags(value.tags),
})

const normalizeCaseWrite = (value: EvalCaseWrite, context: string): EvalCaseWrite => {
  const evalTypes = Array.from(new Set(value.eval_types)).filter(isEvalType)
  if (!evalTypes.length) {
    throw new Error(`${context}: at least one eval type is required`)
  }
  const threshold = Number(value.threshold)
  if (!Number.isInteger(threshold) || threshold < 1 || threshold > 10) {
    throw new Error(`${context}: threshold must be an integer between 1 and 10`)
  }
  if (value.judge_mode !== 'binary' && value.judge_mode !== 'numeric') {
    throw new Error(`${context}: judge_mode must be binary or numeric`)
  }
  const expectedOutput = value.expected_output.trim()
  const criteria = value.criteria.trim()
  const expectedToolCalls = parseStringTags(value.expected_tool_calls)
  const expectedToolCallArguments = normalizeExpectedToolCallArguments(value.expected_tool_call_arguments, context)
  if (evalTypes.includes('agent_as_judge') && !criteria) {
    throw new Error(`${context}: agent_as_judge evals require criteria`)
  }
  if (evalTypes.includes('accuracy') && !expectedOutput) {
    throw new Error(`${context}: accuracy evals require expected_output`)
  }
  if (evalTypes.includes('reliability') && !expectedToolCalls.length) {
    throw new Error(`${context}: reliability evals require expected_tool_calls`)
  }
  const expectedTools = new Set(expectedToolCalls)
  const contractTools = Object.keys(expectedToolCallArguments).filter((tool) => !expectedTools.has(tool))
  if (contractTools.length) {
    throw new Error(`${context}: expected_tool_call_arguments keys must be included in expected_tool_calls`)
  }
  const timeout = value.timeout_seconds
  if (timeout != null && (!Number.isInteger(timeout) || timeout < 1 || timeout > 3600)) {
    throw new Error(`${context}: timeout_seconds must be an integer between 1 and 3600`)
  }
  return {
    suite_id: requireText(value.suite_id, context, 'suite_id'),
    name: requireText(value.name, context, 'name'),
    description: value.description.trim(),
    input: requireText(value.input, context, 'input'),
    expected_output: expectedOutput,
    criteria,
    judge_mode: value.judge_mode,
    additional_guidelines: parseStringTags(value.additional_guidelines),
    threshold,
    eval_types: evalTypes,
    expected_tool_calls: expectedToolCalls,
    expected_tool_call_arguments: expectedToolCallArguments,
    allow_additional_tool_calls: Boolean(value.allow_additional_tool_calls),
    performance_config: normalizePerformanceConfig(value.performance_config, context),
    timeout_seconds: timeout == null ? null : timeout,
    metadata: parseRecord(value.metadata),
    tags: parseStringTags(value.tags),
    enabled: Boolean(value.enabled),
  }
}

export const listSuites = async (): Promise<Suite[]> => {
  const payload = await requestJson<{ data?: unknown[] }>('/agent-evals/suites')
  const rows = Array.isArray(payload.data) ? payload.data : []
  return rows.map((item, index) => parseSuite(item, `listSuites[${index}]`))
}

export const createSuite = async (value: EvalSuiteWrite): Promise<Suite> => {
  const payload = await requestJson<unknown>('/agent-evals/suites', jsonInit('POST', normalizeSuiteWrite(value, 'createSuite')))
  return parseSuite(payload, 'createSuite')
}

export const updateSuite = async (suiteId: string, value: EvalSuiteUpdate): Promise<Suite> => {
  const id = requireText(suiteId, 'updateSuite', 'suite_id')
  const payload = await requestJson<unknown>(
    `/agent-evals/suites/${encodeURIComponent(id)}`,
    jsonInit('PATCH', normalizeSuiteUpdate(value, 'updateSuite'))
  )
  return parseSuite(payload, 'updateSuite')
}

export const listEvalTargets = async (): Promise<EvalTargetOption[]> => {
  const payload = await requestJson<{ data?: unknown[] }>('/agent-evals/targets')
  const rows = Array.isArray(payload.data) ? payload.data : []
  return rows.map((item, index) => parseEvalTargetOption(item, `listEvalTargets[${index}]`))
}

export const deleteSuite = async (suiteId: string): Promise<SuiteRemovalResult> => {
  const id = requireText(suiteId, 'deleteSuite', 'suite_id')
  const payload = await requestJson<unknown>(`/agent-evals/suites/${encodeURIComponent(id)}`, { method: 'DELETE' })
  return parseSuiteRemovalResult(payload, 'deleteSuite')
}

export const listPacks = async (params: { readyOnly?: boolean } = {}): Promise<EvalPack[]> => {
  const readyOnly = params.readyOnly !== false
  const search = new URLSearchParams({
    ready_only: readyOnly ? 'true' : 'false',
  })
  const payload = await requestJson<{ data?: unknown[] }>(`/agent-evals/packs?${search}`)
  const rows = Array.isArray(payload.data) ? payload.data : []
  return rows.map((item, index) => parseEvalPack(item, `listPacks[${index}]`))
}

export const importPack = async (packId: string, packVersion = ''): Promise<PackImportResult> => {
  const id = packId.trim()
  if (!id) throw new Error('importPack: pack_id is required')
  const body: Record<string, string> = { pack_id: id }
  if (packVersion.trim()) body.pack_version = packVersion.trim()
  const payload = await requestJson<unknown>('/agent-evals/packs/import', jsonInit('POST', body))
  return parsePackImportResult(payload, 'importPack')
}

export const removePack = async (packId: string, packVersion: string): Promise<PackRemovalResult> => {
  const id = packId.trim()
  if (!id) throw new Error('removePack: pack_id is required')
  const version = packVersion.trim()
  if (!version) throw new Error('removePack: pack_version is required')
  const search = new URLSearchParams({ pack_version: version }).toString()
  const payload = await requestJson<unknown>(`/agent-evals/packs/${encodeURIComponent(id)}?${search}`, { method: 'DELETE' })
  return parsePackRemovalResult(payload, 'removePack')
}

export const listCases = async (
  suite = '',
  params: { tag?: string; name?: string; page?: number; limit?: number } = {}
): Promise<EvalCaseListResult> => {
  const search = new URLSearchParams()
  if (suite.trim()) search.set('suite_id', suite.trim())
  const tag = params.tag?.trim()
  if (tag) search.set('tag', tag)
  const name = params.name?.trim()
  if (name) search.set('name', name)
  const page = Math.max(1, params.page ?? 1)
  const limit = Math.min(100, Math.max(1, params.limit ?? 50))
  search.set('page', String(page))
  search.set('limit', String(limit))
  const path = `/agent-evals/cases${search.size ? `?${search}` : ''}`
  const payload = await requestJson<unknown>(path)
  return normalizePaginatedList(payload, {
    mapItem: (item) => parseEvalCase(item, 'listCases'),
  })
}

export const createCase = async (value: EvalCaseWrite): Promise<EvalCase> => {
  const payload = await requestJson<unknown>('/agent-evals/cases', jsonInit('POST', normalizeCaseWrite(value, 'createCase')))
  return parseEvalCase(payload, 'createCase')
}

export const updateCase = async (caseId: string, value: EvalCaseWrite): Promise<EvalCase> => {
  const id = requireText(caseId, 'updateCase', 'case_id')
  const payload = await requestJson<unknown>(
    `/agent-evals/cases/${encodeURIComponent(id)}`,
    jsonInit('PATCH', normalizeCaseWrite(value, 'updateCase'))
  )
  return parseEvalCase(payload, 'updateCase')
}

export const deleteCase = async (caseId: string): Promise<CaseRemovalResult> => {
  const id = requireText(caseId, 'deleteCase', 'case_id')
  const payload = await requestJson<unknown>(`/agent-evals/cases/${encodeURIComponent(id)}`, { method: 'DELETE' })
  return parseCaseRemovalResult(payload, 'deleteCase')
}

export const updateCaseTags = async (caseId: string, tags: string[]): Promise<EvalCase> => {
  const id = caseId.trim()
  if (!id) throw new Error('updateCaseTags: case id is required')
  const payload = await requestJson<unknown>(
    `/agent-evals/cases/${encodeURIComponent(id)}`,
    jsonInit('PATCH', { tags: parseStringTags(tags) })
  )
  return parseEvalCase(payload, 'updateCaseTags')
}

type EvalListMeta = ListPaginationMeta

type EvalListResult = {
  data: EvalRun[]
  meta: EvalListMeta
}

export type EvalCaseListResult = {
  data: EvalCase[]
  meta: EvalListMeta
}

export type SuiteRunListResult = {
  data: SuiteRun[]
  meta: EvalListMeta
}

export const listRuns = async (params: { page?: number; limit?: number } = {}): Promise<EvalListResult> => {
  const page = Math.max(1, params.page ?? 1)
  const limit = Math.min(100, Math.max(1, params.limit ?? 20))
  const search = new URLSearchParams({
    page: String(page),
    limit: String(limit),
  })
  const payload = await requestJson<unknown>(`/agent-evals/agno-runs?${search}`)
  return normalizePaginatedList(payload, {
    mapItem: (item) => parseEvalRun(item, 'listRuns'),
  })
}

export const listSuiteRuns = async (suiteId: string, params: { page?: number; limit?: number } = {}): Promise<SuiteRunListResult> => {
  const id = suiteId.trim()
  if (!id) {
    return {
      data: [],
      meta: {
        page: 1,
        limit: params.limit ?? 20,
        total_count: 0,
        total_pages: 0,
        search_time_ms: 0,
      },
    }
  }
  const page = Math.max(1, params.page ?? 1)
  const limit = Math.min(100, Math.max(1, params.limit ?? 20))
  const search = new URLSearchParams({
    page: String(page),
    limit: String(limit),
  })
  const payload = await requestJson<unknown>(`/agent-evals/suites/${encodeURIComponent(id)}/runs?${search}`)
  return normalizePaginatedList(payload, {
    mapItem: (item) => parseSuiteRun(item, 'listSuiteRuns'),
  })
}

export type CaseRunListResult = {
  data: CaseRun[]
  meta: EvalListMeta
}

/** Case runs for one suite run (drill-down from Suite runs table). */
export const listSuiteRunCaseRuns = async (
  suiteRunId: string,
  params: { page?: number; limit?: number } = {}
): Promise<CaseRunListResult> => {
  const id = suiteRunId.trim()
  if (!id) {
    return {
      data: [],
      meta: {
        page: 1,
        limit: params.limit ?? 50,
        total_count: 0,
        total_pages: 0,
        search_time_ms: 0,
      },
    }
  }
  const page = Math.max(1, params.page ?? 1)
  const limit = Math.min(100, Math.max(1, params.limit ?? 50))
  const search = new URLSearchParams({
    page: String(page),
    limit: String(limit),
  })
  const payload = await requestJson<unknown>(`/agent-evals/suite-runs/${encodeURIComponent(id)}/case-runs?${search}`)
  return normalizePaginatedList(payload, {
    mapItem: (item) => parseCaseRun(item, 'listSuiteRunCaseRuns'),
  })
}

/** Export an audited, privacy-preserving JSON report for CI or review. */
export const exportSuiteRunReport = async (suiteRunId: string): Promise<SuiteRunReport> => {
  const id = suiteRunId.trim()
  if (!id) throw new Error('exportSuiteRunReport: suite run id is required')
  const payload = await requestJson<unknown>(`/agent-evals/suite-runs/${encodeURIComponent(id)}/report`, { method: 'POST' })
  return parseSuiteRunReport(payload, 'exportSuiteRunReport')
}

export const listFailures = async (params: { limit?: number } = {}): Promise<EvalRun[]> => {
  const limit = Math.min(100, Math.max(1, params.limit ?? 50))
  const raw = await requestJson<unknown>(`/agent-evals/failures?limit=${limit}`)
  const { data } = normalizePaginatedList(raw, {
    mapItem: (item) => parseEvalRun(item, 'listFailures'),
  })
  return data
}

export const runSuite = async (id: string, options: { tag?: string; name?: string; defaultTimeout?: number } = {}): Promise<SuiteRun> => {
  const suiteId = id.trim()
  if (!suiteId) throw new Error('runSuite: suite id is required')
  const tag = options.tag?.trim()
  const name = options.name?.trim()
  if (options.tag != null && !tag) throw new Error('runSuite: tag must not be blank')
  if (options.name != null && !name) throw new Error('runSuite: name must not be blank')
  if (tag && name) throw new Error('runSuite: tag and name are mutually exclusive')
  const defaultTimeout = options.defaultTimeout
  if (defaultTimeout != null && (!Number.isInteger(defaultTimeout) || defaultTimeout < 1 || defaultTimeout > 3600)) {
    throw new Error('runSuite: defaultTimeout must be an integer between 1 and 3600')
  }
  const body: Record<string, string | number> | undefined =
    tag || name || defaultTimeout != null
      ? {
          ...(tag ? { tag } : {}),
          ...(name ? { name } : {}),
          ...(defaultTimeout != null ? { default_timeout: defaultTimeout } : {}),
        }
      : undefined
  const payload = await requestJson<unknown>(
    `/agent-evals/suites/${encodeURIComponent(suiteId)}/runs`,
    body ? jsonInit('POST', body) : { method: 'POST' }
  )
  return parseSuiteRun(payload, 'runSuite')
}

/** Request cooperative cancellation for a queued or active durable SuiteRun. */
export const cancelSuiteRun = async (suiteRunId: string): Promise<SuiteRun> => {
  const id = suiteRunId.trim()
  if (!id) throw new Error('cancelSuiteRun: suite run id is required')
  const payload = await requestJson<unknown>(`/agent-evals/suite-runs/${encodeURIComponent(id)}/cancel`, { method: 'POST' })
  return parseSuiteRun(payload, 'cancelSuiteRun')
}

export const runCase = (id: string) =>
  requestJson(`/agent-evals/cases/${encodeURIComponent(id)}/runs`, {
    method: 'POST',
  })

export const replay = (id: string) =>
  requestJson(`/agent-evals/case-runs/${encodeURIComponent(id)}/replay`, {
    method: 'POST',
  })

/** Status tag color for suite-run rows. */
export const suiteRunStatusColor = (status: string | undefined): 'success' | 'error' | 'processing' | 'default' => {
  const s = String(status || '').toLowerCase()
  if (s === 'passed' || s === 'completed' || s === 'success') return 'success'
  if (s === 'failed' || s === 'error' || s === 'errored') return 'error'
  if (s === 'running' || s === 'queued' || s === 'cancelling' || s === 'pending') return 'processing'
  return 'default'
}

/** One-line safety metrics for toast / summary strip. */
export const formatSafetySummaryLine = (
  safety: SafetySummary | undefined,
  counts?: { passed?: number; failed?: number; errored?: number }
): string => {
  const parts: string[] = []
  if (counts) {
    const p = counts.passed ?? 0
    const f = counts.failed ?? 0
    const e = counts.errored ?? 0
    parts.push(`✓${p} ✗${f}${e ? ` !${e}` : ''}`)
  }
  if (safety) {
    parts.push(`ASR ${formatSafetyRate(safety.asr)}`)
    parts.push(`Ref ${formatSafetyRate(safety.refusal_rate)}`)
    parts.push(`OR ${formatSafetyRate(safety.over_refusal_rate)}`)
    if (safety.n_guardrail_blocked != null && safety.n_guardrail_blocked > 0) {
      parts.push(`GR ${safety.n_guardrail_blocked}`)
    }
  }
  return parts.join(' · ') || '—'
}

/** Latest suite run with a safety block, else first row. */
export const pickLatestSafetyRun = (runs: SuiteRun[] | undefined): SuiteRun | undefined => {
  if (!runs?.length) return undefined
  const withSafety = runs.find((r) => r.summary.safety != null)
  return withSafety ?? runs[0]
}

export type SafetyMetricDelta = {
  key: 'asr' | 'refusal_rate' | 'over_refusal_rate' | 'n_guardrail_blocked'
  /** current − baseline; null if either side missing */
  delta: number | null
  current: number | null
  baseline: number | null
  /** For rates: lowerIsBetter / higherIsBetter; guardrail: lowerIsBetter count */
  mode: 'lowerIsBetter' | 'higherIsBetter'
}

/** current − baseline for safety rates/counts (null-safe). */
export const diffSafetyMetrics = (current: SafetySummary | undefined, baseline: SafetySummary | undefined): SafetyMetricDelta[] => {
  const pair = (key: SafetyMetricDelta['key'], mode: SafetyMetricDelta['mode']): SafetyMetricDelta => {
    const c = current?.[key]
    const b = baseline?.[key]
    const cur = typeof c === 'number' && Number.isFinite(c) ? c : null
    const base = typeof b === 'number' && Number.isFinite(b) ? b : null
    return {
      key,
      mode,
      current: cur,
      baseline: base,
      delta: cur != null && base != null ? cur - base : null,
    }
  }
  return [
    pair('asr', 'lowerIsBetter'),
    pair('refusal_rate', 'higherIsBetter'),
    pair('over_refusal_rate', 'lowerIsBetter'),
    pair('n_guardrail_blocked', 'lowerIsBetter'),
  ]
}

/** Format signed delta for rates (pp) or integer counts. */
export const formatMetricDelta = (delta: number | null | undefined, kind: 'rate' | 'count' = 'rate'): string => {
  if (delta == null || typeof delta !== 'number' || !Number.isFinite(delta)) return RATE_PLACEHOLDER
  if (kind === 'count') {
    const n = Math.round(delta)
    if (n === 0) return '0'
    return n > 0 ? `+${n}` : String(n)
  }
  // percentage points (e.g. 0.1 → +10pp)
  const pp = Math.round(delta * 1000) / 10
  if (pp === 0) return '0pp'
  const text = `${pp % 1 === 0 ? String(Math.trunc(pp)) : String(pp)}pp`
  return pp > 0 ? `+${text}` : text
}

/** Whether a delta is an improvement given metric mode. */
export const deltaIsImprovement = (delta: number | null | undefined, mode: 'lowerIsBetter' | 'higherIsBetter'): boolean | null => {
  if (delta == null || typeof delta !== 'number' || !Number.isFinite(delta) || delta === 0) {
    return null
  }
  if (mode === 'lowerIsBetter') return delta < 0
  return delta > 0
}

/** Mask sensitive/harmful prompts for list view (compliance). */
export const maskSensitiveInput = (input: string, visible = 24): string => {
  const text = String(input ?? '').trim()
  if (!text) return RATE_PLACEHOLDER
  if (text.length <= visible) return `${text.slice(0, Math.max(4, Math.floor(text.length / 2)))}…`
  return `${text.slice(0, visible)}…`
}

/** Whether case input should be masked by default in the cases table. */
export const caseInputShouldMask = (metadata: Record<string, unknown> | undefined): boolean => {
  const benign = caseIsBenign(metadata)
  if (benign === true) return false
  // harmful, unknown, or guardrail probes → mask
  return true
}
