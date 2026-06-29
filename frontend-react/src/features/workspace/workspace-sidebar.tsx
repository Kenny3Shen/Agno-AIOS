import { startTransition } from 'react'
import { ChevronsLeft, ChevronsRight, ShieldCheck } from 'lucide-react'

import { cn } from '#/lib/utils.ts'
import type { WorkspaceTabId } from '#/lib/workspace.ts'

import { workspaceGroups, workspaceNavItems } from './navigation.ts'

export function WorkspaceSidebar({
  activeTab,
  collapsed,
  onSelect,
  onToggleCollapsed,
}: {
  activeTab: WorkspaceTabId
  collapsed: boolean
  onSelect: (id: WorkspaceTabId) => void
  onToggleCollapsed: () => void
}) {
  const sections = workspaceGroups.map((group) => ({
    title: group,
    items: workspaceNavItems.filter((item) => item.group === group),
  }))

  return (
    <aside className="flex h-full min-h-0 flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
      <div className="border-b border-slate-200 p-3 dark:border-slate-800">
        <div
          className={cn(
            'flex items-center gap-3',
            collapsed && 'justify-center',
          )}
        >
          <div className="grid size-10 place-items-center rounded-lg border border-sky-200 bg-sky-50 text-sky-700 dark:border-cyan-300/20 dark:bg-cyan-300/10 dark:text-cyan-100">
            <ShieldCheck className="size-4.5" />
          </div>
          <div className={cn('min-w-0', collapsed && 'hidden')}>
            <div className="text-[0.72rem] font-semibold tracking-[0.22em] text-slate-500 uppercase dark:text-cyan-100/58">
              Agno AIOS
            </div>
            <div className="truncate text-sm font-semibold text-slate-950 dark:text-white">
              AI 信息安全中台
            </div>
          </div>
        </div>
        <button
          aria-label={collapsed ? '展开侧栏' : '折叠侧栏'}
          className={cn(
            'mt-3 inline-flex h-8 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-2.5 text-xs font-semibold text-slate-600 transition-colors hover:bg-white dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800',
            collapsed && 'mx-auto flex size-8 px-0',
          )}
          onClick={onToggleCollapsed}
          type="button"
        >
          {collapsed ? (
            <ChevronsRight className="size-4" />
          ) : (
            <>
              <ChevronsLeft className="size-4" />
              收起导航
            </>
          )}
        </button>
      </div>

      <div
        className={cn(
          'min-h-0 flex-1 overflow-y-auto p-2.5',
          collapsed
            ? 'flex flex-col items-center gap-2'
            : 'flex flex-col gap-3',
        )}
      >
        {sections.map((section) => (
          <section className={cn(collapsed && 'w-full')} key={section.title}>
            <div
              className={cn(
                'mb-2 px-2 text-[11px] font-semibold tracking-[0.16em] text-slate-500 uppercase dark:text-slate-500',
                collapsed && 'sr-only',
              )}
            >
              {section.title}
            </div>
            <div
              className={cn('flex flex-col gap-1', collapsed && 'items-center')}
            >
              {section.items.map((item) => {
                const Icon = item.icon
                return (
                  <button
                    aria-label={item.label}
                    title={collapsed ? item.label : undefined}
                    className={cn(
                      'rounded-lg border text-left transition-colors',
                      collapsed
                        ? 'grid size-11 place-items-center px-0 py-0'
                        : 'w-full px-2.5 py-2',
                      item.id === activeTab
                        ? 'border-sky-200 bg-sky-50 text-sky-950 dark:border-cyan-300/25 dark:bg-cyan-300/10 dark:text-cyan-50'
                        : 'border-transparent text-slate-600 hover:border-slate-200 hover:bg-slate-50 hover:text-slate-950 dark:text-slate-400 dark:hover:border-slate-800 dark:hover:bg-slate-900 dark:hover:text-slate-50',
                    )}
                    key={item.id}
                    onClick={() =>
                      startTransition(() => {
                        onSelect(item.id)
                      })
                    }
                    type="button"
                  >
                    <div
                      className={cn(
                        'flex items-start gap-3',
                        collapsed && 'justify-center',
                      )}
                    >
                      <div
                        className={cn(
                          'grid size-7 shrink-0 place-items-center rounded-md border',
                          item.id === activeTab
                            ? 'border-sky-200 bg-white text-sky-700 dark:border-cyan-300/25 dark:bg-slate-950 dark:text-cyan-100'
                            : 'border-slate-200 bg-white text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-500',
                        )}
                      >
                        <Icon className="size-4" />
                      </div>
                      <div
                        className={cn('min-w-0 flex-1', collapsed && 'hidden')}
                      >
                        <div className="flex items-center gap-2">
                          <span className="truncate text-sm font-semibold">
                            {item.label}
                          </span>
                          {item.badge ? (
                            <span className="rounded-md border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                              {item.badge}
                            </span>
                          ) : null}
                        </div>
                        <div className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-500">
                          {item.description}
                        </div>
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          </section>
        ))}
      </div>

      <div
        className={cn(
          'border-t border-slate-200 p-2.5 dark:border-slate-800',
          collapsed && 'hidden',
        )}
      >
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-2.5 dark:border-slate-800 dark:bg-slate-900/80">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">
              平台运行状态
            </span>
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700">
              <span className="size-2 rounded-full bg-emerald-500" />
              Ready
            </span>
          </div>
          <p className="mt-1.5 text-xs leading-5 text-slate-500 dark:text-slate-400">
            Agent 对话、知识检索、Trace 与 MCP 统一编排。
          </p>
        </div>
      </div>
    </aside>
  )
}
