import { Alert, Steps } from 'antd'
import type { KnowledgeProgressEvent, KnowledgeProgressStage, KnowledgeProgressStatus } from '../types'

type ProgressStageKey = Exclude<KnowledgeProgressStage, 'done'>

const STAGE_ORDER: ProgressStageKey[] = ['upload', 'parse', 'vectorize', 'cleanup']

const STAGE_TITLES: Record<ProgressStageKey, string> = {
  upload: '上传',
  parse: '解析',
  vectorize: '向量化',
  cleanup: '清理',
}

const STAGE_FALLBACK: Record<ProgressStageKey, string> = {
  upload: '上传中',
  parse: '解析中',
  vectorize: '向量化中',
  cleanup: '清理中',
}

export type ProgressStageState = {
  stage: ProgressStageKey
  status: KnowledgeProgressStatus
  message: string
}

export function createInitialProgress(includeUpload: boolean): ProgressStageState[] {
  return STAGE_ORDER.map((stage) => {
    if (stage === 'upload' && !includeUpload) {
      return { stage, status: 'skipped', message: '跳过' }
    }
    return { stage, status: 'pending', message: STAGE_FALLBACK[stage] }
  })
}

export function applyProgressEvent(
  stages: ProgressStageState[],
  event: KnowledgeProgressEvent
): ProgressStageState[] {
  if (event.stage === 'done') return stages
  return stages.map((item) => {
    if (item.stage !== event.stage) return item
    return {
      ...item,
      status: event.status,
      message: event.message || event.error || item.message,
    }
  })
}

export function activeStepIndex(stages: ProgressStageState[]): number {
  const running = stages.findIndex((item) => item.status === 'running')
  if (running >= 0) return running
  const failed = stages.findIndex((item) => item.status === 'failed')
  if (failed >= 0) return failed
  let lastCompleted = -1
  stages.forEach((item, index) => {
    if (item.status === 'completed' || item.status === 'skipped') lastCompleted = index
  })
  if (lastCompleted < 0) return 0
  return Math.min(lastCompleted + 1, stages.length - 1)
}

const stepStatus = (status: KnowledgeProgressStatus): 'wait' | 'process' | 'finish' | 'error' => {
  if (status === 'running') return 'process'
  if (status === 'completed' || status === 'skipped') return 'finish'
  if (status === 'failed') return 'error'
  return 'wait'
}

export function UpdateProgress({
  stages,
  includeUpload,
}: {
  stages: ProgressStageState[]
  includeUpload: boolean
}) {
  const visible = includeUpload ? stages : stages.filter((item) => item.stage !== 'upload')
  const current = activeStepIndex(visible)
  const failed = visible.find((item) => item.status === 'failed')
  const running = visible.find((item) => item.status === 'running')
  const summary = failed?.message || running?.message || '处理中'

  return (
    <div className="knowledge-update-progress">
      <Steps
        size="small"
        current={current}
        items={visible.map((item) => ({
          title: STAGE_TITLES[item.stage],
          content: item.message,
          status: stepStatus(item.status),
        }))}
      />
      <Alert className="knowledge-update-progress-alert" type={failed ? 'error' : 'info'} showIcon title={summary} />
    </div>
  )
}
