export type WorkflowStepKind = "step" | "steps" | "condition" | "loop" | "router" | "parallel"
export type WorkflowExecutorType = "agent" | "team" | "function" | "workflow"

export interface WorkflowStepDraft {
  id: string
  kind: WorkflowStepKind
  executor: WorkflowExecutorType
  name: string
  symbol: string
  description: string
  expression: string
  maxIterations: number
  branches: number
}

export interface WorkflowCodeOptions {
  name: string
  description: string
  input: string
  steps: WorkflowStepDraft[]
  streamEvents: boolean
  storeEvents: boolean
  addWorkflowHistoryToSteps: boolean
}

const constructorNames: Record<WorkflowStepKind, string> = {
  step: "Step",
  steps: "Steps",
  condition: "Condition",
  loop: "Loop",
  router: "Router",
  parallel: "Parallel",
}

export function constructorName(kind: WorkflowStepKind) {
  return constructorNames[kind]
}

export function normalizePythonIdentifier(value: string, fallback = "step") {
  const identifier = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "")

  if (!identifier) return fallback
  if (/^[0-9]/.test(identifier)) return `${fallback}_${identifier}`
  return identifier
}

export function workflowStepSymbol(step: Pick<WorkflowStepDraft, "id" | "name" | "symbol">) {
  return normalizePythonIdentifier(step.symbol || step.id || step.name, normalizePythonIdentifier(step.id || "step"))
}

export function workflowNameSymbol(name: string) {
  return normalizePythonIdentifier(name, "workflow")
}

export function buildWorkflowCode(options: WorkflowCodeOptions) {
  const imports = new Set(["Workflow", "Step"])
  options.steps.forEach((step) => {
    if (step.kind !== "step") imports.add(constructorName(step.kind))
  })

  const workflowArgs = [
    `    name=${quote(options.name || "security_research_workflow")},`,
    `    description=${quote(options.description)},`,
    "    db=workflow_db,",
    "    steps=[",
    options.steps.map((step) => indent(renderStep(step), 8)).join(",\n"),
    "    ],",
  ]

  if (options.storeEvents) workflowArgs.push("    store_events=True,")
  if (options.addWorkflowHistoryToSteps) workflowArgs.push("    add_workflow_history_to_steps=True,")

  return [
    `from agno.workflow import ${Array.from(imports).join(", ")}`,
    "",
    "# Define agents, teams, executors, nested workflows, and workflow_db above this block.",
    "workflow = Workflow(",
    ...workflowArgs,
    ")",
    "",
    "workflow.print_response(",
    `    input=${quote(options.input)},`,
    "    markdown=True,",
    "    stream=True,",
    `    stream_events=${options.streamEvents ? "True" : "False"},`,
    ")",
  ].join("\n")
}

function renderStep(step: WorkflowStepDraft): string {
  if (step.kind === "step") {
    return `Step(name=${quote(displayName(step))}, ${executorArgument(step)}, description=${quote(step.description)})`
  }

  const children = Array.from({ length: step.branches }, (_, index) => {
    const symbol = workflowStepSymbol(step)
    return `Step(name=${quote(`${displayName(step)} branch ${index + 1}`)}, ${executorArgument(step, `${symbol}_${index + 1}`)})`
  })

  if (step.kind === "parallel") {
    return `Parallel(\n${indent(children.join(",\n"), 4)},\n    name=${quote(displayName(step))},\n    description=${quote(step.description)},\n)`
  }

  if (step.kind === "steps") {
    return `Steps(\n    name=${quote(displayName(step))},\n    steps=[\n${indent(children.join(",\n"), 8)},\n    ],\n    description=${quote(step.description)},\n)`
  }

  if (step.kind === "condition") {
    const [truthy, fallback] = children
    return `Condition(\n    name=${quote(displayName(step))},\n    evaluator=${quote(step.expression || "last_step_content.contains('critical')")},\n    steps=[${truthy}],\n    else_steps=[${fallback || truthy}],\n    description=${quote(step.description)},\n)`
  }

  if (step.kind === "loop") {
    return `Loop(\n    name=${quote(displayName(step))},\n    steps=[${children[0]}],\n    end_condition=${quote(step.expression || "last_step_content.contains('APPROVED')")},\n    max_iterations=${step.maxIterations},\n    description=${quote(step.description)},\n)`
  }

  return `Router(\n    name=${quote(displayName(step))},\n    selector=${quote(step.expression || "last_step_content.contains('critical')")},\n    choices=[\n${indent(children.join(",\n"), 8)},\n    ],\n    description=${quote(step.description)},\n)`
}

function executorArgument(step: WorkflowStepDraft, symbol = workflowStepSymbol(step)) {
  if (step.executor === "team") return `team=${symbol}_team`
  if (step.executor === "function") return `executor=${symbol}_executor`
  if (step.executor === "workflow") return `workflow=${symbol}_workflow`
  return `agent=${symbol}_agent`
}

function displayName(step: WorkflowStepDraft) {
  return step.name.trim() || workflowStepSymbol(step)
}

function quote(value: string) {
  return JSON.stringify(value)
}

function indent(value: string, spaces: number) {
  const padding = " ".repeat(spaces)
  return value
    .split("\n")
    .map((line) => `${padding}${line}`)
    .join("\n")
}
