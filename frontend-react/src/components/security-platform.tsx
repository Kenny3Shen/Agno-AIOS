import { useGSAP } from '@gsap/react'
import gsap from 'gsap'
import { Streamdown } from 'streamdown'
import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  startTransition,
  useDeferredValue,
  useEffect,
  useEffectEvent,
  useRef,
  useState,
} from 'react'
import {
  Activity,
  ArrowRight,
  Bot,
  Cable,
  ChevronLeft,
  Copy,
  Cpu,
  HardDriveUpload,
  KeyRound,
  Link2,
  Moon,
  Network,
  RefreshCw,
  Route,
  Search,
  Sparkles,
  Sun,
  Workflow,
} from 'lucide-react'

import { Button } from '#/components/ui/button.tsx'
import { Input } from '#/components/ui/input.tsx'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '#/components/ui/select.tsx'
import { Switch } from '#/components/ui/switch.tsx'
import { Textarea } from '#/components/ui/textarea.tsx'
import { AuthProvider, useAuth } from '#/features/auth/auth-provider.tsx'
import { AuthScreen } from '#/features/auth/auth-screen.tsx'
import { formatKnowledgeMetadataBadges } from '#/features/workspace/knowledge-view.ts'
import { workspaceNavItems as navItems } from '#/features/workspace/navigation.ts'
import {
  buildTraceDateRange,
  buildTraceTimeline,
  summarizeConversationMessages,
} from '#/features/workspace/tracing-view.ts'
import type { TraceDatePreset } from '#/features/workspace/tracing-view.ts'
import {
  COLLAPSED_SIDEBAR_WIDTH,
  DEFAULT_SIDEBAR_WIDTH,
  clampSidebarWidth,
} from '#/features/workspace/sidebar-state.ts'
import { WorkspaceSidebar } from '#/features/workspace/workspace-sidebar.tsx'
import {
  fallbackDashboardSnapshot,
  fetchDashboardSnapshot,
} from '#/lib/dashboard.ts'
import type { DashboardSnapshot } from '#/lib/dashboard.ts'
import { applyThemeClass, getStoredTheme, setStoredTheme } from '#/lib/theme.ts'
import type { ThemeMode } from '#/lib/theme.ts'
import {
  addHiAgent,
  addPathKnowledgeDocument,
  addTextKnowledgeDocument,
  compactId,
  createPreviewSession,
  createMcpToken,
  deleteChatSession,
  deleteHiAgent,
  deleteKnowledgeDocument,
  deleteMcpToken,
  formatDurationMs,
  formatIsoDate,
  formatUnixDate,
  getPreviewWelcomeMessage,
  getTraceDetail,
  listTraces,
  loadChatHistory,
  loadChatSessions,
  loadKnowledgeBundle,
  loadMcpBundle,
  loadSettingsBundle,
  loadSkills,
  parseUrlToMarkdown,
  refreshCveCatalog,
  saveSettingsBundle,
  searchAssets,
  searchCves,
  searchKnowledge,
  setHiAgentEnabled,
  setMcpServiceEnabled,
  setSkillEnabled,
  streamChatMessage,
} from '#/lib/workspace.ts'
import type {
  AssetResult,
  ChatSession,
  KnowledgeBundle,
  KnowledgeSearchResult,
  McpBundle,
  ModelConfig,
  SettingsBundle,
  SkillInfo,
  TraceDetailResponse,
  TraceItem,
  WorkspaceMessage,
  WorkspaceTabId,
} from '#/lib/workspace.ts'
import { cn } from '#/lib/utils.ts'

gsap.registerPlugin(useGSAP)

type NoticeTone = 'info' | 'success' | 'error'

type NoticeState = {
  tone: NoticeTone
  title: string
  detail?: string
} | null

type StatusTone = 'ok' | 'warn' | 'error' | 'muted'

type WorkspaceSelectOption = {
  value: string
  label: string
}

const EMPTY_SELECT_VALUE = '__workspace_empty__'
const primaryButtonClass =
  'h-9 rounded-md bg-cyan-300 px-4 text-sm font-semibold text-slate-950 hover:bg-cyan-200'
const secondaryButtonClass =
  'h-9 rounded-md border-slate-200 bg-white px-4 text-sm text-slate-700 hover:border-slate-300 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800'
const dangerButtonClass =
  'h-8 rounded-md border-rose-200 bg-rose-50 px-3 text-xs font-semibold text-rose-700 hover:bg-rose-100 dark:border-rose-500/25 dark:bg-rose-500/10 dark:text-rose-100 dark:hover:bg-rose-500/16'
const fieldClass =
  'h-9 rounded-md border-slate-200 bg-white text-sm text-slate-950 placeholder:text-slate-400 dark:border-slate-800 dark:bg-slate-950/70 dark:text-slate-50 dark:placeholder:text-slate-500'
const textAreaClass =
  'rounded-md border-slate-200 bg-white text-sm text-slate-950 placeholder:text-slate-400 dark:border-slate-800 dark:bg-slate-950/70 dark:text-slate-50 dark:placeholder:text-slate-500'
const panelLabelClass =
  'text-[11px] font-semibold tracking-[0.12em] text-slate-500 uppercase dark:text-slate-500'
const rowTitleClass =
  'truncate text-sm font-semibold text-slate-950 dark:text-white'
const mutedTextClass = 'text-xs text-slate-500 dark:text-slate-400'
const innerPanelClass =
  'rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950/45'
const listFrameClass =
  'divide-y divide-slate-200 overflow-hidden rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-800'

function encodeSelectValue(value: string) {
  return value === '' ? EMPTY_SELECT_VALUE : value
}

function decodeSelectValue(value: string) {
  return value === EMPTY_SELECT_VALUE ? '' : value
}

function WorkspaceSelect({
  value,
  options,
  onValueChange,
  placeholder,
  triggerClassName,
}: {
  value: string
  options: WorkspaceSelectOption[]
  onValueChange: (value: string) => void
  placeholder?: string
  triggerClassName?: string
}) {
  return (
    <Select
      onValueChange={(nextValue) => onValueChange(decodeSelectValue(nextValue))}
      value={encodeSelectValue(value)}
    >
      <SelectTrigger
        className={cn(
          'h-9 rounded-md border-slate-200 bg-white px-3 text-sm text-slate-900 shadow-xs hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950/70 dark:text-white dark:hover:bg-slate-900',
          triggerClassName,
        )}
      >
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent
        className="border-slate-200 bg-white text-slate-950 shadow-xl dark:border-slate-700 dark:bg-slate-950 dark:text-slate-50"
        position="popper"
      >
        <SelectGroup>
          {options.map((option) => (
            <SelectItem
              className="focus:bg-slate-100 focus:text-slate-950 dark:focus:bg-slate-800 dark:focus:text-slate-50"
              key={`${option.value}-${option.label}`}
              value={encodeSelectValue(option.value)}
            >
              {option.label}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  )
}

function SurfaceCard({
  className,
  children,
}: {
  className?: string
  children: ReactNode
}) {
  return (
    <article
      className={cn(
        'relative overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950/72',
        className,
      )}
    >
      {children}
    </article>
  )
}

function PanelNotice({ notice }: { notice: NoticeState }) {
  if (!notice) return null

  return (
    <div
      className={cn(
        'rounded-lg border px-3 py-2 text-sm',
        notice.tone === 'info' &&
          'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300',
        notice.tone === 'success' &&
          'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-100',
        notice.tone === 'error' &&
          'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/25 dark:bg-rose-500/10 dark:text-rose-100',
      )}
    >
      <div className="font-semibold">{notice.title}</div>
      {notice.detail ? <div className="sr-only">{notice.detail}</div> : null}
    </div>
  )
}

function SectionIntro({
  title,
  body,
  actions,
}: {
  title: string
  body: string
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-3 border-b border-slate-200 pb-3 dark:border-slate-800 lg:flex-row lg:items-center lg:justify-between">
      <div className="min-w-0">
        <h3 className="truncate text-base font-semibold tracking-[-0.02em] text-slate-950 dark:text-white">
          {title}
        </h3>
        <p className="sr-only">{body}</p>
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>
      ) : null}
    </div>
  )
}

function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
  variant = 'dark',
  tone = 'neutral',
}: {
  label: string
  value: string
  hint: string
  icon: LucideIcon
  variant?: 'dark' | 'light'
  tone?: 'neutral' | 'ok' | 'warn' | 'error'
}) {
  const isLight = variant === 'light'
  const accentClass = cn(
    tone === 'ok' && 'bg-emerald-400',
    tone === 'warn' && 'bg-amber-400',
    tone === 'error' && 'bg-rose-400',
    tone === 'neutral' && (isLight ? 'bg-cyan-400' : 'bg-cyan-300'),
  )

  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-lg border p-3 transition-colors duration-200',
        isLight
          ? 'border-slate-200 bg-white text-slate-950 shadow-sm dark:border-slate-800 dark:bg-slate-950/70 dark:text-white'
          : 'border-slate-900 bg-slate-950 text-white shadow-[0_14px_32px_rgba(15,23,42,0.2)] dark:border-slate-800 dark:bg-slate-950/70 dark:shadow-none',
      )}
    >
      <div className={cn('absolute inset-x-0 top-0 h-0.5', accentClass)} />
      <div className="flex items-center justify-between gap-3">
        <span
          className={cn(
            'text-[11px] font-semibold tracking-[0.12em] uppercase',
            isLight ? 'text-slate-500 dark:text-slate-400' : 'text-slate-400',
          )}
        >
          {label}
        </span>
        <Icon
          className={cn(
            'size-4',
            isLight ? 'text-slate-400 dark:text-slate-500' : 'text-slate-500',
          )}
        />
      </div>
      <div
        className={cn(
          'mt-2 truncate text-lg font-semibold tracking-[-0.03em]',
          isLight ? 'text-slate-950 dark:text-white' : 'text-white',
        )}
      >
        {value}
      </div>
      <div
        className={cn(
          'mt-1 truncate text-xs',
          isLight
            ? 'text-slate-500 dark:text-slate-300/60'
            : 'text-slate-300/72',
        )}
      >
        {hint}
      </div>
    </div>
  )
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4 text-center dark:border-slate-800 dark:bg-slate-900/70">
      <div className="text-sm font-semibold text-slate-950 dark:text-white">
        {title}
      </div>
      <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
        {body}
      </p>
    </div>
  )
}

function InlineStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-900/70">
      <div className="text-[10px] font-semibold tracking-[0.12em] text-slate-500 uppercase dark:text-slate-500">
        {label}
      </div>
      <div className="mt-1 truncate text-sm font-bold text-slate-950 dark:text-white">
        {value}
      </div>
    </div>
  )
}

function PanelHeading({
  title,
  value,
  actions,
}: {
  title: string
  value?: string
  actions?: ReactNode
}) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-3">
      <div className={panelLabelClass}>{title}</div>
      <div className="flex shrink-0 items-center gap-2">
        {value ? (
          <span className="rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[11px] text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
            {value}
          </span>
        ) : null}
        {actions}
      </div>
    </div>
  )
}

function StatusPill({
  children,
  tone = 'muted',
}: {
  children: ReactNode
  tone?: StatusTone
}) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center rounded-md px-2 py-0.5 text-[11px] font-semibold',
        tone === 'ok' &&
          'bg-emerald-50 text-emerald-700 dark:bg-emerald-400/12 dark:text-emerald-200',
        tone === 'warn' &&
          'bg-amber-50 text-amber-700 dark:bg-amber-400/12 dark:text-amber-200',
        tone === 'error' &&
          'bg-rose-50 text-rose-700 dark:bg-rose-400/12 dark:text-rose-200',
        tone === 'muted' &&
          'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
      )}
    >
      {children}
    </span>
  )
}

function SignalRail({
  snapshot,
  previewMode,
}: {
  snapshot: DashboardSnapshot
  previewMode: boolean
}) {
  const cells: Array<{
    label: string
    value: string
    hint: string
    icon: LucideIcon
    tone: StatusTone
  }> = [
    {
      label: 'API',
      value: snapshot.apiOnline ? '在线' : '本地',
      hint: snapshot.backendLabel,
      icon: Activity,
      tone: snapshot.apiOnline ? 'ok' : 'warn',
    },
    {
      label: 'Trace',
      value: `${snapshot.liveTraces}`,
      hint: `均耗时 ${formatDurationMs(snapshot.averageDurationMs)}`,
      icon: Route,
      tone: snapshot.successRate >= 90 ? 'ok' : 'error',
    },
    {
      label: 'RAG',
      value: `${snapshot.knowledgeDocuments} docs`,
      hint: `${snapshot.knowledgeChunks} chunks`,
      icon: HardDriveUpload,
      tone: snapshot.knowledgeDocuments ? 'ok' : 'warn',
    },
    {
      label: 'Services',
      value: `${snapshot.enabledServices}`,
      hint: `${snapshot.enabledSkills} skills`,
      icon: Cable,
      tone: snapshot.enabledServices ? 'ok' : 'warn',
    },
  ]

  return (
    <div className="border-b border-slate-200 bg-slate-100/92 px-3 py-2 dark:border-slate-800 dark:bg-slate-950/86 md:px-4">
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {cells.map((cell) => {
          const Icon = cell.icon
          return (
            <div
              className="group relative overflow-hidden rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm dark:border-slate-800 dark:bg-slate-900/80 dark:shadow-none"
              key={cell.label}
            >
              <div
                className={cn(
                  'absolute inset-y-0 left-0 w-1',
                  cell.tone === 'ok' && 'bg-emerald-400',
                  cell.tone === 'warn' && 'bg-amber-400',
                  cell.tone === 'error' && 'bg-rose-400',
                  cell.tone === 'muted' && 'bg-slate-400',
                )}
              />
              <div className="flex items-center justify-between gap-3 pl-1">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Icon className="size-3.5 text-slate-500 dark:text-slate-500" />
                    <span className="text-[11px] font-semibold tracking-[0.12em] text-slate-600 uppercase dark:text-slate-500">
                      {cell.label}
                    </span>
                  </div>
                  <div className="mt-1 truncate text-sm font-semibold text-slate-950 dark:text-white">
                    {cell.value}
                  </div>
                </div>
                <div className="truncate text-right text-xs text-slate-600 dark:text-slate-400">
                  {cell.hint}
                </div>
              </div>
            </div>
          )
        })}
      </div>
      {previewMode ? (
        <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-800 dark:border-amber-300/20 dark:bg-amber-300/10 dark:text-amber-50">
          后端未连接，当前显示本地数据。
        </div>
      ) : null}
    </div>
  )
}

