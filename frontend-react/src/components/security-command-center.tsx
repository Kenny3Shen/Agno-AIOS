import { useGSAP } from '@gsap/react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import {
  Activity,
  ArrowRight,
  Bot,
  ChevronLeft,
  ChevronRight,
  LibraryBig,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Workflow,
} from 'lucide-react'
import {
  startTransition,
  useDeferredValue,
  useEffect,
  useEffectEvent,
  useRef,
  useState,
} from 'react'
import type { ReactNode } from 'react'

import { Button } from '#/components/ui/button.tsx'
import { Input } from '#/components/ui/input.tsx'
import {
  fallbackDashboardSnapshot,
  fetchDashboardSnapshot,
  formatCount,
  formatDuration,
  formatSnapshotTime,
} from '#/lib/dashboard.ts'
import type { DashboardSnapshot } from '#/lib/dashboard.ts'
import { cn } from '#/lib/utils.ts'

gsap.registerPlugin(useGSAP, ScrollTrigger)

const marqueeTerms = [
  'Trace Graph',
  'RAG Memory',
  'MCP Mesh',
  'Asset Surface',
  'CVE Triage',
  'Playbook Guard',
  'Model Routing',
  'Live Signals',
]

const carouselStories = [
  {
    name: 'SOC 分析师',
    role: '一线值班研判',
    quote:
      '过去在资产、CVE、运行链路之间来回切，现在一张屏就能看到请求从进入到收敛的全过程。',
    image: 'https://picsum.photos/seed/soc-analyst-portrait/400/400',
  },
  {
    name: '知识工程',
    role: 'RAG 运维',
    quote:
      '知识库命中、Chunk 覆盖率和模型路由被放进同一条链里后，问题定位速度明显稳定了。',
    image: 'https://picsum.photos/seed/rag-owner-portrait/400/400',
  },
  {
    name: '安全平台负责人',
    role: '平台编排',
    quote:
      'MCP 服务、Skills 和模型配置终于不是三个孤岛，变更影响可以在上线前被直观看见。',
    image: 'https://picsum.photos/seed/platform-lead-portrait/400/400',
  },
]

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
        'group security-noise relative overflow-hidden rounded-[2rem] border border-white/10 bg-white/[0.04] shadow-[0_28px_100px_rgba(0,0,0,0.38)] backdrop-blur-xl',
        className,
      )}
    >
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/35 to-transparent" />
      {children}
    </article>
  )
}

function StatusTone({ status }: { status: string }) {
  const isHealthy = status === 'OK'
  const isError = status === 'ERROR'

  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-[11px] font-semibold tracking-[0.18em] uppercase',
        isHealthy && 'border-emerald-400/25 bg-emerald-400/10 text-emerald-200',
        isError && 'border-rose-400/25 bg-rose-400/10 text-rose-200',
        !isHealthy &&
          !isError &&
          'border-sky-300/20 bg-sky-300/10 text-sky-100',
      )}
    >
      <span
        className={cn(
          'size-1.5 rounded-full',
          isHealthy && 'bg-emerald-300',
          isError && 'bg-rose-300',
          !isHealthy && !isError && 'bg-sky-200',
        )}
      />
      {status}
    </span>
  )
}