function SituationPanel({ previewMode }: { previewMode: boolean }) {
  const [timeScope, setTimeScope] = useState<'24h' | '7d' | '30d'>('24h')
  const [traces, setTraces] = useState<TraceItem[]>([])
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState<NoticeState>(null)

  const loadSituation = useEffectEvent(async () => {
    setLoading(true)
    try {
      const limit = timeScope === '24h' ? 12 : timeScope === '7d' ? 24 : 36
      const response = await listTraces({ page: 1, limit })
      setTraces(response.items)
      setNotice(
        previewMode
          ? {
              tone: 'info',
              title: '当前使用本地运行数据',
              detail: '后端未联通时，态势指标会自动切换到本地数据集。',
            }
          : null,
      )
    } catch (error) {
      setNotice({
        tone: 'error',
        title: '加载运行态势失败',
        detail: error instanceof Error ? error.message : '请稍后重试',
      })
    } finally {
      setLoading(false)
    }
  })

  useEffect(() => {
    void loadSituation()
  }, [previewMode, timeScope])

  const sampleSize = traces.length
  const errorRuns = traces.filter(
    (trace) => trace.status === 'ERROR' || Number(trace.error_count || 0) > 0,
  )
  const okRuns = traces.filter(
    (trace) => trace.status === 'OK' && Number(trace.error_count || 0) === 0,
  )
  const maxDuration = Math.max(
    ...traces.map((trace) => trace.duration_ms || 0),
    1,
  )
  const agentRows = Object.entries(
    traces.reduce<
      Record<string, { runs: number; duration: number; errors: number }>
    >((acc, trace) => {
      const agentId = trace.agent_id || trace.workflow_id || 'default-agent'
      const current = acc[agentId] ?? { runs: 0, duration: 0, errors: 0 }
      current.runs += 1
      current.duration += trace.duration_ms || 0
      current.errors += Number(trace.error_count || 0) > 0 ? 1 : 0
      acc[agentId] = current
      return acc
    }, {}),
  ).map(([agentId, stat]) => ({ agentId, ...stat }))

  return (
    <div className="flex flex-col gap-4">
      <SectionIntro
        actions={
          <>
            <WorkspaceSelect
              onValueChange={(value) =>
                setTimeScope(value as '24h' | '7d' | '30d')
              }
              options={[
                { value: '24h', label: '最近 24 小时' },
                { value: '7d', label: '最近 7 天' },
                { value: '30d', label: '最近 30 天' },
              ]}
              value={timeScope}
            />
            <Button
              className={primaryButtonClass}
              onClick={() => void loadSituation()}
              type="button"
            >
              <RefreshCw className={cn('size-4', loading && 'animate-spin')} />
              刷新
            </Button>
          </>
        }
        body="集中呈现最近运行、状态分布、Agent 负载和异常样本，帮助快速判断当前安全运营态势。"
        title="态势总览"
      />

      <PanelNotice notice={notice} />

      <div className="grid gap-3 xl:grid-cols-4">
        <MetricCard
          hint={`当前样本 ${sampleSize} 条`}
          icon={Activity}
          label="运行数"
          tone="neutral"
          value={`${sampleSize}`}
        />
        <MetricCard
          hint="按最近样本计算"
          icon={Sparkles}
          label="成功率"
          tone={sampleSize && okRuns.length / sampleSize >= 0.9 ? 'ok' : 'warn'}
          value={`${sampleSize ? Math.round((okRuns.length / sampleSize) * 100) : 0}%`}
        />
        <MetricCard
          hint="状态 ERROR 或含错误 Span"
          icon={Workflow}
          label="异常数"
          tone={errorRuns.length ? 'error' : 'ok'}
          value={`${errorRuns.length}`}
        />
        <MetricCard
          hint="平均链路耗时"
          icon={Route}
          label="均耗时"
          tone="neutral"
          value={
            traces.length
              ? formatDurationMs(
                  traces.reduce((total, item) => total + item.duration_ms, 0) /
                    traces.length,
                )
              : '0ms'
          }
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
        <SurfaceCard>
          <div className="p-4">
            <PanelHeading title="最近运行" value={`${traces.length} 条`} />
            <div
              className={cn(
                'mt-3',
                listFrameClass,
                !traces.length && 'border-dashed',
              )}
            >
              {traces.length ? (
                traces.map((trace) => (
                  <div
                    className="grid gap-2 bg-white p-3 dark:bg-slate-950/40"
                    key={trace.trace_id}
                  >
                    <div className="grid min-w-0 gap-3 md:grid-cols-[minmax(0,1fr)_auto_auto] md:items-center">
                      <div className="min-w-0">
                        <div className={rowTitleClass}>{trace.name}</div>
                        <div className={cn('mt-1 truncate', mutedTextClass)}>
                          {compactId(trace.session_id)} ·{' '}
                          {compactId(trace.run_id)} ·{' '}
                          {formatIsoDate(trace.start_time)}
                        </div>
                      </div>
                      <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                        {formatDurationMs(trace.duration_ms)}
                      </div>
                      <StatusPill
                        tone={trace.status === 'ERROR' ? 'error' : 'ok'}
                      >
                        {trace.status}
                      </StatusPill>
                    </div>
                    <div className="h-1.5 rounded-full bg-slate-200 dark:bg-slate-800">
                      <div
                        className={cn(
                          'h-full rounded-full',
                          trace.status === 'ERROR'
                            ? 'bg-gradient-to-r from-rose-400 to-orange-300'
                            : 'bg-gradient-to-r from-cyan-300 to-emerald-300',
                        )}
                        style={{
                          width: `${Math.max(
                            10,
                            (trace.duration_ms / maxDuration) * 100,
                          )}%`,
                        }}
                      />
                    </div>
                  </div>
                ))
              ) : (
                <div className="grid min-h-[138px] place-items-center bg-white px-4 py-8 dark:bg-slate-950/40">
                  <EmptyState
                    body="调整日期范围或刷新运行队列。"
                    title="暂无运行数据"
                  />
                </div>
              )}
            </div>
          </div>
        </SurfaceCard>

        <SurfaceCard>
          <div className="flex flex-col gap-5 p-4">
            <div>
              <PanelHeading title="状态分布" />
              <div className="mt-3 flex flex-col gap-3">
                {[
                  {
                    label: 'OK',
                    count: okRuns.length,
                    tone: 'from-emerald-300 to-cyan-300',
                  },
                  {
                    label: 'ERROR',
                    count: errorRuns.length,
                    tone: 'from-rose-300 to-orange-300',
                  },
                  {
                    label: 'OTHER',
                    count: Math.max(
                      sampleSize - okRuns.length - errorRuns.length,
                      0,
                    ),
                    tone: 'from-slate-400 to-slate-500',
                  },
                ].map((item) => (
                  <div key={item.label}>
                    <div className="mb-1 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                      <span>{item.label}</span>
                      <span>{item.count}</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-slate-200 dark:bg-slate-800">
                      <div
                        className={cn(
                          'h-full rounded-full bg-gradient-to-r',
                          item.tone,
                        )}
                        style={{
                          width: `${Math.max(
                            item.count ? 10 : 0,
                            sampleSize ? (item.count / sampleSize) * 100 : 0,
                          )}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <PanelHeading title="Agent 负载" value={`${agentRows.length}`} />
              <div className={cn('mt-3', listFrameClass)}>
                {agentRows.length ? (
                  agentRows.map((agent) => (
                    <div
                      className="flex items-center justify-between bg-white px-3 py-2.5 dark:bg-slate-950/40"
                      key={agent.agentId}
                    >
                      <div className="min-w-0">
                        <div className={rowTitleClass}>{agent.agentId}</div>
                        <div className={mutedTextClass}>
                          {agent.runs} 次 · {agent.errors} 异常
                        </div>
                      </div>
                      <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                        {formatDurationMs(
                          agent.duration / Math.max(agent.runs, 1),
                        )}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="bg-white p-3 dark:bg-slate-950/40">
                    <EmptyState
                      body="等待 Trace 样本写入后显示。"
                      title="暂无 Agent 负载"
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        </SurfaceCard>
      </div>
    </div>
  )
}

function ChatPanel({ previewMode }: { previewMode: boolean }) {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [messages, setMessages] = useState<WorkspaceMessage[]>([
    {
      role: 'assistant',
      content: getPreviewWelcomeMessage(),
      final: true,
    },
  ])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [models, setModels] = useState<ModelConfig[]>([])
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingSessions, setLoadingSessions] = useState(true)
  const [notice, setNotice] = useState<NoticeState>(null)
  const chatRef = useRef<HTMLDivElement | null>(null)

  const loadSessions = useEffectEvent(async () => {
    setLoadingSessions(true)
    try {
      const nextSessions = await loadChatSessions()
      setSessions(nextSessions)
      if (previewMode) {
        setNotice({
          tone: 'info',
          title: '当前使用本地会话数据',
          detail:
            '发送消息时会使用本地流式响应，便于在后端不可达时继续操作工作台。',
        })
      }
    } catch (error) {
      setNotice({
        tone: 'error',
        title: '加载会话列表失败',
        detail: error instanceof Error ? error.message : '请稍后重试',
      })
    } finally {
      setLoadingSessions(false)
    }
  })

  const loadModels = useEffectEvent(async () => {
    try {
      const bundle = await loadSettingsBundle()
      setModels(bundle.models)
      setSelectedModelId(
        bundle.active_model_id ||
          bundle.models.find((model) => model.enabled)?.id ||
          bundle.models[0]?.id ||
          null,
      )
    } catch (error) {
      setNotice({
        tone: 'error',
        title: '加载模型配置失败',
        detail: error instanceof Error ? error.message : '请稍后重试',
      })
    }
  })

  useEffect(() => {
    void Promise.all([loadSessions(), loadModels()])
  }, [])

  useEffect(() => {
    chatRef.current?.scrollTo({
      top: chatRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, loading])

  const selectedModel =
    models.find((model) => model.id === selectedModelId) ||
    models.find((model) => model.enabled) ||
    null

  const selectSession = useEffectEvent(async (sessionId: string) => {
    setCurrentSessionId(sessionId)
    try {
      const history = await loadChatHistory(sessionId)
      setMessages(
        history.length
          ? history
          : [
              {
                role: 'assistant',
                content: getPreviewWelcomeMessage(),
                final: true,
              },
            ],
      )
    } catch (error) {
      setNotice({
        tone: 'error',
        title: '加载会话内容失败',
        detail: error instanceof Error ? error.message : '请稍后重试',
      })
    }
  })

  const createNewChat = () => {
    setCurrentSessionId(null)
    setMessages([
      {
        role: 'assistant',
        content: getPreviewWelcomeMessage(),
        final: true,
      },
    ])
  }

  const sendMessage = useEffectEvent(async () => {
    if (!input.trim() || loading || !selectedModel) return

    const message = input.trim()
    const sessionId = currentSessionId || createPreviewSession()
    if (!currentSessionId) {
      setCurrentSessionId(sessionId)
    }

    setInput('')
    setLoading(true)
    setMessages((current) => [
      ...current,
      { role: 'user', content: message, final: true },
      { role: 'assistant', content: '', final: false },
    ])

    try {
      await streamChatMessage({
        message,
        modelId: selectedModelId,
        sessionId,
        onChunk: (chunk) => {
          startTransition(() => {
            setMessages((current) => {
              const next = [...current]
              const last = next.at(-1)
              if (last && last.role === 'assistant') {
                next[next.length - 1] = {
                  ...last,
                  content: `${last.content}${chunk}`,
                  final: false,
                }
              }
              return next
            })
          })
        },
      })

      setMessages((current) => {
        const next = [...current]
        const last = next.at(-1)
        if (last && last.role === 'assistant') {
          next[next.length - 1] = { ...last, final: true }
        }
        return next
      })
      await loadSessions()
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: '请求失败，请检查 API 状态后再试。',
          final: true,
        },
      ])
      setNotice({
        tone: 'error',
        title: '发送消息失败',
        detail: error instanceof Error ? error.message : '请稍后重试',
      })
    } finally {
      setLoading(false)
    }
  })

  const removeSession = useEffectEvent(async (sessionId: string) => {
    await deleteChatSession(sessionId)
    if (currentSessionId === sessionId) {
      createNewChat()
    }
    await loadSessions()
  })

  return (
    <div className="flex flex-col gap-4">
      <SectionIntro
        actions={
          <Button
            className={primaryButtonClass}
            onClick={createNewChat}
            type="button"
          >
            <Sparkles className="size-4" />
            新建对话
          </Button>
        }
        body="面向安全研判的 Agent 对话空间，支持历史会话、模型路由和流式响应。"
        title="Agent 对话"
      />

      <PanelNotice notice={notice} />

      <div className="grid gap-4 xl:grid-cols-[240px_minmax(0,1fr)]">
        <SurfaceCard className="h-full">
          <div className="flex h-full flex-col p-4">
            <PanelHeading title="会话" value={`${sessions.length}`} />
            <div className={cn('mt-3 flex-1', listFrameClass)}>
              {loadingSessions ? (
                <div className="p-4 text-sm text-slate-500 dark:text-slate-400">
                  加载会话中...
                </div>
              ) : sessions.length ? (
                sessions.map((session) => (
                  <div
                    className={cn(
                      'w-full cursor-pointer px-3 py-2.5 text-left transition-colors',
                      currentSessionId === session.session_id
                        ? 'bg-cyan-50 text-slate-950 dark:bg-cyan-300/10 dark:text-white'
                        : 'bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-950 dark:bg-slate-950/40 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-white',
                    )}
                    key={session.session_id}
                    onClick={() => void selectSession(session.session_id)}
                    onKeyDown={(event) => {
                      if (event.target !== event.currentTarget) return
                      if (event.key !== 'Enter' && event.key !== ' ') return
                      event.preventDefault()
                      void selectSession(session.session_id)
                    }}
                    role="button"
                    tabIndex={0}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-semibold">
                          {session.preview || '新对话'}
                        </div>
                        <div className="mt-1 text-[11px] text-inherit/60">
                          {formatUnixDate(session.updated_at)}
                        </div>
                      </div>
                      <button
                        aria-label={`删除会话 ${session.preview || session.session_id}`}
                        className="grid size-7 place-items-center rounded-md border border-slate-200 bg-white text-slate-500 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-slate-800"
                        onClick={(event) => {
                          event.stopPropagation()
                          void removeSession(session.session_id)
                        }}
                        type="button"
                      >
                        <ChevronLeft className="size-3.5 rotate-45" />
                      </button>
                    </div>
                  </div>
                ))
              ) : (
                <EmptyState body="点击新建对话开始。" title="暂无历史会话" />
              )}
            </div>
          </div>
        </SurfaceCard>

        <SurfaceCard>
          <div className="flex flex-col gap-3 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <div className={rowTitleClass}>
                  {selectedModel?.name ?? '未选择模型'}
                </div>
                <div className={cn('mt-0.5', mutedTextClass)}>
                  session {compactId(currentSessionId)}
                </div>
              </div>
              <WorkspaceSelect
                onValueChange={setSelectedModelId}
                options={models.map((model) => ({
                  value: model.id,
                  label: `${model.name} ${model.enabled ? '' : '(disabled)'}`,
                }))}
                triggerClassName="min-w-[14rem]"
                value={selectedModelId ?? ''}
              />
            </div>

            <div
              className="flex max-h-[34rem] min-h-[24rem] flex-col gap-3 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-950/40"
              ref={chatRef}
            >
              {messages.map((message, index) => (
                <div
                  className={cn(
                    'flex gap-3',
                    message.role === 'user' && 'justify-end',
                  )}
                  key={`${index}-${message.role}`}
                >
                  {message.role === 'assistant' ? (
                    <div className="grid size-8 shrink-0 place-items-center rounded-md border border-cyan-200 bg-cyan-50 text-cyan-700 dark:border-cyan-300/20 dark:bg-cyan-300/10 dark:text-cyan-100">
                      <Cpu className="size-4" />
                    </div>
                  ) : null}
                  <div
                    className={cn(
                      'max-w-[85%] rounded-lg border px-3 py-2.5',
                      message.role === 'assistant'
                        ? 'border-slate-200 bg-white text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100'
                        : 'border-cyan-200 bg-cyan-50 text-slate-900 dark:border-cyan-300/20 dark:bg-cyan-300/12 dark:text-cyan-50',
                    )}
                  >
                    <div className="mb-1.5 flex items-center gap-2 text-[11px] text-inherit/62">
                      <span>
                        {message.role === 'assistant' ? 'Agent' : '我'}
                      </span>
                      {message.role === 'assistant' && !message.final ? (
                        <StatusPill tone="ok">流式</StatusPill>
                      ) : null}
                    </div>
                    {message.role === 'assistant' ? (
                      <Streamdown
                        className="prose prose-sm max-w-none text-slate-700 dark:prose-invert dark:text-slate-100"
                        controls={{ code: { copy: true }, table: true }}
                        mode={message.final ? 'static' : 'streaming'}
                        parseIncompleteMarkdown
                      >
                        {message.content}
                      </Streamdown>
                    ) : (
                      <div className="whitespace-pre-wrap text-sm leading-7">
                        {message.content}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {loading ? (
                <div className="flex gap-3">
                  <div className="grid size-8 shrink-0 place-items-center rounded-md border border-cyan-200 bg-cyan-50 text-cyan-700 dark:border-cyan-300/20 dark:bg-cyan-300/10 dark:text-cyan-100">
                    <RefreshCw className="size-4 animate-spin" />
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                    Agent 生成中...
                  </div>
                </div>
              ) : null}
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-950/60">
              <Textarea
                className="min-h-28 resize-y border-none bg-transparent px-0 py-0 text-sm text-slate-950 placeholder:text-slate-400 focus-visible:ring-0 dark:text-white dark:placeholder:text-slate-500"
                onChange={(event) => setInput(event.target.value)}
                placeholder="描述任务，例如：分析这批 Nginx 入口是否受新 CVE 影响。"
                value={input}
              />
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                <div className={mutedTextClass}>
                  模型：{selectedModel?.name ?? '未配置'}
                </div>
                <Button
                  className={primaryButtonClass}
                  onClick={() => void sendMessage()}
                  type="button"
                >
                  发送
                  <ArrowRight className="size-4" />
                </Button>
              </div>
            </div>
          </div>
        </SurfaceCard>
      </div>
    </div>
  )
}

function KnowledgePanel({ previewMode }: { previewMode: boolean }) {
  const [bundle, setBundle] = useState<KnowledgeBundle | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeForm, setActiveForm] = useState<'upload' | 'text' | 'path'>(
    'upload',
  )
  const [documentQuery, setDocumentQuery] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [searchLimit, setSearchLimit] = useState(5)
  const [searchResults, setSearchResults] = useState<KnowledgeSearchResult[]>(
    [],
  )
  const [file, setFile] = useState<File | null>(null)
  const [browserTitle, setBrowserTitle] = useState('')
  const [browserSource, setBrowserSource] = useState('upload')
  const [textTitle, setTextTitle] = useState('')
  const [textSource, setTextSource] = useState('manual')
  const [textContent, setTextContent] = useState('')
  const [pathValue, setPathValue] = useState('')
  const [pathTitle, setPathTitle] = useState('')
  const [notice, setNotice] = useState<NoticeState>(null)
  const deferredQuery = useDeferredValue(documentQuery)

  const loadKnowledge = useEffectEvent(async () => {
    setLoading(true)
    try {
      const next = await loadKnowledgeBundle()
      setBundle(next)
      setNotice(
        previewMode
          ? {
              tone: 'info',
              title: '当前使用本地知识库数据',
              detail: '文档写入、删除和检索会在本地数据集上执行。',
            }
          : null,
      )
    } catch (error) {
      setNotice({
        tone: 'error',
        title: '加载知识库失败',
        detail: error instanceof Error ? error.message : '请稍后重试',
      })
    } finally {
      setLoading(false)
    }
  })

  useEffect(() => {
    void loadKnowledge()
  }, [previewMode])

  const documents =
    bundle?.documents.filter((document) => {
      if (!deferredQuery.trim()) return true
      const haystack =
        `${document.title} ${document.source} ${document.id} ${JSON.stringify(document.metadata ?? {})}`.toLowerCase()
      return haystack.includes(deferredQuery.toLowerCase())
    }) ?? []

  const submitBrowserUpload = useEffectEvent(async () => {
    if (!file) {
      setNotice({
        tone: 'error',
        title: '请选择一个文本文件',
      })
      return
    }

    const content = await file.text()
    const title = browserTitle || file.name.replace(/\.[^.]+$/, '')
    await addTextKnowledgeDocument({
      title,
      source: browserSource,
      content,
    })
    setFile(null)
    setBrowserTitle('')
    setNotice({
      tone: 'success',
      title: '文件内容已写入知识库',
      detail: `${title} 已被转成文本块写入当前集合。`,
    })
    await loadKnowledge()
  })

  const submitTextDocument = useEffectEvent(async () => {
    if (!textTitle.trim() || !textContent.trim()) {
      setNotice({
        tone: 'error',
        title: '标题和内容不能为空',
      })
      return
    }

    await addTextKnowledgeDocument({
      title: textTitle.trim(),
      source: textSource.trim() || 'manual',
      content: textContent.trim(),
    })
    setTextTitle('')
    setTextContent('')
    setNotice({
      tone: 'success',
      title: '文本已写入知识库',
    })
    await loadKnowledge()
  })

  const submitPathDocument = useEffectEvent(async () => {
    if (!pathValue.trim()) {
      setNotice({
        tone: 'error',
        title: '请输入服务端文件路径',
      })
      return
    }

    await addPathKnowledgeDocument({
      path: pathValue.trim(),
      title: pathTitle.trim() || undefined,
    })
    setPathValue('')
    setPathTitle('')
    setNotice({
      tone: 'success',
      title: '服务端路径已导入',
    })
    await loadKnowledge()
  })

  const runSearch = useEffectEvent(async () => {
    if (!searchQuery.trim()) {
      setNotice({
        tone: 'error',
        title: '检索问题不能为空',
      })
      return
    }

    const results = await searchKnowledge(searchQuery.trim(), searchLimit)
    setSearchResults(results)
    setNotice({
      tone: 'success',
      title: '检索完成',
      detail: `共返回 ${results.length} 条片段命中。`,
    })
  })

  const removeDocument = useEffectEvent(async (documentId: string) => {
    await deleteKnowledgeDocument(documentId)
    await loadKnowledge()
    setNotice({
      tone: 'success',
      title: '知识文档已删除',
    })
  })

  const knowledgeStats = [
    {
      label: '文档',
      value: `${bundle?.status.documents ?? 0}`,
    },
    {
      label: '切片',
      value: `${bundle?.status.chunks ?? 0}`,
    },
    {
      label: 'Embedding',
      value: bundle?.status.embedding_dimensions
        ? `${bundle.status.embedding_dimensions}d`
        : (bundle?.status.embedding ?? '--'),
    },
    {
      label: 'Top K',
      value: `${bundle?.status.top_k ?? 0}`,
    },
  ]

  return (
    <div className="flex flex-col gap-5">
      <SectionIntro
        actions={
          <Button
            className={secondaryButtonClass}
            onClick={() => void loadKnowledge()}
            type="button"
            variant="outline"
          >
            <RefreshCw className={cn('size-4', loading && 'animate-spin')} />
            刷新
          </Button>
        }
        body="统一管理文本、路径和批量文档写入，并提供检索验证与分块状态。"
        title="RAG 知识库"
      />

      <PanelNotice notice={notice} />

      <div className="grid gap-4 xl:grid-cols-2 2xl:grid-cols-[minmax(280px,0.75fr)_minmax(0,1fr)_minmax(320px,0.85fr)]">
        <SurfaceCard>
          <div className="flex flex-col gap-4 p-4">
            <PanelHeading title="写入" />
            <div className="flex flex-wrap gap-2">
              {[
                { id: 'upload', label: '文件上传' },
                { id: 'text', label: '文本写入' },
                { id: 'path', label: '服务端路径' },
              ].map((item) => (
                <button
                  className={cn(
                    'rounded-md border px-3 py-1.5 text-sm transition-colors',
                    activeForm === item.id
                      ? 'border-cyan-300/40 bg-cyan-50 text-cyan-800 dark:bg-cyan-300/12 dark:text-white'
                      : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950/40 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-white',
                  )}
                  key={item.id}
                  onClick={() =>
                    setActiveForm(item.id as 'upload' | 'text' | 'path')
                  }
                  type="button"
                >
                  {item.label}
                </button>
              ))}
            </div>

            {activeForm === 'upload' ? (
              <div className="grid gap-4">
                <label className="grid min-h-36 place-items-center rounded-lg border border-dashed border-slate-300 bg-slate-50 p-5 text-center dark:border-slate-800 dark:bg-slate-950/40">
                  <div>
                    <HardDriveUpload className="mx-auto size-6 text-cyan-700 dark:text-cyan-100/74" />
                    <div className={cn('mt-3', rowTitleClass)}>
                      Markdown / TXT / LOG
                    </div>
                    <div className="mt-3 inline-flex rounded-md bg-cyan-300 px-3 py-1.5 text-sm font-semibold text-slate-950">
                      选择文件
                    </div>
                    <input
                      accept=".md,.markdown,.txt,.log,text/plain,text/markdown"
                      className="sr-only"
                      onChange={(event) =>
                        setFile(event.target.files?.[0] ?? null)
                      }
                      type="file"
                    />
                    {file ? (
                      <div className={cn('mt-3', mutedTextClass)}>
                        {file.name}
                      </div>
                    ) : null}
                  </div>
                </label>

                <div className="flex flex-col gap-3">
                  <Input
                    className={fieldClass}
                    onChange={(event) => setBrowserTitle(event.target.value)}
                    placeholder="标题，默认使用文件名"
                    value={browserTitle}
                  />
                  <Input
                    className={fieldClass}
                    onChange={(event) => setBrowserSource(event.target.value)}
                    placeholder="来源，例如 upload"
                    value={browserSource}
                  />
                  <Button
                    className={cn(primaryButtonClass, 'w-full')}
                    onClick={() => void submitBrowserUpload()}
                    type="button"
                  >
                    写入选中文件
                  </Button>
                </div>
              </div>
            ) : null}

            {activeForm === 'text' ? (
              <div className="grid gap-3 md:grid-cols-2">
                <Input
                  className={fieldClass}
                  onChange={(event) => setTextTitle(event.target.value)}
                  placeholder="标题，例如 应急处置规范"
                  value={textTitle}
                />
                <Input
                  className={fieldClass}
                  onChange={(event) => setTextSource(event.target.value)}
                  placeholder="来源，例如 manual"
                  value={textSource}
                />
                <div className="md:col-span-2">
                  <Textarea
                    className={cn(textAreaClass, 'min-h-40')}
                    onChange={(event) => setTextContent(event.target.value)}
                    placeholder="输入需要沉淀到知识库的文本内容"
                    value={textContent}
                  />
                </div>
                <div className="md:col-span-2 flex justify-end">
                  <Button
                    className={primaryButtonClass}
                    onClick={() => void submitTextDocument()}
                    type="button"
                  >
                    写入文本
                  </Button>
                </div>
              </div>
            ) : null}

            {activeForm === 'path' ? (
              <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_260px]">
                <Input
                  className={fieldClass}
                  onChange={(event) => setPathValue(event.target.value)}
                  placeholder="/abs/path/report.md"
                  value={pathValue}
                />
                <Input
                  className={fieldClass}
                  onChange={(event) => setPathTitle(event.target.value)}
                  placeholder="可选标题"
                  value={pathTitle}
                />
                <div className="md:col-span-2 flex justify-end">
                  <Button
                    className={primaryButtonClass}
                    onClick={() => void submitPathDocument()}
                    type="button"
                  >
                    导入路径
                  </Button>
                </div>
              </div>
            ) : null}
          </div>
        </SurfaceCard>

        <SurfaceCard>
          <div className="flex flex-col gap-4 p-4">
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <PanelHeading title="文档资产" value={`${documents.length}`} />
                <Input
                  className={cn(fieldClass, 'max-w-xs')}
                  onChange={(event) => setDocumentQuery(event.target.value)}
                  placeholder="按标题、来源或 ID 筛选"
                  value={documentQuery}
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                {knowledgeStats.map((item) => (
                  <InlineStat
                    key={item.label}
                    label={item.label}
                    value={item.value}
                  />
                ))}
              </div>
            </div>

            <div
              className={cn('max-h-[540px] overflow-y-auto', listFrameClass)}
            >
              {loading ? (
                <div className="p-4 text-sm text-slate-500 dark:text-slate-400">
                  加载文档中...
                </div>
              ) : documents.length ? (
                documents.map((document) => (
                  <div
                    className="overflow-hidden bg-white p-3 dark:bg-slate-950/40"
                    key={document.id}
                  >
                    <div className="grid min-w-0 gap-3">
                      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
                        <div className="min-w-0 overflow-hidden">
                          <div className={rowTitleClass} title={document.title}>
                            {document.title}
                          </div>
                          <div
                            className={cn('mt-1 truncate', mutedTextClass)}
                            title={document.source}
                          >
                            {document.source} · {document.chunks} chunks ·{' '}
                            {formatIsoDate(document.created_at)}
                          </div>
                        </div>
                        <Button
                          className={cn(dangerButtonClass, 'shrink-0')}
                          onClick={() => void removeDocument(document.id)}
                          type="button"
                          variant="outline"
                        >
                          删除
                        </Button>
                      </div>
                      <div className="flex min-w-0 flex-wrap gap-2 overflow-hidden">
                        {formatKnowledgeMetadataBadges(document.metadata).map(
                          (badge) => (
                            <span
                              className="inline-flex max-w-full min-w-0 rounded-md border border-slate-200 px-2 py-1 text-[10px] text-slate-500 dark:border-slate-800 dark:text-slate-400"
                              key={`${document.id}-${badge.key}`}
                              title={badge.title}
                            >
                              <span className="shrink-0">{badge.key}:</span>
                              <span className="ml-1 truncate">
                                {badge.value}
                              </span>
                            </span>
                          ),
                        )}
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <EmptyState body="从左侧写入入口添加。" title="暂无知识文档" />
              )}
            </div>
          </div>
        </SurfaceCard>

        <SurfaceCard className="xl:col-span-2 2xl:col-span-1">
          <div className="flex flex-col gap-4 p-4">
            <PanelHeading title="检索验证" value={`${searchResults.length}`} />
            <div className={cn('p-3', innerPanelClass)}>
              <div className="flex flex-col gap-3 sm:flex-row">
                <Input
                  className={fieldClass}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="输入问题，例如：MCP 审计基线"
                  value={searchQuery}
                />
                <WorkspaceSelect
                  onValueChange={(value) => setSearchLimit(Number(value))}
                  options={[
                    { value: '3', label: 'Top 3' },
                    { value: '5', label: 'Top 5' },
                    { value: '8', label: 'Top 8' },
                  ]}
                  triggerClassName="bg-slate-50 dark:bg-slate-950/70"
                  value={String(searchLimit)}
                />
                <Button
                  className={primaryButtonClass}
                  onClick={() => void runSearch()}
                  type="button"
                >
                  检索
                </Button>
              </div>

              <div className="mt-4 space-y-3">
                {searchResults.length ? (
                  searchResults.map((result) => (
                    <div
                      className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-950/60"
                      key={`${result.doc_id}-${result.chunk_index}`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className={rowTitleClass}>{result.title}</div>
                        <div className={mutedTextClass}>
                          score {(result.score * 100).toFixed(0)}%
                        </div>
                      </div>
                      <div className={cn('mt-1', mutedTextClass)}>
                        {result.source} · chunk #{result.chunk_index}
                      </div>
                      <div className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
                        {result.content}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-lg border border-dashed border-slate-200 bg-white p-4 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-400">
                    输入问题后查看召回片段。
                  </div>
                )}
              </div>
            </div>
          </div>
        </SurfaceCard>
      </div>
    </div>
  )
}

function TracingPanel({ previewMode }: { previewMode: boolean }) {
  const [filters, setFilters] = useState({ status: '', sessionId: '' })
  const [tracePage, setTracePage] = useState(1)
  const [traceLimit, setTraceLimit] = useState(25)
  const [datePreset, setDatePreset] = useState<TraceDatePreset>('24h')
  const [customStartDate, setCustomStartDate] = useState('')
  const [customEndDate, setCustomEndDate] = useState('')
  const [rangeAnchorIso, setRangeAnchorIso] = useState(() =>
    new Date().toISOString(),
  )
  const [reloadToken, setReloadToken] = useState(0)
  const [traceItems, setTraceItems] = useState<TraceItem[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null)
  const [detail, setDetail] = useState<TraceDetailResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [conversationMessages, setConversationMessages] = useState<
    WorkspaceMessage[]
  >([])
  const [loadingConversation, setLoadingConversation] = useState(false)
  const [notice, setNotice] = useState<NoticeState>(null)
  const traceDateRange = buildTraceDateRange({
    preset: datePreset,
    customStartDate,
    customEndDate,
    now: new Date(rangeAnchorIso),
  })

  const loadTraceList = useEffectEvent(async () => {
    setLoading(true)
    try {
      const response = await listTraces({
        page: tracePage,
        limit: traceLimit,
        session_id: filters.sessionId || undefined,
        status: filters.status || undefined,
        start_time: traceDateRange.startTime,
        end_time: traceDateRange.endTime,
      })
      setTraceItems(response.items)
      setTotalCount(response.total_count)
      if (response.items.length) {
        const visibleTraceIds = new Set(
          response.items.map((item) => item.trace_id),
        )
        setSelectedTraceId((current) =>
          current && visibleTraceIds.has(current)
            ? current
            : response.items[0].trace_id,
        )
      } else {
        setSelectedTraceId(null)
        setDetail(null)
        setConversationMessages([])
      }
      setNotice(
        previewMode
          ? {
              tone: 'info',
              title: 'Trace 队列使用本地数据',
              detail:
                '后端不可达时仍可查看 Trace、Span 和上下文事实的交互结构。',
            }
          : null,
      )
    } catch (error) {
      setNotice({
        tone: 'error',
        title: '加载 Trace 列表失败',
        detail: error instanceof Error ? error.message : '请稍后重试',
      })
    } finally {
      setLoading(false)
    }
  })

  const loadTraceDetail = useEffectEvent(async (traceId: string) => {
    setLoadingDetail(true)
    try {
      setDetail(await getTraceDetail(traceId))
    } catch (error) {
      setNotice({
        tone: 'error',
        title: '加载 Trace 详情失败',
        detail: error instanceof Error ? error.message : '请稍后重试',
      })
    } finally {
      setLoadingDetail(false)
    }
  })

  useEffect(() => {
    void loadTraceList()
  }, [
    filters.sessionId,
    filters.status,
    previewMode,
    reloadToken,
    traceDateRange.endTime,
    traceDateRange.startTime,
    traceLimit,
    tracePage,
  ])

  useEffect(() => {
    if (selectedTraceId) {
      void loadTraceDetail(selectedTraceId)
    }
  }, [selectedTraceId])

  useEffect(() => {
    const sessionId = detail?.trace.session_id
    if (!sessionId) {
      setConversationMessages([])
      return
    }

    let cancelled = false
    setLoadingConversation(true)

    void loadChatHistory(sessionId)
      .then((messages) => {
        if (!cancelled) setConversationMessages(messages)
      })
      .catch((error) => {
        if (!cancelled) {
          setConversationMessages([])
          setNotice({
            tone: 'error',
            title: '加载关联对话失败',
            detail: error instanceof Error ? error.message : '请稍后重试',
          })
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingConversation(false)
      })

    return () => {
      cancelled = true
    }
  }, [detail?.trace.session_id])

  const maxDuration = Math.max(...traceItems.map((item) => item.duration_ms), 1)
  const errorCount = traceItems.filter(
    (item) => item.status === 'ERROR' || Number(item.error_count || 0) > 0,
  ).length
  const averageDuration = traceItems.length
    ? formatDurationMs(
        traceItems.reduce((total, item) => total + item.duration_ms, 0) /
          traceItems.length,
      )
    : '0ms'
  const totalPages = Math.max(1, Math.ceil(totalCount / traceLimit))
  const pageStart = totalCount ? (tracePage - 1) * traceLimit + 1 : 0
  const pageEnd = Math.min(totalCount, tracePage * traceLimit)
  const traceStats = [
    { label: '当前页', value: `${traceItems.length}` },
    { label: '总数', value: `${totalCount}` },
    { label: '错误', value: `${errorCount}` },
    { label: '均耗时', value: averageDuration },
  ]
  const selectedTimeline = buildTraceTimeline(detail)
  const conversationSummaries =
    summarizeConversationMessages(conversationMessages)
  const refreshTraceQueue = () => {
    setRangeAnchorIso(new Date().toISOString())
    setReloadToken((current) => current + 1)
  }

  return (
    <div className="flex flex-col gap-5">
      <SectionIntro
        actions={
          <>
            <Input
              className={cn(fieldClass, 'w-44')}
              onChange={(event) => {
                setFilters((current) => ({
                  ...current,
                  sessionId: event.target.value,
                }))
                setTracePage(1)
              }}
              placeholder="session_id"
              value={filters.sessionId}
            />
            <WorkspaceSelect
              onValueChange={(value) => {
                setFilters((current) => ({
                  ...current,
                  status: value,
                }))
                setTracePage(1)
              }}
              options={[
                { value: '', label: '全部状态' },
                { value: 'OK', label: 'OK' },
                { value: 'ERROR', label: 'ERROR' },
                { value: 'UNSET', label: 'UNSET' },
              ]}
              value={filters.status}
            />
            <Button
              className={primaryButtonClass}
              onClick={refreshTraceQueue}
              type="button"
            >
              <RefreshCw className={cn('size-4', loading && 'animate-spin')} />
              刷新
            </Button>
          </>
        }
        body="按会话、状态和页码筛选 Trace 队列，快速展开 Span 列表和上下文事实。"
        title="运行观测"
      />

      <PanelNotice notice={notice} />

      <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <SurfaceCard>
          <div className="flex flex-col gap-3 p-4">
            <PanelHeading
              title="Trace 队列"
              value={`${pageStart}-${pageEnd} / ${totalCount}`}
            />

            <div className={cn('p-3', innerPanelClass)}>
              <div className="grid gap-2 sm:grid-cols-2">
                <WorkspaceSelect
                  onValueChange={(value) => {
                    setDatePreset(value as TraceDatePreset)
                    setRangeAnchorIso(new Date().toISOString())
                    setTracePage(1)
                  }}
                  options={[
                    { value: '24h', label: '最近 24 小时' },
                    { value: '7d', label: '最近 7 天' },
                    { value: '30d', label: '最近 30 天' },
                    { value: 'custom', label: '自定义日期' },
                  ]}
                  triggerClassName="bg-white dark:bg-slate-950/50"
                  value={datePreset}
                />
                <WorkspaceSelect
                  onValueChange={(value) => {
                    setTraceLimit(Number(value))
                    setTracePage(1)
                  }}
                  options={[
                    { value: '12', label: '每页 12 条' },
                    { value: '25', label: '每页 25 条' },
                    { value: '50', label: '每页 50 条' },
                  ]}
                  triggerClassName="bg-white dark:bg-slate-950/50"
                  value={String(traceLimit)}
                />
              </div>
              {datePreset === 'custom' ? (
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <Input
                    className={cn(
                      fieldClass,
                      '[color-scheme:light] dark:[color-scheme:dark]',
                    )}
                    onChange={(event) => {
                      setCustomStartDate(event.target.value)
                      setTracePage(1)
                    }}
                    type="date"
                    value={customStartDate}
                  />
                  <Input
                    className={cn(
                      fieldClass,
                      '[color-scheme:light] dark:[color-scheme:dark]',
                    )}
                    onChange={(event) => {
                      setCustomEndDate(event.target.value)
                      setTracePage(1)
                    }}
                    type="date"
                    value={customEndDate}
                  />
                </div>
              ) : null}
              <div className="mt-2 text-[11px] text-slate-500 dark:text-slate-400">
                <span>时间范围：{traceDateRange.label}</span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              {traceStats.map((item) => (
                <InlineStat
                  key={item.label}
                  label={item.label}
                  value={item.value}
                />
              ))}
            </div>

            {loading ? (
              <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-950/40 dark:text-slate-400">
                加载 Trace 中...
              </div>
            ) : traceItems.length ? (
              <div className={listFrameClass}>
                {traceItems.map((trace) => (
                  <button
                    className={cn(
                      'w-full p-3 text-left transition-colors',
                      selectedTraceId === trace.trace_id
                        ? 'bg-cyan-50 text-slate-950 dark:bg-cyan-300/10 dark:text-white'
                        : 'bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-950 dark:bg-slate-950/40 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-white',
                    )}
                    key={trace.trace_id}
                    onClick={() => setSelectedTraceId(trace.trace_id)}
                    type="button"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="truncate text-sm font-semibold">
                        {trace.name}
                      </div>
                      <StatusPill
                        tone={trace.status === 'ERROR' ? 'error' : 'ok'}
                      >
                        {trace.status}
                      </StatusPill>
                    </div>
                    <div className="mt-1 text-[11px] text-inherit/60">
                      {compactId(trace.session_id)} ·{' '}
                      {formatIsoDate(trace.start_time)} ·{' '}
                      {formatDurationMs(trace.duration_ms)}
                    </div>
                    <div className="mt-2 h-1.5 rounded-full bg-slate-200 dark:bg-slate-800">
                      <div
                        className={cn(
                          'h-full rounded-full',
                          trace.status === 'ERROR'
                            ? 'bg-gradient-to-r from-rose-400 to-orange-300'
                            : 'bg-gradient-to-r from-cyan-300 to-emerald-300',
                        )}
                        style={{
                          width: `${Math.max(
                            12,
                            (trace.duration_ms / maxDuration) * 100,
                          )}%`,
                        }}
                      />
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <EmptyState body="调整日期或状态筛选。" title="暂无 Trace" />
            )}

            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 p-2 dark:border-slate-800 dark:bg-slate-950/40">
              <Button
                className="h-8 rounded-md px-3"
                disabled={loading || tracePage <= 1}
                onClick={() =>
                  setTracePage((current) => Math.max(1, current - 1))
                }
                type="button"
                variant="outline"
              >
                上一页
              </Button>
              <div className="text-center text-xs text-slate-500 dark:text-slate-300/62">
                第 {tracePage} / {totalPages} 页 · {pageStart}-{pageEnd} /{' '}
                {totalCount}
              </div>
              <Button
                className="h-8 rounded-md px-3"
                disabled={loading || tracePage >= totalPages}
                onClick={() =>
                  setTracePage((current) => Math.min(totalPages, current + 1))
                }
                type="button"
                variant="outline"
              >
                下一页
              </Button>
            </div>
          </div>
        </SurfaceCard>

        <SurfaceCard>
          <div className="flex flex-col gap-4 p-4">
            {detail ? (
              <>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className={panelLabelClass}>Trace detail</div>
                    <div className={cn('mt-1', rowTitleClass)}>
                      {detail.trace.name}
                    </div>
                    <div className="mt-1 font-mono text-xs text-slate-500 dark:text-slate-400">
                      {detail.trace.trace_id}
                    </div>
                  </div>
                  <Button
                    className={secondaryButtonClass}
                    onClick={() => void loadTraceDetail(detail.trace.trace_id)}
                    type="button"
                    variant="outline"
                  >
                    {loadingDetail ? (
                      <RefreshCw className="size-4 animate-spin" />
                    ) : (
                      <Copy className="size-4" />
                    )}
                    重新拉取
                  </Button>
                </div>

                <div className="grid gap-3 md:grid-cols-4">
                  {[
                    {
                      label: 'session_id',
                      value: compactId(detail.trace.session_id),
                    },
                    { label: 'run_id', value: compactId(detail.trace.run_id) },
                    {
                      label: 'duration',
                      value: formatDurationMs(detail.trace.duration_ms),
                    },
                    { label: 'spans', value: `${detail.spans.length}` },
                  ].map((fact) => (
                    <div
                      className="rounded-md border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-950/40"
                      key={fact.label}
                    >
                      <div className="text-[11px] text-slate-500 dark:text-slate-400">
                        {fact.label}
                      </div>
                      <div className="mt-2 truncate text-sm font-semibold text-slate-950 dark:text-white">
                        {fact.value}
                      </div>
                    </div>
                  ))}
                </div>

                <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
                  <div className={cn('p-4', innerPanelClass)}>
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <PanelHeading
                        title="Trace 时间线"
                        value={formatDurationMs(detail.trace.duration_ms)}
                      />
                    </div>

                    <div className="mt-4 flex flex-col gap-3">
                      {selectedTimeline.length ? (
                        selectedTimeline.map((entry) => (
                          <div key={entry.id}>
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <div className="min-w-0">
                                <div className={rowTitleClass}>
                                  {entry.name}
                                </div>
                                <div className={cn('mt-1', mutedTextClass)}>
                                  {entry.kind} ·{' '}
                                  {formatIsoDate(entry.startedAt)}
                                </div>
                              </div>
                              <StatusPill
                                tone={entry.status === 'ERROR' ? 'error' : 'ok'}
                              >
                                {formatDurationMs(entry.durationMs)}
                              </StatusPill>
                            </div>
                            <div className="mt-2 h-2.5 rounded-full border border-slate-200 bg-white p-0.5 dark:border-slate-800 dark:bg-slate-950/60">
                              <div
                                className={cn(
                                  'h-full rounded-full',
                                  entry.status === 'ERROR'
                                    ? 'bg-gradient-to-r from-rose-400 to-orange-300'
                                    : 'bg-gradient-to-r from-cyan-300 to-emerald-300',
                                )}
                                style={{
                                  marginLeft: `${entry.offsetPercent}%`,
                                  width: `${Math.min(
                                    100 - entry.offsetPercent,
                                    entry.widthPercent,
                                  )}%`,
                                }}
                              />
                            </div>
                          </div>
                        ))
                      ) : (
                        <EmptyState
                          body="该 Trace 尚无 Span。"
                          title="暂无时间线"
                        />
                      )}
                    </div>
                  </div>

                  <div className={cn('p-4', innerPanelClass)}>
                    <PanelHeading
                      title="关联对话"
                      value={compactId(detail.trace.session_id)}
                    />
                    <div className="mt-4 flex max-h-[26rem] flex-col gap-3 overflow-y-auto pr-1">
                      {loadingConversation ? (
                        <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-950/50 dark:text-slate-400">
                          加载对话中...
                        </div>
                      ) : conversationSummaries.length ? (
                        conversationSummaries.map((message) => (
                          <div
                            className={cn(
                              'rounded-lg border p-3',
                              message.label === '用户'
                                ? 'border-cyan-200 bg-cyan-50 dark:border-cyan-300/20 dark:bg-cyan-300/10'
                                : 'border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950/45',
                            )}
                            key={message.id}
                          >
                            <div className="text-[11px] font-semibold tracking-[0.12em] text-slate-500 uppercase dark:text-slate-400">
                              {message.label}
                            </div>
                            <div className="mt-2 line-clamp-5 text-sm leading-6 text-slate-600 dark:text-slate-300">
                              {message.content}
                            </div>
                          </div>
                        ))
                      ) : (
                        <EmptyState
                          body="该 Trace 暂无历史消息。"
                          title="暂无关联对话"
                        />
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex flex-col gap-3">
                  <PanelHeading
                    title="Span waterfall"
                    value={`${detail.spans.length}`}
                  />
                  {detail.spans.map((span) => (
                    <div
                      className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950/45"
                      key={span.span_id}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <div className={rowTitleClass}>{span.name}</div>
                          <div className={cn('mt-1', mutedTextClass)}>
                            {span.kind || 'span'} ·{' '}
                            {formatIsoDate(span.start_time)}
                          </div>
                        </div>
                        <StatusPill
                          tone={span.status_code === 'ERROR' ? 'error' : 'ok'}
                        >
                          {span.status_code}
                        </StatusPill>
                      </div>
                      <div className="mt-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
                        {formatDurationMs(span.duration_ms)}
                      </div>
                      {span.attributes ? (
                        <pre className="mt-3 overflow-x-auto rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs leading-6 text-slate-600 dark:border-slate-800 dark:bg-slate-950/70 dark:text-slate-300">
                          {JSON.stringify(span.attributes, null, 2)}
                        </pre>
                      ) : null}
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <EmptyState
                body="从左侧选择一个 Trace 进入详情查看。"
                title="选择一次 Agent Run"
              />
            )}
          </div>
        </SurfaceCard>
      </div>
    </div>
  )
}

function McpPanel({ previewMode }: { previewMode: boolean }) {
  const [bundle, setBundle] = useState<McpBundle | null>(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState<NoticeState>(null)
  const [createdToken, setCreatedToken] = useState('')
  const [tokenName, setTokenName] = useState('')
  const [tokenExpires, setTokenExpires] = useState(604_800)
  const [agentName, setAgentName] = useState('')
  const [agentUrl, setAgentUrl] = useState('')
  const [agentDescription, setAgentDescription] = useState('')
  const [agentEnabled, setAgentEnabled] = useState(true)

  const loadMcp = useEffectEvent(async () => {
    setLoading(true)
    try {
      setBundle(await loadMcpBundle())
      setNotice(
        previewMode
          ? {
              tone: 'info',
              title: 'MCP 当前使用本地配置',
              detail:
                '服务切换、Token 签发和 Hi-Agent 注册会写入当前本地配置。',
            }
          : null,
      )
    } catch (error) {
      setNotice({
        tone: 'error',
        title: '加载 MCP 数据失败',
        detail: error instanceof Error ? error.message : '请稍后重试',
      })
    } finally {
      setLoading(false)
    }
  })

  useEffect(() => {
    void loadMcp()
  }, [previewMode])

  const toggleService = useEffectEvent(
    async (id: 'basic' | 'agent' | 'playbook', enabled: boolean) => {
      await setMcpServiceEnabled(id, enabled)
      await loadMcp()
    },
  )

  const issueToken = useEffectEvent(async () => {
    if (!tokenName.trim()) {
      setNotice({
        tone: 'error',
        title: '请先填写 Token 名称',
      })
      return
    }
    const token = await createMcpToken(tokenName.trim(), tokenExpires)
    setCreatedToken(token)
    setTokenName('')
    await loadMcp()
    setNotice({
      tone: 'success',
      title: '新的 MCP Token 已生成',
      detail: '请在右侧立即复制，该字段只会在本地弹出一次。',
    })
  })

  const submitHiAgent = useEffectEvent(async () => {
    if (!agentName.trim() || !agentUrl.trim()) {
      setNotice({
        tone: 'error',
        title: 'Hi-Agent 名称和 URL 不能为空',
      })
      return
    }
    await addHiAgent({
      name: agentName.trim(),
      url: agentUrl.trim(),
      description: agentDescription.trim(),
      enabled: agentEnabled,
    })
    setAgentName('')
    setAgentUrl('')
    setAgentDescription('')
    setAgentEnabled(true)
    await loadMcp()
    setNotice({
      tone: 'success',
      title: 'Hi-Agent 已注册',
    })
  })

  return (
    <div className="flex flex-col gap-4">
      <SectionIntro
        actions={
          <Button
            className={primaryButtonClass}
            onClick={() => void loadMcp()}
            type="button"
          >
            <RefreshCw className={cn('size-4', loading && 'animate-spin')} />
            刷新
          </Button>
        }
        body="集中管理 MCP 服务启停、访问 Token 和外部 Hi-Agent 注册状态。"
        title="MCP 工具中枢"
      />

      <PanelNotice notice={notice} />

      <div className="grid gap-4 xl:grid-cols-4">
        <MetricCard
          hint="已启用服务"
          icon={Cable}
          label="服务"
          value={`${bundle ? Object.values(bundle.config.services).filter(Boolean).length : 0}`}
        />
        <MetricCard
          hint="已签发访问凭证"
          icon={KeyRound}
          label="Tokens"
          value={`${bundle?.tokens.length ?? 0}`}
        />
        <MetricCard
          hint="外部接入 Agent"
          icon={Bot}
          label="Hi-Agent"
          value={`${bundle?.hiAgents.length ?? 0}`}
        />
        <MetricCard
          hint="管理模式"
          icon={Network}
          label="模式"
          value={bundle?.config.control_mode ?? '--'}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <SurfaceCard>
          <div className="flex flex-col gap-4 p-4">
            <div className="grid gap-4 lg:grid-cols-3">
              {bundle
                ? (['basic', 'agent', 'playbook'] as const).map((id) => (
                    <div
                      className="rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/45"
                      key={id}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className={rowTitleClass}>{id}</div>
                          <div className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
                            {id === 'basic'
                              ? '基础工具'
                              : id === 'agent'
                                ? 'Agent 编排'
                                : '剧本闸门'}
                          </div>
                        </div>
                        <Switch
                          checked={bundle.config.services[id]}
                          onCheckedChange={(checked) =>
                            void toggleService(id, checked)
                          }
                        />
                      </div>
                      <div className="mt-4">
                        <StatusPill
                          tone={bundle.config.services[id] ? 'ok' : 'muted'}
                        >
                          {bundle.config.services[id] ? '启用' : '停用'}
                        </StatusPill>
                      </div>
                    </div>
                  ))
                : null}
            </div>

            <div className="grid gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
              <div className={cn('p-4', innerPanelClass)}>
                <PanelHeading title="签发 Token" />
                <div className="mt-4 flex flex-col gap-3">
                  <Input
                    className={fieldClass}
                    onChange={(event) => setTokenName(event.target.value)}
                    placeholder="Token 名称，例如 AgentOS"
                    value={tokenName}
                  />
                  <WorkspaceSelect
                    onValueChange={(value) => setTokenExpires(Number(value))}
                    options={[
                      { value: '86400', label: '1 天' },
                      { value: '604800', label: '7 天' },
                      { value: '2592000', label: '30 天' },
                      { value: '0', label: '永久' },
                    ]}
                    triggerClassName="w-full"
                    value={String(tokenExpires)}
                  />
                  <Button
                    className={cn(primaryButtonClass, 'w-full')}
                    onClick={() => void issueToken()}
                    type="button"
                  >
                    生成 Token
                  </Button>
                  {createdToken ? (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-300/20 dark:bg-amber-300/10 dark:text-amber-50">
                      <div className="font-semibold">
                        仅展示一次，请立即复制
                      </div>
                      <div className="mt-2 break-all font-mono">
                        {createdToken}
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>

              <div className={cn('p-4', innerPanelClass)}>
                <PanelHeading
                  title="已签发 Token"
                  value={`${bundle?.tokens.length ?? 0}`}
                />
                <div className="mt-4 flex flex-col gap-3">
                  {bundle?.tokens.length ? (
                    bundle.tokens.map((token) => (
                      <div
                        className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950/60"
                        key={token.id}
                      >
                        <div className="min-w-0">
                          <div className={rowTitleClass}>{token.name}</div>
                          <div className="mt-1 truncate font-mono text-[11px] text-slate-500 dark:text-slate-400">
                            {token.token}
                          </div>
                          <div className={cn('mt-2', mutedTextClass)}>
                            创建 {formatUnixDate(token.created_at)} · 过期{' '}
                            {formatUnixDate(token.expires_at)}
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <Button
                            className={secondaryButtonClass}
                            onClick={() =>
                              navigator.clipboard
                                .writeText(token.token)
                                .then(() =>
                                  setNotice({
                                    tone: 'success',
                                    title: 'Token 已复制',
                                  }),
                                )
                                .catch(() =>
                                  setNotice({
                                    tone: 'error',
                                    title: '复制失败',
                                  }),
                                )
                            }
                            type="button"
                            variant="outline"
                          >
                            复制
                          </Button>
                          <Button
                            className={dangerButtonClass}
                            onClick={() =>
                              void deleteMcpToken(token.id).then(loadMcp)
                            }
                            type="button"
                            variant="outline"
                          >
                            删除
                          </Button>
                        </div>
                      </div>
                    ))
                  ) : (
                    <EmptyState
                      body="当前还没有任何访问 Token。"
                      title="暂无 Token"
                    />
                  )}
                </div>
              </div>
            </div>
          </div>
        </SurfaceCard>

        <SurfaceCard>
          <div className="flex flex-col gap-5 p-4">
            <div>
              <PanelHeading title="接入上下文" />
              <div className="mt-4 flex flex-col gap-3">
                {[
                  {
                    label: '管理模式',
                    value: bundle?.config.control_mode ?? '--',
                  },
                  { label: 'FastMCP', value: bundle?.config.fastmcp ?? '--' },
                  { label: 'MCP URL', value: bundle?.config.mcp_url ?? '--' },
                  {
                    label: 'Config',
                    value: bundle?.config.config_path ?? '--',
                  },
                ].map((item) => (
                  <div
                    className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-950/45"
                    key={item.label}
                  >
                    <div className="text-[11px] text-slate-500 dark:text-slate-400">
                      {item.label}
                    </div>
                    <div className="mt-1 break-all text-sm font-semibold text-slate-950 dark:text-white">
                      {item.value}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <PanelHeading title="注册 Hi-Agent" />
              <div className="mt-4 flex flex-col gap-3">
                <Input
                  className={fieldClass}
                  onChange={(event) => setAgentName(event.target.value)}
                  placeholder="名称，例如 CVE Hunter"
                  value={agentName}
                />
                <Input
                  className={fieldClass}
                  onChange={(event) => setAgentUrl(event.target.value)}
                  placeholder="MCP URL"
                  value={agentUrl}
                />
                <Textarea
                  className={cn(textAreaClass, 'min-h-28')}
                  onChange={(event) => setAgentDescription(event.target.value)}
                  placeholder="能力描述"
                  value={agentDescription}
                />
                <label className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-950/45 dark:text-slate-200">
                  默认启用
                  <Switch
                    checked={agentEnabled}
                    onCheckedChange={setAgentEnabled}
                  />
                </label>
                <Button
                  className={cn(primaryButtonClass, 'w-full')}
                  onClick={() => void submitHiAgent()}
                  type="button"
                >
                  注册 Hi-Agent
                </Button>
              </div>
            </div>

            <div className="flex flex-col gap-3">
              <PanelHeading
                title="已接入 Agent"
                value={`${bundle?.hiAgents.length ?? 0}`}
              />
              {bundle?.hiAgents.length ? (
                bundle.hiAgents.map((agent) => (
                  <div
                    className="rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/45"
                    key={agent.url}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className={rowTitleClass}>{agent.name}</div>
                        <div className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
                          {agent.description || '未提供能力描述'}
                        </div>
                        <div className="mt-2 break-all font-mono text-[11px] text-slate-500 dark:text-slate-500">
                          {agent.url}
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <Switch
                          checked={agent.enabled}
                          onCheckedChange={(checked) =>
                            void setHiAgentEnabled(agent.url, checked).then(
                              loadMcp,
                            )
                          }
                        />
                        <Button
                          className={dangerButtonClass}
                          onClick={() =>
                            void deleteHiAgent(agent.url).then(loadMcp)
                          }
                          type="button"
                          variant="outline"
                        >
                          删除
                        </Button>
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <EmptyState
                  body="当前没有任何外部 Hi-Agent 接入。"
                  title="暂无外部 Agent"
                />
              )}
            </div>
          </div>
        </SurfaceCard>
      </div>
    </div>
  )
}

function CvePanel({ previewMode }: { previewMode: boolean }) {
  const [query, setQuery] = useState('')
  const [source, setSource] = useState('')
  const [results, setResults] = useState<
    Array<Awaited<ReturnType<typeof searchCves>>['items'][number]>
  >([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const [loading, setLoading] = useState(false)
  const [notice, setNotice] = useState<NoticeState>(
    previewMode
      ? {
          tone: 'info',
          title: '当前使用本地漏洞情报',
          detail: '搜索和情报刷新在后端不可达时会使用本地数据集。',
        }
      : null,
  )

  const runSearch = useEffectEvent(async () => {
    if (!query.trim()) {
      setNotice({
        tone: 'error',
        title: '请输入 CVE 编号、组件名或漏洞关键词',
      })
      return
    }
    setLoading(true)
    try {
      const response = await searchCves({
        query: query.trim(),
        source: source || undefined,
        page,
        size,
      })
      setResults(response.items)
      setTotal(response.total)
      setNotice({
        tone: 'success',
        title: '漏洞检索完成',
        detail: `命中 ${response.total} 条记录。`,
      })
    } catch (error) {
      setNotice({
        tone: 'error',
        title: '漏洞检索失败',
        detail: error instanceof Error ? error.message : '请稍后重试',
      })
    } finally {
      setLoading(false)
    }
  })

  useEffect(() => {
    if (page > 1 && query.trim()) {
      void runSearch()
    }
  }, [page, query, size, source])

  return (
    <div className="flex flex-col gap-4">
      <SectionIntro
        actions={
          <Button
            className={primaryButtonClass}
            onClick={() =>
              void refreshCveCatalog()
                .then((result) =>
                  setNotice({
                    tone: 'success',
                    title: '情报源已刷新',
                    detail: result.message ?? '已重新拉取漏洞情报数据。',
                  }),
                )
                .catch((error) =>
                  setNotice({
                    tone: 'error',
                    title: '刷新情报源失败',
                    detail:
                      error instanceof Error ? error.message : '请稍后重试',
                  }),
                )
            }
            type="button"
          >
            刷新情报
          </Button>
        }
        body="按编号、关键词和来源检索漏洞情报，支持分页查看与情报刷新。"
        title="CVE 情报"
      />

      <PanelNotice notice={notice} />

      <SurfaceCard>
        <div className="flex flex-col gap-4 p-4">
          <div className="flex flex-col gap-3 lg:flex-row">
            <Input
              className={fieldClass}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="输入 CVE 编号、组件名或漏洞关键词"
              value={query}
            />
            <WorkspaceSelect
              onValueChange={setSource}
              options={[
                { value: '', label: '全部来源' },
                { value: 'NVD', label: 'NVD' },
                { value: 'GitHub', label: 'GitHub' },
                { value: 'ExploitDB', label: 'ExploitDB' },
              ]}
              triggerClassName="bg-slate-50 dark:bg-slate-950/70"
              value={source}
            />
            <Button
              className={primaryButtonClass}
              onClick={() => {
                setPage(1)
                void runSearch()
              }}
              type="button"
            >
              {loading ? (
                <RefreshCw className="size-4 animate-spin" />
              ) : (
                <Search className="size-4" />
              )}
              搜索
            </Button>
          </div>

          <div className="flex flex-wrap gap-2">
            {['CVE-2026', 'nginx', 'spring'].map((sample) => (
              <button
                className="rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-500 transition-colors hover:bg-white hover:text-slate-950 dark:border-slate-800 dark:bg-slate-950/45 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-white"
                key={sample}
                onClick={() => setQuery(sample)}
                type="button"
              >
                {sample}
              </button>
            ))}
          </div>

          <div className="grid gap-3">
            {results.length ? (
              results.map((item) => (
                <div
                  className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950/45"
                  key={item.id}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-base font-semibold text-slate-950 dark:text-white">
                        {item.cve_id}
                      </div>
                      <div className={cn('mt-1', mutedTextClass)}>
                        {item.source} · {item.create_time}
                      </div>
                    </div>
                    <a
                      className="text-sm font-semibold text-cyan-200 hover:text-cyan-100"
                      href={item.github_url}
                      rel="noreferrer"
                      target="_blank"
                    >
                      查看源
                    </a>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
                    {item.description}
                  </p>
                </div>
              ))
            ) : (
              <EmptyState
                body="输入一个 CVE 编号、组件名或关键词后开始检索。"
                title="等待检索条件"
              />
            )}
          </div>

          {results.length ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-950/45 dark:text-slate-400">
              <span>共 {total} 条记录</span>
              <div className="flex items-center gap-2">
                <WorkspaceSelect
                  onValueChange={(value) => setSize(Number(value))}
                  options={[
                    { value: '10', label: '10 / page' },
                    { value: '20', label: '20 / page' },
                    { value: '50', label: '50 / page' },
                  ]}
                  triggerClassName="text-xs"
                  value={String(size)}
                />
                <Button
                  className={secondaryButtonClass}
                  disabled={page === 1}
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  type="button"
                  variant="outline"
                >
                  上一页
                </Button>
                <Button
                  className={secondaryButtonClass}
                  disabled={page * size >= total}
                  onClick={() => setPage((current) => current + 1)}
                  type="button"
                  variant="outline"
                >
                  下一页
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      </SurfaceCard>
    </div>
  )
}

function AssetPanel({ previewMode }: { previewMode: boolean }) {
  const [mode, setMode] = useState<'fingerprint' | 'ip'>('fingerprint')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<AssetResult[]>([])
  const [allResults, setAllResults] = useState<AssetResult[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedIpType, setSelectedIpType] = useState('')
  const [selectedStatus, setSelectedStatus] = useState('')
  const [selectedTag, setSelectedTag] = useState('')
  const [notice, setNotice] = useState<NoticeState>(
    previewMode
      ? {
          tone: 'info',
          title: '资产画像使用本地数据',
          detail: '可按指纹或 IP 对本地资产数据执行同样的筛选链路。',
        }
      : null,
  )

  const runSearch = useEffectEvent(async () => {
    if (!query.trim()) {
      setNotice({
        tone: 'error',
        title: mode === 'ip' ? '请输入 IP 地址' : '请输入指纹关键字',
      })
      return
    }
    setLoading(true)
    try {
      const response = await searchAssets({
        mode,
        query: query.trim(),
        page: 1,
        size: 100,
      })
      setAllResults(response.items)
      setNotice({
        tone: 'success',
        title: '资产检索完成',
        detail: `命中 ${response.total} 条资产记录。`,
      })
    } catch (error) {
      setNotice({
        tone: 'error',
        title: '资产检索失败',
        detail: error instanceof Error ? error.message : '请稍后重试',
      })
    } finally {
      setLoading(false)
    }
  })

  useEffect(() => {
    const next = allResults.filter((item) => {
      if (selectedIpType && item.ip_type !== selectedIpType) return false
      if (selectedStatus && String(item.status) !== selectedStatus) return false
      if (selectedTag && !item.tag.includes(selectedTag)) return false
      return true
    })
    setResults(next)
  }, [allResults, selectedIpType, selectedStatus, selectedTag])

  const ipTypes = [...new Set(allResults.map((item) => item.ip_type))]
  const statuses = [...new Set(allResults.map((item) => String(item.status)))]
  const tags = [...new Set(allResults.flatMap((item) => item.tag))]

  return (
    <div className="flex flex-col gap-4">
      <SectionIntro
        body="通过指纹和 IP 查询资产画像，快速定位暴露面、端口和归属信息。"
        title="资产画像"
      />

      <PanelNotice notice={notice} />

      <SurfaceCard>
        <div className="flex flex-col gap-4 p-4">
          <div className="flex flex-col gap-3 lg:flex-row">
            <div className="flex rounded-md border border-slate-200 bg-slate-50 p-1 dark:border-slate-800 dark:bg-slate-950/45">
              {[
                { id: 'fingerprint', label: '指纹' },
                { id: 'ip', label: 'IP' },
              ].map((item) => (
                <button
                  className={cn(
                    'rounded-md px-4 py-1.5 text-sm transition-colors',
                    mode === item.id
                      ? 'bg-cyan-300 text-slate-950'
                      : 'text-slate-500 hover:text-slate-950 dark:text-slate-400 dark:hover:text-white',
                  )}
                  key={item.id}
                  onClick={() => setMode(item.id as 'fingerprint' | 'ip')}
                  type="button"
                >
                  {item.label}
                </button>
              ))}
            </div>
            <Input
              className={fieldClass}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={
                mode === 'ip'
                  ? '输入 IP 地址，例如 10.10.4.18'
                  : '输入指纹，例如 Nginx、Vue、React'
              }
              value={query}
            />
            <Button
              className={primaryButtonClass}
              onClick={() => void runSearch()}
              type="button"
            >
              {loading ? (
                <RefreshCw className="size-4 animate-spin" />
              ) : (
                <Search className="size-4" />
              )}
              搜索
            </Button>
          </div>

          {allResults.length ? (
            <div className="grid gap-3 md:grid-cols-4">
              <WorkspaceSelect
                onValueChange={setSelectedIpType}
                options={[
                  { value: '', label: '全部 IP 类型' },
                  ...ipTypes.map((item) => ({ value: item, label: item })),
                ]}
                triggerClassName="w-full"
                value={selectedIpType}
              />
              <WorkspaceSelect
                onValueChange={setSelectedStatus}
                options={[
                  { value: '', label: '全部状态码' },
                  ...statuses.map((item) => ({ value: item, label: item })),
                ]}
                triggerClassName="w-full"
                value={selectedStatus}
              />
              <WorkspaceSelect
                onValueChange={setSelectedTag}
                options={[
                  { value: '', label: '全部标签' },
                  ...tags.map((item) => ({ value: item, label: item })),
                ]}
                triggerClassName="w-full"
                value={selectedTag}
              />
              <Button
                className={secondaryButtonClass}
                onClick={() => {
                  setSelectedIpType('')
                  setSelectedStatus('')
                  setSelectedTag('')
                }}
                type="button"
                variant="outline"
              >
                清空筛选
              </Button>
            </div>
          ) : null}

          <div className="grid gap-3 lg:grid-cols-2">
            {results.length ? (
              results.map((asset) => (
                <div
                  className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950/45"
                  key={`${asset.site}-${asset.ip}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <a
                        className="truncate text-base font-semibold text-cyan-200 hover:text-cyan-100"
                        href={asset.site}
                        rel="noreferrer"
                        target="_blank"
                      >
                        {asset.title}
                      </a>
                      <div className={cn('mt-1 truncate', mutedTextClass)}>
                        {asset.site}
                      </div>
                    </div>
                    <StatusPill tone="muted">{asset.status}</StatusPill>
                  </div>

                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-950/60">
                      <div className="text-[11px] text-slate-500 dark:text-slate-400">
                        IP / Host
                      </div>
                      <div className="mt-1 text-sm text-slate-950 dark:text-white">
                        {asset.ip} · {asset.hostname || 'n/a'}
                      </div>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-950/60">
                      <div className="text-[11px] text-slate-500 dark:text-slate-400">
                        Server
                      </div>
                      <div className="mt-1 text-sm text-slate-950 dark:text-white">
                        {asset.http_server || 'unknown'}
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 flex flex-wrap gap-2">
                    {asset.finger.map((finger) => (
                      <span
                        className="rounded-md border border-cyan-200 bg-cyan-50 px-2.5 py-1 text-[11px] text-cyan-800 dark:border-cyan-300/18 dark:bg-cyan-300/10 dark:text-cyan-100"
                        key={`${asset.site}-${finger}`}
                      >
                        {finger}
                      </span>
                    ))}
                    {asset.tag.map((tag) => (
                      <span
                        className="rounded-md border border-slate-200 px-2.5 py-1 text-[11px] text-slate-500 dark:border-slate-800 dark:text-slate-400"
                        key={`${asset.site}-${tag}`}
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              ))
            ) : (
              <EmptyState
                body="输入指纹或 IP 后开始检索。"
                title="等待资产查询"
              />
            )}
          </div>
        </div>
      </SurfaceCard>
    </div>
  )
}

function Url2MdPanel({ previewMode }: { previewMode: boolean }) {
  const [url, setUrl] = useState('')
  const [markdown, setMarkdown] = useState('')
  const [view, setView] = useState<'markdown' | 'preview'>('markdown')
  const [loading, setLoading] = useState(false)
  const [notice, setNotice] = useState<NoticeState>(
    previewMode
      ? {
          tone: 'info',
          title: 'URL 解析使用本地结果',
          detail: '当后端不可达时，会返回一份可编辑的示例 Markdown。',
        }
      : null,
  )

  const handleParse = useEffectEvent(async () => {
    try {
      new URL(url)
    } catch {
      setNotice({
        tone: 'error',
        title: '请输入有效的 URL',
      })
      return
    }

    setLoading(true)
    try {
      const response = await parseUrlToMarkdown(url)
      const nextMarkdown = Array.isArray(response.markdown)
        ? response.markdown.join('\n\n')
        : response.markdown || ''
      setMarkdown(nextMarkdown)
      setNotice({
        tone: 'success',
        title: '网页内容已转换',
      })
    } catch (error) {
      setNotice({
        tone: 'error',
        title: 'URL 解析失败',
        detail: error instanceof Error ? error.message : '请稍后重试',
      })
    } finally {
      setLoading(false)
    }
  })

  return (
    <div className="flex flex-col gap-4">
      <SectionIntro
        body="将网页正文转换为 Markdown，并在工作台内完成复制、查看和知识沉淀准备。"
        title="网页解析"
      />

      <PanelNotice notice={notice} />

      <SurfaceCard>
        <div className="flex flex-col gap-4 p-4">
          <div className="flex flex-col gap-3 lg:flex-row">
            <Input
              className={fieldClass}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="请输入要解析的网址，例如 https://example.com"
              value={url}
            />
            <Button
              className={primaryButtonClass}
              onClick={() => void handleParse()}
              type="button"
            >
              {loading ? (
                <RefreshCw className="size-4 animate-spin" />
              ) : (
                <Link2 className="size-4" />
              )}
              解析
            </Button>
            <Button
              className={secondaryButtonClass}
              onClick={() => {
                setUrl('')
                setMarkdown('')
              }}
              type="button"
              variant="outline"
            >
              清空
            </Button>
          </div>

          <div className="flex gap-2">
            {[
              { id: 'markdown', label: 'Markdown 文本' },
              { id: 'preview', label: '渲染视图' },
            ].map((item) => (
              <button
                className={cn(
                  'rounded-md border px-3 py-1.5 text-sm transition-colors',
                  view === item.id
                    ? 'border-cyan-300/30 bg-cyan-50 text-cyan-800 dark:bg-cyan-300/12 dark:text-white'
                    : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50 hover:text-slate-950 dark:border-slate-800 dark:bg-slate-950/45 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-white',
                )}
                key={item.id}
                onClick={() => setView(item.id as 'markdown' | 'preview')}
                type="button"
              >
                {item.label}
              </button>
            ))}
          </div>

          {markdown ? (
            view === 'markdown' ? (
              <div className="relative">
                <Textarea
                  className={cn(textAreaClass, 'min-h-[24rem]')}
                  onChange={(event) => setMarkdown(event.target.value)}
                  value={markdown}
                />
                <Button
                  className={cn(secondaryButtonClass, 'absolute right-4 top-4')}
                  onClick={() =>
                    navigator.clipboard
                      .writeText(markdown)
                      .then(() =>
                        setNotice({
                          tone: 'success',
                          title: 'Markdown 已复制',
                        }),
                      )
                      .catch(() =>
                        setNotice({
                          tone: 'error',
                          title: '复制失败',
                        }),
                      )
                  }
                  type="button"
                  variant="outline"
                >
                  复制
                </Button>
              </div>
            ) : (
              <Streamdown
                className="prose prose-sm min-h-[24rem] max-w-none rounded-lg border border-slate-200 bg-white p-5 text-slate-700 dark:prose-invert dark:border-slate-800 dark:bg-slate-950/45 dark:text-slate-100"
                controls={{ code: { copy: true }, table: true }}
                mode="static"
                parseIncompleteMarkdown={false}
              >
                {markdown}
              </Streamdown>
            )
          ) : (
            <EmptyState
              body="输入一个 URL 并执行解析后，工作台会把 Markdown 文本和渲染视图同时准备好。"
              title="等待 URL 解析"
            />
          )}
        </div>
      </SurfaceCard>
    </div>
  )
}

function SkillsPanel({ previewMode }: { previewMode: boolean }) {
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [notice, setNotice] = useState<NoticeState>(
    previewMode
      ? {
          tone: 'info',
          title: 'Skills 使用本地状态',
          detail: '启用或禁用 Skill 会即时反映在当前本地状态里。',
        }
      : null,
  )

  const loadAllSkills = useEffectEvent(async () => {
    setLoading(true)
    try {
      setSkills(await loadSkills())
    } catch (error) {
      setNotice({
        tone: 'error',
        title: '加载 Skills 失败',
        detail: error instanceof Error ? error.message : '请稍后重试',
      })
    } finally {
      setLoading(false)
    }
  })

  useEffect(() => {
    void loadAllSkills()
  }, [])

  return (
    <div className="flex flex-col gap-4">
      <SectionIntro
        actions={
          <Button
            className={primaryButtonClass}
            onClick={() => void loadAllSkills()}
            type="button"
          >
            <RefreshCw className={cn('size-4', loading && 'animate-spin')} />
            刷新
          </Button>
        }
        body="管理安全能力模块开关、脚本清单和说明信息，为 Agent 编排提供能力边界。"
        title="Skills 管理"
      />

      <PanelNotice notice={notice} />

      <div className="grid gap-4">
        {loading ? (
          <SurfaceCard>
            <div className="p-6 text-sm text-slate-500 dark:text-slate-400">
              加载 Skills 中...
            </div>
          </SurfaceCard>
        ) : skills.length ? (
          skills.map((skill) => (
            <SurfaceCard key={skill.name}>
              <div className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={cn(
                          'size-2 rounded-full',
                          skill.enabled ? 'bg-emerald-300' : 'bg-slate-500',
                        )}
                      />
                      <div className="truncate text-base font-semibold text-slate-950 dark:text-white">
                        {skill.name}
                      </div>
                      {skill.has_scripts ? (
                        <span className="rounded-md border border-slate-200 px-2 py-0.5 text-[10px] text-slate-500 dark:border-slate-800 dark:text-slate-400">
                          {skill.scripts.length} scripts
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                      {skill.description || '暂无描述'}
                    </div>
                    {skill.has_scripts ? (
                      <button
                        className="mt-3 text-xs font-semibold text-cyan-200 hover:text-cyan-100"
                        onClick={() =>
                          setExpanded((current) => ({
                            ...current,
                            [skill.name]: !current[skill.name],
                          }))
                        }
                        type="button"
                      >
                        {expanded[skill.name]
                          ? '收起脚本'
                          : `查看 ${skill.scripts.length} 个脚本`}
                      </button>
                    ) : null}
                    {expanded[skill.name] ? (
                      <div className="mt-4 flex flex-wrap gap-2">
                        {skill.scripts.map((script) => (
                          <span
                            className="rounded-md border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] text-slate-500 dark:border-slate-800 dark:bg-slate-950/45 dark:text-slate-400"
                            key={script}
                          >
                            {script}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <Switch
                    checked={skill.enabled}
                    onCheckedChange={(checked) =>
                      void setSkillEnabled(skill.name, checked).then(() => {
                        setSkills((current) =>
                          current.map((item) =>
                            item.name === skill.name
                              ? { ...item, enabled: checked }
                              : item,
                          ),
                        )
                        setNotice({
                          tone: 'success',
                          title: `${skill.name} 已${checked ? '启用' : '禁用'}`,
                        })
                      })
                    }
                  />
                </div>
              </div>
            </SurfaceCard>
          ))
        ) : (
          <EmptyState body="当前没有任何 Skill 能力模块。" title="暂无 Skill" />
        )}
      </div>
    </div>
  )
}

function SettingsPanel({ previewMode }: { previewMode: boolean }) {
  const [bundle, setBundle] = useState<SettingsBundle | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<NoticeState>(
    previewMode
      ? {
          tone: 'info',
          title: '系统配置使用本地状态',
          detail: '模型和运行时参数的修改会保存到当前浏览器会话里的本地状态。',
        }
      : null,
  )

  const loadBundle = useEffectEvent(async () => {
    setLoading(true)
    try {
      setBundle(await loadSettingsBundle())
    } catch (error) {
      setNotice({
        tone: 'error',
        title: '加载配置失败',
        detail: error instanceof Error ? error.message : '请稍后重试',
      })
    } finally {
      setLoading(false)
    }
  })

  useEffect(() => {
    void loadBundle()
  }, [])

  const saveAll = useEffectEvent(async () => {
    if (!bundle) return
    setSaving(true)
    try {
      const next = await saveSettingsBundle(bundle)
      setBundle(next)
      setNotice({
        tone: 'success',
        title: '配置已保存',
      })
    } catch (error) {
      setNotice({
        tone: 'error',
        title: '保存配置失败',
        detail: error instanceof Error ? error.message : '请稍后重试',
      })
    } finally {
      setSaving(false)
    }
  })

  return (
    <div className="flex flex-col gap-4">
      <SectionIntro
        actions={
          <>
            <Button
              className={secondaryButtonClass}
              onClick={() =>
                setBundle((current) => {
                  if (!current) return current
                  return {
                    ...current,
                    models: [
                      ...current.models,
                      {
                        id: `custom-${Date.now()}`,
                        name: 'Custom Model',
                        model_id: '',
                        base_url: '',
                        api_key: '',
                        description: '用于自定义路由的新增模型。',
                        enabled: true,
                        builtin: false,
                        configured: false,
                      },
                    ],
                  }
                })
              }
              type="button"
              variant="outline"
            >
              新增模型
            </Button>
            <Button
              className={primaryButtonClass}
              onClick={() => void saveAll()}
              type="button"
            >
              {saving ? (
                <RefreshCw className="size-4 animate-spin" />
              ) : (
                <ArrowRight className="size-4" />
              )}
              保存
            </Button>
          </>
        }
        body="维护模型路由、默认模型和运行时参数，让 Agent 调用保持可控、可审计。"
        title="系统配置"
      />

      <PanelNotice notice={notice} />

      {loading || !bundle ? (
        <SurfaceCard>
          <div className="p-6 text-sm text-slate-500 dark:text-slate-400">
            加载系统配置中...
          </div>
        </SurfaceCard>
      ) : (
        <>
          <SurfaceCard>
            <div className="flex flex-col gap-5 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className={panelLabelClass}>模型路由</div>
                </div>
                <WorkspaceSelect
                  onValueChange={(value) =>
                    setBundle((current) =>
                      current
                        ? { ...current, active_model_id: value }
                        : current,
                    )
                  }
                  options={bundle.models
                    .filter((model) => model.enabled)
                    .map((model) => ({
                      value: model.id,
                      label: model.name,
                    }))}
                  triggerClassName="bg-slate-50 dark:bg-slate-950/70"
                  value={bundle.active_model_id}
                />
              </div>

              <div className="grid gap-4">
                {bundle.models.map((model, index) => (
                  <div
                    className="rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/45"
                    key={model.id}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="grid size-8 place-items-center rounded-md border border-slate-200 bg-white text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-300">
                            {index + 1}
                          </span>
                          <div className="truncate text-base font-semibold text-slate-950 dark:text-white">
                            {model.name || '未命名模型'}
                          </div>
                          {model.builtin ? (
                            <span className="rounded-md border border-slate-200 px-2 py-0.5 text-[10px] text-slate-500 dark:border-slate-800 dark:text-slate-400">
                              Builtin
                            </span>
                          ) : null}
                          {bundle.active_model_id === model.id ? (
                            <span className="rounded-md border border-cyan-200 bg-cyan-50 px-2 py-0.5 text-[10px] text-cyan-800 dark:border-cyan-300/20 dark:bg-cyan-300/10 dark:text-cyan-100">
                              Default
                            </span>
                          ) : null}
                        </div>
                        <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                          {model.description || '自定义模型参数'}
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <Switch
                          checked={model.enabled}
                          onCheckedChange={(checked) =>
                            setBundle((current) =>
                              current
                                ? {
                                    ...current,
                                    models: current.models.map((item) =>
                                      item.id === model.id
                                        ? { ...item, enabled: checked }
                                        : item,
                                    ),
                                  }
                                : current,
                            )
                          }
                        />
                        {!model.builtin ? (
                          <Button
                            className={dangerButtonClass}
                            onClick={() =>
                              setBundle((current) =>
                                current
                                  ? {
                                      ...current,
                                      models: current.models.filter(
                                        (item) => item.id !== model.id,
                                      ),
                                    }
                                  : current,
                              )
                            }
                            type="button"
                            variant="outline"
                          >
                            删除
                          </Button>
                        ) : null}
                      </div>
                    </div>

                    <div className="mt-4 grid gap-3 lg:grid-cols-2">
                      {[
                        { key: 'name', placeholder: '显示名称' },
                        { key: 'model_id', placeholder: 'Model ID' },
                        { key: 'base_url', placeholder: 'Base URL' },
                        { key: 'api_key', placeholder: 'API Key' },
                      ].map((field) => (
                        <Input
                          className={fieldClass}
                          key={`${model.id}-${field.key}`}
                          onChange={(event) =>
                            setBundle((current) =>
                              current
                                ? {
                                    ...current,
                                    models: current.models.map((item) =>
                                      item.id === model.id
                                        ? {
                                            ...item,
                                            [field.key]: event.target.value,
                                          }
                                        : item,
                                    ),
                                  }
                                : current,
                            )
                          }
                          placeholder={field.placeholder}
                          type={field.key === 'api_key' ? 'password' : 'text'}
                          value={
                            model[field.key as keyof ModelConfig] as string
                          }
                        />
                      ))}
                      <div className="lg:col-span-2">
                        <Input
                          className={fieldClass}
                          onChange={(event) =>
                            setBundle((current) =>
                              current
                                ? {
                                    ...current,
                                    models: current.models.map((item) =>
                                      item.id === model.id
                                        ? {
                                            ...item,
                                            description: event.target.value,
                                          }
                                        : item,
                                    ),
                                  }
                                : current,
                            )
                          }
                          placeholder="说明"
                          value={model.description}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </SurfaceCard>

          <SurfaceCard>
            <div className="flex flex-col gap-5 p-4">
              <div>
                <div className={panelLabelClass}>运行时参数</div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                {[
                  {
                    key: 'MCP_SERVER_URL',
                    label: 'MCP Server URL',
                    placeholder: 'http://127.0.0.1:8000/mcp/',
                  },
                  {
                    key: 'MCP_TOKEN',
                    label: 'MCP Access Token',
                    placeholder: 'YOUR_ACCESS_TOKEN',
                  },
                  {
                    key: 'FEISHU_WEBHOOK_URL',
                    label: '飞书 Webhook URL',
                    placeholder:
                      'https://open.feishu.cn/open-apis/bot/v2/hook/...',
                  },
                ].map((item) => (
                  <div
                    className="rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/45"
                    key={item.key}
                  >
                    <div className={rowTitleClass}>{item.label}</div>
                    <div className={cn('mt-1', mutedTextClass)}>{item.key}</div>
                    <Input
                      className={cn(fieldClass, 'mt-4')}
                      onChange={(event) =>
                        setBundle((current) =>
                          current
                            ? {
                                ...current,
                                settings: {
                                  ...current.settings,
                                  [item.key]: event.target.value,
                                },
                              }
                            : current,
                        )
                      }
                      placeholder={item.placeholder}
                      type={item.key === 'MCP_TOKEN' ? 'password' : 'text'}
                      value={bundle.settings[item.key] ?? ''}
                    />
                  </div>
                ))}
              </div>
            </div>
          </SurfaceCard>
        </>
      )}
    </div>
  )
}

function WorkspacePanels({
  activeTab,
  previewMode,
}: {
  activeTab: WorkspaceTabId
  previewMode: boolean
}) {
  switch (activeTab) {
    case 'situation':
      return <SituationPanel previewMode={previewMode} />
    case 'chat':
      return <ChatPanel previewMode={previewMode} />
    case 'knowledge':
      return <KnowledgePanel previewMode={previewMode} />
    case 'tracing':
      return <TracingPanel previewMode={previewMode} />
    case 'mcp':
      return <McpPanel previewMode={previewMode} />
    case 'cve':
      return <CvePanel previewMode={previewMode} />
    case 'asset':
      return <AssetPanel previewMode={previewMode} />
    case 'url2md':
      return <Url2MdPanel previewMode={previewMode} />
    case 'skills':
      return <SkillsPanel previewMode={previewMode} />
    case 'settings':
      return <SettingsPanel previewMode={previewMode} />
    default:
      return null
  }
}

function ThemeToggle({
  theme,
  onThemeChange,
}: {
  theme: ThemeMode
  onThemeChange: (theme: ThemeMode) => void
}) {
  const isDark = theme === 'dark'

  return (
    <div className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 text-sm font-semibold text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200">
      <Sun className="size-4 text-amber-500" />
      <Switch
        aria-label="切换暗色模式"
        checked={isDark}
        onCheckedChange={(checked) => onThemeChange(checked ? 'dark' : 'light')}
        size="sm"
      />
      <Moon className="size-4 text-sky-500 dark:text-cyan-200" />
    </div>
  )
}

function SecurityWorkspace() {
  const { logout, user } = useAuth()
  const [snapshot, setSnapshot] = useState<DashboardSnapshot>(
    fallbackDashboardSnapshot,
  )
  const [loadingSnapshot, setLoadingSnapshot] = useState(true)
  const [activeTab, setActiveTab] = useState<WorkspaceTabId>('situation')
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_SIDEBAR_WIDTH)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [resizingSidebar, setResizingSidebar] = useState(false)
  const [theme, setTheme] = useState<ThemeMode>(() => getStoredTheme())
  const dashboardRef = useRef<HTMLElement | null>(null)

  const refreshSnapshot = useEffectEvent(async (background = false) => {
    if (!background) {
      setLoadingSnapshot(true)
    }
    const next = await fetchDashboardSnapshot()
    startTransition(() => {
      setSnapshot(next)
      setLoadingSnapshot(false)
    })
  })

  useEffect(() => {
    void refreshSnapshot(false)
    const timer = window.setInterval(() => {
      void refreshSnapshot(true)
    }, 45_000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    applyThemeClass(theme)
    setStoredTheme(theme)
  }, [theme])

  useEffect(() => {
    if (!resizingSidebar) return

    const previousCursor = document.body.style.cursor
    const previousUserSelect = document.body.style.userSelect
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    function handlePointerMove(event: PointerEvent) {
      setSidebarWidth(clampSidebarWidth(event.clientX))
    }

    function stopResizing() {
      setResizingSidebar(false)
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', stopResizing, { once: true })

    return () => {
      document.body.style.cursor = previousCursor
      document.body.style.userSelect = previousUserSelect
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', stopResizing)
    }
  }, [resizingSidebar])

  useGSAP(
    () => {
      gsap.fromTo(
        '[data-dashboard-reveal]',
        { y: 16 },
        {
          y: 0,
          duration: 0.42,
          ease: 'power3.out',
          stagger: 0.045,
        },
      )
    },
    {
      scope: dashboardRef,
    },
  )

  const currentMeta =
    navItems.find((item) => item.id === activeTab) ?? navItems[0]
  const CurrentIcon = currentMeta.icon
  const previewMode = !snapshot.apiOnline
  const healthLabel = snapshot.apiOnline ? 'API 在线' : '本地演示'

  return (
    <main
      className="w-full max-w-full overflow-x-hidden bg-[#edf2f6] text-slate-950 dark:bg-[#050b12] dark:text-slate-50 lg:h-dvh lg:overflow-hidden"
      ref={dashboardRef}
    >
      <div
        className="flex min-h-dvh flex-col lg:grid lg:h-full lg:min-h-0"
        style={{
          gridTemplateColumns: `${
            sidebarCollapsed ? COLLAPSED_SIDEBAR_WIDTH : sidebarWidth
          }px minmax(0, 1fr)`,
        }}
      >
        <div className="relative hidden min-h-0 lg:block">
          <WorkspaceSidebar
            activeTab={activeTab}
            collapsed={sidebarCollapsed}
            onSelect={setActiveTab}
            onToggleCollapsed={() => setSidebarCollapsed((value) => !value)}
          />
          {!sidebarCollapsed ? (
            <button
              aria-label="拖拽调整侧栏宽度"
              className={cn(
                'absolute top-0 right-[-4px] z-10 h-full w-2 cursor-col-resize border-x border-transparent transition-colors hover:border-sky-200 hover:bg-sky-200/30 dark:hover:border-cyan-300/30 dark:hover:bg-cyan-300/10',
                resizingSidebar &&
                  'border-sky-300 bg-sky-200/40 dark:border-cyan-300/40 dark:bg-cyan-300/12',
              )}
              onPointerDown={(event) => {
                event.preventDefault()
                setResizingSidebar(true)
              }}
              type="button"
            />
          ) : null}
        </div>

        <section className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <header
            className="border-b border-slate-200 bg-white/92 px-4 py-3 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-950/92 lg:px-5"
            data-dashboard-reveal
          >
            <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
              <div className="flex min-w-0 items-center gap-3">
                <div className="grid size-11 shrink-0 place-items-center rounded-lg border border-slate-200 bg-slate-950 text-white shadow-sm dark:border-cyan-300/20 dark:bg-cyan-300/10 dark:text-cyan-100">
                  <CurrentIcon className="size-4.5" />
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h1 className="max-w-3xl truncate text-lg font-semibold tracking-[-0.02em] text-slate-950 dark:text-white">
                      {currentMeta.label}
                    </h1>
                    <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-semibold text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                      AI 信息安全中台
                    </span>
                  </div>
                  <p className="mt-0.5 max-w-3xl truncate text-xs text-slate-500 dark:text-slate-400">
                    {currentMeta.description}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <div className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-medium text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200">
                  <span
                    className={cn(
                      'size-2 rounded-full',
                      snapshot.apiOnline ? 'bg-emerald-500' : 'bg-amber-500',
                    )}
                  />
                  {healthLabel}
                </div>
                <ThemeToggle theme={theme} onThemeChange={setTheme} />
                <Button
                  disabled={loadingSnapshot}
                  onClick={() => void refreshSnapshot(false)}
                  size="sm"
                  type="button"
                  variant="outline"
                >
                  <RefreshCw
                    className={cn('size-4', loadingSnapshot && 'animate-spin')}
                  />
                  刷新
                </Button>
                <div className="inline-flex h-9 max-w-[220px] items-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200">
                  <span className="truncate">{user?.email}</span>
                </div>
                <Button
                  onClick={logout}
                  size="sm"
                  type="button"
                  variant="outline"
                >
                  退出
                </Button>
              </div>
            </div>
          </header>

          <div
            className="border-b border-slate-200 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-950 lg:hidden"
            data-dashboard-reveal
          >
            <div className="flex gap-2 overflow-x-auto">
              {navItems.map((item) => {
                const Icon = item.icon
                return (
                  <button
                    className={cn(
                      'inline-flex shrink-0 items-center gap-2 rounded-lg border px-3 py-2 text-sm font-semibold',
                      activeTab === item.id
                        ? 'border-slate-950 bg-slate-950 text-white dark:border-cyan-300/30 dark:bg-cyan-300/12 dark:text-cyan-50'
                        : 'border-slate-200 bg-white text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300',
                    )}
                    key={item.id}
                    onClick={() =>
                      startTransition(() => {
                        setActiveTab(item.id)
                      })
                    }
                    type="button"
                  >
                    <Icon className="size-4" />
                    {item.label}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-hidden bg-[#f7fafc] p-3 dark:bg-[#071014] lg:p-4">
            <section
              className="workspace-canvas flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_18px_60px_rgba(15,23,42,0.12)] dark:border-white/10 dark:bg-[#071014] dark:shadow-[0_18px_60px_rgba(0,0,0,0.36)]"
              data-dashboard-reveal
            >
              <SignalRail previewMode={previewMode} snapshot={snapshot} />
              <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 md:p-5">
                <div className="min-h-0">
                  <WorkspacePanels
                    activeTab={activeTab}
                    previewMode={previewMode}
                  />
                </div>
              </div>
            </section>
          </div>
        </section>
      </div>
    </main>
  )
}

function AuthGate() {
  const { bootstrapping, user } = useAuth()

  if (bootstrapping) {
    return (
      <main className="grid min-h-dvh place-items-center bg-[#071014] text-white">
        <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-6 py-5 shadow-[0_24px_80px_rgba(0,0,0,0.28)]">
          <div className="text-sm font-semibold tracking-[0.22em] text-cyan-100/70 uppercase">
            AGNO AIOS
          </div>
          <div className="mt-2 text-xl font-black tracking-[-0.04em]">
            正在恢复登录状态
          </div>
        </div>
      </main>
    )
  }

  if (!user) {
    return <AuthScreen />
  }

  return <SecurityWorkspace />
}

export function SecurityPlatform() {
  return (
    <AuthProvider>
      <AuthGate />
    </AuthProvider>
  )
}