export function SecurityCommandCenter() {
  const [snapshot, setSnapshot] = useState<DashboardSnapshot>(
    fallbackDashboardSnapshot,
  )
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [storyIndex, setStoryIndex] = useState(0)
  const deferredSearch = useDeferredValue(search)

  const desireSectionRef = useRef<HTMLElement | null>(null)
  const desirePinRef = useRef<HTMLDivElement | null>(null)
  const stackRefs = useRef<Array<HTMLDivElement | null>>([])

  const refreshSnapshot = useEffectEvent(async (background = false) => {
    if (!background) {
      setLoading(true)
    }

    const nextSnapshot = await fetchDashboardSnapshot()

    startTransition(() => {
      setSnapshot(nextSnapshot)
      setLoading(false)
    })
  })

  const rotateStory = useEffectEvent(() => {
    startTransition(() => {
      setStoryIndex((current) => (current + 1) % carouselStories.length)
    })
  })

  useEffect(() => {
    void refreshSnapshot(false)

    const refreshTimer = window.setInterval(() => {
      void refreshSnapshot(true)
    }, 45_000)

    return () => window.clearInterval(refreshTimer)
  }, [])

  useEffect(() => {
    const carouselTimer = window.setInterval(() => {
      rotateStory()
    }, 5_200)

    return () => window.clearInterval(carouselTimer)
  }, [])

  const query = deferredSearch.trim().toLowerCase()
  const filteredTraces = query
    ? snapshot.traces.filter((trace) => {
        const haystack =
          `${trace.name} ${trace.agentId} ${trace.sessionId} ${trace.status}`.toLowerCase()
        return haystack.includes(query)
      })
    : snapshot.traces

  const filteredSkills = query
    ? snapshot.skills.filter((skill) => {
        const haystack = `${skill.name} ${skill.description}`.toLowerCase()
        return haystack.includes(query)
      })
    : snapshot.skills

  const filteredDocuments = query
    ? snapshot.documents.filter((document) => {
        const haystack = `${document.title} ${document.source}`.toLowerCase()
        return haystack.includes(query)
      })
    : snapshot.documents

  const workflowCards = [
    {
      title: '事件入口统一压平',
      eyebrow: 'Trace intake',
      body: 'CVE、资产、URL 解析和 Agent 对话在同一条编排通路里进入，不再先切工具再追证据。',
      image: 'https://picsum.photos/seed/trace-ingress/1280/960',
      statLabel: '最近活动',
      statValue: `${snapshot.liveTraces} 条运行链路`,
    },
    {
      title: '检索上下文直接回贴到动作层',
      eyebrow: 'Knowledge braid',
      body: '命中的知识文档、Chunk 数量和检索参数被并排展示，研判时不需要再猜模型到底看到了什么。',
      image: 'https://picsum.photos/seed/rag-braid/1280/960',
      statLabel: '知识覆盖',
      statValue: `${formatCount(snapshot.knowledgeChunks)} chunks`,
    },
    {
      title: '服务、技能和模型在上线前对齐',
      eyebrow: 'Control surface',
      body: 'MCP 服务开关、Skills 状态和当前模型路由被收束在同一面板里，让变更影响可追、可回滚。',
      image: 'https://picsum.photos/seed/control-surface/1280/960',
      statLabel: '活跃模型',
      statValue: snapshot.activeModelName,
    },
  ]

  useGSAP(
    () => {
      if (!desireSectionRef.current) {
        return
      }

      const mm = gsap.matchMedia()

      mm.add('(min-width: 1024px)', () => {
        if (desirePinRef.current) {
          ScrollTrigger.create({
            trigger: desireSectionRef.current,
            start: 'top top+=88',
            end: 'bottom bottom-=120',
            pin: desirePinRef.current,
            pinSpacing: false,
          })
        }
      })

      stackRefs.current.forEach((card, index) => {
        if (!card) {
          return
        }

        const media = card.querySelector('[data-stack-media]')
        const timeline = gsap.timeline({
          scrollTrigger: {
            trigger: card,
            start: 'top 86%',
            end: 'bottom 18%',
            scrub: true,
          },
        })

        timeline
          .fromTo(
            card,
            { y: 96, scale: 0.94, opacity: 0.58 },
            {
              y: -(index * 18),
              scale: 1 - index * 0.025,
              opacity: 1,
              ease: 'none',
            },
          )
          .fromTo(
            media,
            {
              scale: 0.9,
              opacity: 0.58,
              filter: 'grayscale(0.35) brightness(0.88)',
            },
            {
              scale: 1,
              opacity: 1,
              filter: 'grayscale(0) brightness(1)',
              ease: 'none',
            },
            0,
          )
          .to(
            media,
            {
              opacity: 0.42,
              filter: 'grayscale(0.55) brightness(0.76)',
              ease: 'none',
            },
            0.68,
          )
      })

      return () => {
        mm.revert()
      }
    },
    {
      scope: desireSectionRef,
      dependencies: [workflowCards.length],
      revertOnUpdate: true,
    },
  )

  const activeStory = carouselStories[storyIndex]
  const maxDuration = Math.max(
    ...snapshot.traces.map((item) => item.durationMs),
    1,
  )

  return (
    <main className="overflow-x-hidden w-full max-w-full">
      <section className="px-4 pb-12 pt-4 sm:px-6 lg:px-10 xl:px-14">
        <div className="mx-auto max-w-[92rem]">
          <div className="sticky top-4 z-40">
            <div className="rounded-full border border-white/12 bg-slate-950/65 px-4 py-3 shadow-[0_18px_50px_rgba(0,0,0,0.32)] backdrop-blur-2xl">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="grid size-10 place-items-center rounded-full border border-cyan-300/20 bg-cyan-300/10 text-cyan-100">
                    <ShieldCheck className="size-4.5" />
                  </div>
                  <div>
                    <div className="text-[0.72rem] font-semibold tracking-[0.28em] text-cyan-100/70 uppercase">
                      Agno AIOS
                    </div>
                    <div className="text-sm font-medium text-white">
                      AI 信息安全中台
                    </div>
                  </div>
                </div>

                <nav className="hidden items-center gap-1 rounded-full border border-white/8 bg-white/[0.03] p-1 text-sm text-white/72 md:flex">
                  <a
                    className="rounded-full px-4 py-2 transition-colors hover:bg-white/8 hover:text-white"
                    href="#overview"
                  >
                    总览
                  </a>
                  <a
                    className="rounded-full px-4 py-2 transition-colors hover:bg-white/8 hover:text-white"
                    href="#signals"
                  >
                    信号
                  </a>
                  <a
                    className="rounded-full px-4 py-2 transition-colors hover:bg-white/8 hover:text-white"
                    href="#flows"
                  >
                    编排
                  </a>
                  <a
                    className="rounded-full px-4 py-2 transition-colors hover:bg-white/8 hover:text-white"
                    href="#action"
                  >
                    接管
                  </a>
                </nav>

                <div className="flex items-center gap-3 text-sm text-white/72">
                  <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-2">
                    <span
                      className={cn(
                        'size-2 rounded-full',
                        snapshot.apiOnline ? 'bg-emerald-300' : 'bg-amber-300',
                      )}
                    />
                    {snapshot.backendLabel}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div
            className="grid items-center gap-12 py-20 md:py-28 lg:grid-cols-[minmax(0,1.16fr)_minmax(320px,0.84fr)] xl:gap-20 xl:py-36"
            id="overview"
          >
            <div className="max-w-6xl">
              <p className="mb-6 text-sm font-semibold tracking-[0.32em] text-cyan-100/64 uppercase">
                简洁高效的安全运营视角
              </p>
              <h1 className="max-w-6xl text-[clamp(1.8rem,8.4vw,3.2rem)] font-black leading-[0.94] tracking-[-0.05em] text-white md:text-[clamp(2.85rem,7vw,5.15rem)]">
                <span className="block md:hidden">让 Agent、Trace</span>
                <span className="mt-2 block md:hidden">与知识检索汇成</span>
                <span className="mt-2 block md:hidden">同一中台决策</span>
                <span className="hidden md:inline">让 Agent、Trace 与 </span>
                <span className="hidden md:inline">知识检索在同一中台</span>
                <span className="mt-2 hidden md:block">
                  收束成
                  <span
                    className="mx-3 inline-block h-11 w-24 rounded-full align-middle bg-cover bg-center grayscale contrast-125 md:h-14 md:w-32"
                    style={{
                      backgroundImage:
                        'url(https://picsum.photos/seed/security-grid-inline/320/180)',
                    }}
                  />
                  决策
                </span>
              </h1>
              <p className="mt-8 max-w-3xl text-lg leading-8 text-slate-200/78 md:text-xl">
                针对 AI 信息安全场景重做的工作台，把 CVE 线索、资产暴露、 MCP
                服务、技能开关、知识库命中和运行链路并排放进一张屏。
                你看到的不只是结果，而是每一步为什么发生。
              </p>

              <div className="mt-10 flex flex-wrap items-center gap-4">
                <Button
                  asChild
                  className="h-12 rounded-full bg-cyan-300 px-7 text-sm font-semibold text-slate-950 hover:bg-cyan-200"
                >
                  <a href="#signals">
                    进入信号面板
                    <ArrowRight className="size-4" />
                  </a>
                </Button>

                <Button
                  asChild
                  variant="outline"
                  className="h-12 rounded-full border-white/14 bg-white/6 px-7 text-sm font-semibold text-white hover:bg-white/10"
                >
                  <a href="#flows">查看编排链路</a>
                </Button>
              </div>
            </div>

            <div className="relative lg:pl-10">
              <div className="absolute -left-4 top-12 h-48 w-48 rounded-full bg-cyan-300/18 blur-3xl" />
              <div className="absolute right-0 top-0 h-56 w-56 rounded-full bg-emerald-300/12 blur-3xl" />

              <div className="group relative overflow-hidden rounded-[2.25rem] border border-white/10 bg-slate-950/68 shadow-[0_36px_120px_rgba(0,0,0,0.48)]">
                <img
                  alt="Security command center preview"
                  className="h-[28rem] w-full object-cover grayscale mix-blend-luminosity opacity-90 contrast-125 transition-transform duration-700 ease-out group-hover:scale-105 md:h-[34rem] xl:h-[38rem]"
                  src="https://picsum.photos/seed/ai-security-center/1240/1560"
                />
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_25%_18%,rgba(125,234,255,0.18),transparent_28%),linear-gradient(180deg,rgba(7,16,25,0.14),rgba(7,16,25,0.76))]" />

                <div className="absolute bottom-6 right-6 left-6 rounded-[1.75rem] border border-white/12 bg-white/[0.06] p-5 backdrop-blur-xl">
                  <div className="text-sm font-semibold tracking-[0.22em] text-cyan-100/70 uppercase">
                    unified operator view
                  </div>
                  <p className="mt-3 max-w-md text-base leading-7 text-slate-100/84">
                    同一块玻璃上看见知识召回、模型路由、技能启停和链路质量，
                    让操作面与证据面不再割裂。
                  </p>
                  <div className="mt-5 flex flex-wrap gap-2 text-xs text-slate-200/70">
                    <span className="rounded-full border border-white/10 bg-white/[0.05] px-3 py-1.5">
                      Trace aware
                    </span>
                    <span className="rounded-full border border-white/10 bg-white/[0.05] px-3 py-1.5">
                      Knowledge linked
                    </span>
                    <span className="rounded-full border border-white/10 bg-white/[0.05] px-3 py-1.5">
                      MCP visible
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="overflow-hidden rounded-full border border-white/10 bg-white/[0.04] px-0 py-4 backdrop-blur-xl">
            <div className="marquee-track flex items-center gap-4 text-sm font-semibold tracking-[0.3em] text-slate-200/70 uppercase">
              {[...marqueeTerms, ...marqueeTerms].map((term, index) => (
                <div
                  className="flex items-center gap-4 px-4"
                  key={`${term}-${index}`}
                >
                  <span>{term}</span>
                  <span className="size-1.5 rounded-full bg-cyan-200/60" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section
        className="px-4 py-32 md:px-6 md:py-40 xl:px-14 xl:py-48"
        id="signals"
      >
        <div className="mx-auto max-w-[92rem]">
          <div className="mb-12 flex flex-col gap-8 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-4xl">
              <p className="text-sm font-semibold tracking-[0.32em] text-cyan-100/64 uppercase">
                数据一眼可扫
              </p>
              <h2 className="mt-4 text-balance max-w-5xl text-[clamp(2.5rem,4vw,4.6rem)] font-black leading-[0.98] tracking-[-0.05em] text-white">
                把运营信号收进同一视野，而不是散落在五个标签页里。
              </h2>
              <p className="mt-5 max-w-3xl text-lg leading-8 text-slate-300/76">
                首页先展示你需要判断风险走势的核心面，再展开具体链路与配置。
                如果 API
                暂时不可达，界面仍会保留一份结构化快照，方便继续前端联调。
              </p>
            </div>

            <div className="w-full max-w-xl">
              <div className="rounded-[1.5rem] border border-white/10 bg-white/[0.04] p-3 backdrop-blur-xl">
                <div className="flex items-center gap-3">
                  <RefreshCw
                    className={cn(
                      'size-4 text-cyan-100/72',
                      loading && 'animate-spin',
                    )}
                  />
                  <Input
                    className="h-12 rounded-[1.2rem] border-none bg-transparent px-0 text-white placeholder:text-slate-300/44 focus-visible:ring-0"
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="快速筛选 traces / skills / 文档"
                    value={search}
                  />
                  <span className="rounded-full border border-white/10 bg-white/[0.05] px-3 py-1.5 text-xs text-slate-200/64">
                    {snapshot.backendLabel}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-6 lg:grid-flow-dense">
            <SurfaceCard className="lg:col-span-3 lg:row-span-2">
              <div className="flex h-full flex-col gap-8 p-7 md:p-8">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-semibold tracking-[0.22em] text-cyan-100/64 uppercase">
                      运行稳定性
                    </p>
                    <h3 className="mt-3 text-3xl font-bold tracking-[-0.04em] text-white">
                      {snapshot.successRate}% 成功率
                    </h3>
                  </div>
                  <div className="rounded-full border border-white/10 bg-white/[0.05] p-3 text-cyan-100">
                    <Activity className="size-5" />
                  </div>
                </div>

                <div className="grid gap-4 sm:grid-cols-3">
                  <div className="rounded-[1.5rem] border border-white/10 bg-white/[0.05] p-4">
                    <div className="text-sm text-slate-300/72">实时链路</div>
                    <div className="mt-2 text-2xl font-bold text-white">
                      {formatCount(snapshot.liveTraces)}
                    </div>
                  </div>
                  <div className="rounded-[1.5rem] border border-white/10 bg-white/[0.05] p-4">
                    <div className="text-sm text-slate-300/72">平均耗时</div>
                    <div className="mt-2 text-2xl font-bold text-white">
                      {formatDuration(snapshot.averageDurationMs)}
                    </div>
                  </div>
                  <div className="rounded-[1.5rem] border border-white/10 bg-white/[0.05] p-4">
                    <div className="text-sm text-slate-300/72">接口状态</div>
                    <div className="mt-2 text-2xl font-bold text-white">
                      {snapshot.apiOnline ? 'Online' : 'Fallback'}
                    </div>
                  </div>
                </div>

                <div className="space-y-3">
                  {filteredTraces.slice(0, 4).map((trace) => {
                    const width = `${Math.max(12, (trace.durationMs / maxDuration) * 100)}%`

                    return (
                      <div
                        className="rounded-[1.5rem] border border-white/10 bg-slate-950/40 p-4"
                        key={trace.traceId}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <div className="text-base font-semibold text-white">
                              {trace.name}
                            </div>
                            <div className="mt-1 text-sm text-slate-300/66">
                              {trace.agentId} ·{' '}
                              {formatSnapshotTime(trace.startTime)}
                            </div>
                          </div>
                          <div className="flex items-center gap-3">
                            <StatusTone status={trace.status} />
                            <div className="text-sm font-medium text-slate-100">
                              {formatDuration(trace.durationMs)}
                            </div>
                          </div>
                        </div>
                        <div className="mt-4 h-2 rounded-full bg-white/8">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-cyan-300 via-sky-300 to-emerald-300"
                            style={{ width }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            </SurfaceCard>

            <SurfaceCard className="lg:col-span-3 lg:row-span-1">
              <div className="grid h-full gap-5 p-7 md:grid-cols-[1.1fr_0.9fr]">
                <div>
                  <p className="text-sm font-semibold tracking-[0.22em] text-cyan-100/64 uppercase">
                    模型路由
                  </p>
                  <h3 className="mt-3 text-2xl font-bold tracking-[-0.04em] text-white">
                    {snapshot.activeModelName}
                  </h3>
                  <p className="mt-3 max-w-xl text-sm leading-7 text-slate-300/72">
                    当前默认模型为 {snapshot.activeModelId}，已启用{' '}
                    {snapshot.models.filter((item) => item.enabled).length}/
                    {snapshot.models.length} 个可调度模型。
                  </p>
                </div>
                <div className="rounded-[1.5rem] border border-white/10 bg-white/[0.04] p-4">
                  <div className="space-y-3">
                    {snapshot.models.slice(0, 3).map((model) => (
                      <div
                        className="flex items-center justify-between gap-3 rounded-[1rem] border border-white/8 bg-black/18 px-4 py-3"
                        key={model.id}
                      >
                        <div>
                          <div className="text-sm font-semibold text-white">
                            {model.name}
                          </div>
                          <div className="text-xs text-slate-300/62">
                            {model.modelId}
                          </div>
                        </div>
                        <span
                          className={cn(
                            'rounded-full px-2.5 py-1 text-[11px] font-semibold',
                            model.enabled
                              ? 'bg-emerald-400/12 text-emerald-200'
                              : 'bg-white/8 text-slate-300/68',
                          )}
                        >
                          {model.enabled ? 'enabled' : 'standby'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </SurfaceCard>

            <SurfaceCard className="lg:col-span-3 lg:row-span-1">
              <div className="grid h-full gap-5 p-7 md:grid-cols-[0.95fr_1.05fr]">
                <div>
                  <p className="text-sm font-semibold tracking-[0.22em] text-cyan-100/64 uppercase">
                    知识热区
                  </p>
                  <h3 className="mt-3 text-2xl font-bold tracking-[-0.04em] text-white">
                    {formatCount(snapshot.knowledgeChunks)} chunks
                  </h3>
                  <p className="mt-3 text-sm leading-7 text-slate-300/72">
                    集合 {snapshot.knowledgeCollection} 当前默认 top-k 为{' '}
                    {snapshot.topK}， 文档总数 {snapshot.knowledgeDocuments}。
                  </p>
                </div>
                <div className="space-y-3">
                  {filteredDocuments.slice(0, 3).map((document) => (
                    <div
                      className="rounded-[1.2rem] border border-white/10 bg-black/18 px-4 py-4"
                      key={document.id}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-semibold text-white">
                            {document.title}
                          </div>
                          <div className="mt-1 text-xs text-slate-300/62">
                            {document.source} ·{' '}
                            {formatSnapshotTime(document.createdAt)}
                          </div>
                        </div>
                        <div className="rounded-full border border-white/8 px-2.5 py-1 text-[11px] text-slate-200/72">
                          {document.chunks} chunks
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </SurfaceCard>

            <SurfaceCard className="lg:col-span-2 lg:row-span-1">
              <div className="flex h-full flex-col gap-5 p-7">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold tracking-[0.22em] text-cyan-100/64 uppercase">
                      Skills
                    </p>
                    <h3 className="mt-3 text-2xl font-bold tracking-[-0.04em] text-white">
                      {snapshot.enabledSkills}/{snapshot.skills.length}
                    </h3>
                  </div>
                  <Sparkles className="size-5 text-cyan-100/76" />
                </div>

                <div className="space-y-3">
                  {filteredSkills.slice(0, 3).map((skill) => (
                    <div
                      className="rounded-[1rem] border border-white/10 bg-black/18 px-4 py-3"
                      key={skill.name}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-semibold text-white">
                          {skill.name}
                        </div>
                        <span
                          className={cn(
                            'rounded-full px-2.5 py-1 text-[11px] font-semibold',
                            skill.enabled
                              ? 'bg-emerald-400/12 text-emerald-200'
                              : 'bg-white/8 text-slate-300/68',
                          )}
                        >
                          {skill.enabled ? 'on' : 'off'}
                        </span>
                      </div>
                      <p className="mt-2 text-xs leading-6 text-slate-300/62">
                        {skill.description}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </SurfaceCard>

            <SurfaceCard className="lg:col-span-4 lg:row-span-1">
              <div className="grid h-full gap-5 p-7 md:grid-cols-[1fr_1.05fr]">
                <div>
                  <p className="text-sm font-semibold tracking-[0.22em] text-cyan-100/64 uppercase">
                    MCP 服务矩阵
                  </p>
                  <h3 className="mt-3 text-2xl font-bold tracking-[-0.04em] text-white">
                    {snapshot.enabledServices} 条服务已接入
                  </h3>
                  <p className="mt-3 max-w-xl text-sm leading-7 text-slate-300/72">
                    当前使用 {snapshot.mcpFastmcp} 模式，主入口为{' '}
                    {snapshot.mcpUrl}。
                    服务启停的影响被并列放进同一面板，避免编排面和控制面分离。
                  </p>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  {snapshot.serviceStates.map((service) => (
                    <div
                      className="rounded-[1.25rem] border border-white/10 bg-black/18 p-4"
                      key={service.name}
                    >
                      <div className="flex items-center justify-between">
                        <div className="text-sm font-semibold text-white">
                          {service.name}
                        </div>
                        <span
                          className={cn(
                            'size-2 rounded-full',
                            service.enabled ? 'bg-emerald-300' : 'bg-slate-500',
                          )}
                        />
                      </div>
                      <div className="mt-3 text-xs uppercase tracking-[0.2em] text-slate-300/58">
                        {service.enabled ? 'serving' : 'standby'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </SurfaceCard>
          </div>
        </div>
      </section>

      <section
        className="px-4 py-32 md:px-6 md:py-40 xl:px-14 xl:py-48"
        id="flows"
        ref={desireSectionRef}
      >
        <div className="mx-auto grid max-w-[92rem] gap-12 lg:grid-cols-[minmax(420px,0.92fr)_minmax(0,1.08fr)] xl:gap-16">
          <div className="lg:min-h-[48rem]">
            <div ref={desirePinRef}>
              <p className="text-sm font-semibold tracking-[0.32em] text-cyan-100/64 uppercase">
                编排不再隐身
              </p>
              <h2 className="mt-4 max-w-2xl text-[clamp(2rem,3.5vw,3.7rem)] font-black leading-[0.98] tracking-[-0.05em] text-white">
                <span className="block">把证据、动作与控制</span>
                <span className="mt-2 block">收进同一条</span>
                <span className="mt-2 block">连续叙事</span>
              </h2>
              <p className="mt-5 max-w-lg text-lg leading-8 text-slate-300/74">
                左侧固定的是你的判断上下文，右侧滚动的是每一步动作如何长出来。
                这段区域用真实的滚动联动去表达链路，而不是静态堆卡片。
              </p>
            </div>
          </div>

          <div className="space-y-0">
            {workflowCards.map((card, index) => (
              <SurfaceCard
                className={cn(index > 0 && 'mt-5 lg:mt-[-3.5rem]')}
                key={card.title}
              >
                <div
                  className="grid gap-6 p-6 md:grid-cols-[0.95fr_1.05fr] md:gap-8 md:p-8"
                  ref={(node) => {
                    stackRefs.current[index] = node
                  }}
                  style={{
                    position: 'relative',
                    zIndex: workflowCards.length - index,
                  }}
                >
                  <div className="flex flex-col justify-between">
                    <div>
                      <p className="text-sm font-semibold tracking-[0.22em] text-cyan-100/64 uppercase">
                        {card.eyebrow}
                      </p>
                      <h3 className="mt-4 text-3xl font-bold tracking-[-0.04em] text-white">
                        {card.title}
                      </h3>
                      <p className="mt-4 text-base leading-8 text-slate-300/72">
                        {card.body}
                      </p>
                    </div>
                    <div className="mt-8 rounded-[1.35rem] border border-white/10 bg-black/18 p-4">
                      <div className="text-xs uppercase tracking-[0.2em] text-slate-300/58">
                        {card.statLabel}
                      </div>
                      <div className="mt-2 text-xl font-semibold text-white">
                        {card.statValue}
                      </div>
                    </div>
                  </div>

                  <div className="overflow-hidden rounded-[1.75rem] border border-white/10">
                    <img
                      alt={card.title}
                      className="h-full min-h-72 w-full object-cover grayscale mix-blend-luminosity opacity-90 contrast-125 transition-transform duration-700 ease-out group-hover:scale-105 md:min-h-80"
                      data-stack-media
                      src={card.image}
                    />
                  </div>
                </div>
              </SurfaceCard>
            ))}
          </div>
        </div>
      </section>

      <section className="px-4 pb-24 pt-32 md:px-6 xl:px-14" id="action">
        <div className="mx-auto max-w-[92rem]">
          <SurfaceCard className="overflow-visible">
            <div className="grid gap-10 p-7 md:p-10 xl:grid-cols-[0.95fr_1.05fr] xl:p-12">
              <div className="flex flex-col justify-between">
                <div>
                  <p className="text-sm font-semibold tracking-[0.32em] text-cyan-100/64 uppercase">
                    接管工作流
                  </p>
                  <h2 className="mt-4 max-w-3xl text-[clamp(2.25rem,4vw,4rem)] font-black leading-[0.98] tracking-[-0.05em] text-white">
                    <span className="block">当信号和链路站到一起</span>
                    <span className="mt-2 block">下一步动作也就</span>
                    <span className="mt-2 block">能被更快确认</span>
                  </h2>
                  <p className="mt-5 max-w-2xl text-lg leading-8 text-slate-300/76">
                    这次重写不是把中台做成更漂亮的导航，而是让数据、编排、
                    知识和控制视角自然衔接。接下来可以继续把 CVE、资产搜索、 URL
                    解析和 Trace 详情页一并迁进去。
                  </p>
                </div>

                <div className="mt-10 flex flex-wrap items-center gap-4">
                  <Button
                    asChild
                    className="h-12 rounded-full !bg-white px-7 text-sm font-semibold !text-slate-950 hover:!bg-slate-100"
                  >
                    <a href="/api/health" rel="noreferrer" target="_blank">
                      验证 API 健康
                      <ArrowRight className="size-4" />
                    </a>
                  </Button>
                  <Button
                    asChild
                    className="h-12 rounded-full border-white/14 bg-white/6 px-7 text-sm font-semibold text-white hover:bg-white/10"
                    variant="outline"
                  >
                    <a href="#overview">回到顶部</a>
                  </Button>
                </div>
              </div>

              <div className="rounded-[2rem] border border-white/10 bg-black/18 p-6 md:p-8">
                <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-sm font-semibold tracking-[0.22em] text-cyan-100/64 uppercase">
                      现场反馈
                    </p>
                    <h3 className="mt-3 max-w-[10ch] text-[clamp(2rem,8vw,3rem)] font-bold leading-[0.96] tracking-[-0.04em] text-white sm:max-w-none">
                      {activeStory.name}
                    </h3>
                    <p className="mt-1 text-sm text-slate-300/62">
                      {activeStory.role}
                    </p>
                  </div>

                  <div className="flex gap-2 sm:self-auto">
                    <button
                      className="grid size-10 place-items-center rounded-full border border-white/10 bg-white/[0.04] text-white transition-colors hover:bg-white/10"
                      onClick={() =>
                        setStoryIndex((current) =>
                          current === 0
                            ? carouselStories.length - 1
                            : current - 1,
                        )
                      }
                      type="button"
                    >
                      <ChevronLeft className="size-4" />
                    </button>
                    <button
                      className="grid size-10 place-items-center rounded-full border border-white/10 bg-white/[0.04] text-white transition-colors hover:bg-white/10"
                      onClick={() =>
                        setStoryIndex(
                          (current) => (current + 1) % carouselStories.length,
                        )
                      }
                      type="button"
                    >
                      <ChevronRight className="size-4" />
                    </button>
                  </div>
                </div>

                <div className="mt-8 flex flex-col items-start gap-4 sm:flex-row sm:items-center">
                  <div className="flex -space-x-3">
                    {carouselStories.map((story) => (
                      <img
                        alt={story.name}
                        className={cn(
                          'size-14 rounded-full border border-white/14 object-cover grayscale contrast-125 transition-all duration-500',
                          story.name === activeStory.name
                            ? 'translate-y-0 opacity-100'
                            : 'translate-y-1 opacity-55',
                        )}
                        key={story.name}
                        src={story.image}
                      />
                    ))}
                  </div>
                  <div className="max-w-sm text-sm leading-7 text-slate-300/64">
                    轮播的是不同角色视角，不是营销口号。
                  </div>
                </div>

                <blockquote className="mt-8 text-[clamp(1.4rem,4vw,2rem)] leading-[1.45] font-medium text-white/92">
                  “{activeStory.quote}”
                </blockquote>

                <div className="mt-8 grid gap-3 sm:grid-cols-3">
                  <div className="rounded-[1.25rem] border border-white/10 bg-white/[0.04] p-4">
                    <div className="flex items-center gap-2 text-sm text-slate-300/68">
                      <Bot className="size-4 text-cyan-100/76" />
                      Agent 路由
                    </div>
                    <div className="mt-3 text-lg font-semibold text-white">
                      {snapshot.activeModelName}
                    </div>
                  </div>
                  <div className="rounded-[1.25rem] border border-white/10 bg-white/[0.04] p-4">
                    <div className="flex items-center gap-2 text-sm text-slate-300/68">
                      <LibraryBig className="size-4 text-cyan-100/76" />
                      知识命中
                    </div>
                    <div className="mt-3 text-lg font-semibold text-white">
                      {formatCount(snapshot.knowledgeChunks)} chunks
                    </div>
                  </div>
                  <div className="rounded-[1.25rem] border border-white/10 bg-white/[0.04] p-4">
                    <div className="flex items-center gap-2 text-sm text-slate-300/68">
                      <Workflow className="size-4 text-cyan-100/76" />
                      服务开关
                    </div>
                    <div className="mt-3 text-lg font-semibold text-white">
                      {snapshot.enabledServices}/{snapshot.serviceStates.length}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </SurfaceCard>
        </div>
      </section>
    </main>
  )
}
