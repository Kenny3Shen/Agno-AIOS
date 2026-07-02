<template>
  <AuthScreen
    v-if="!authBooting && !currentUser"
    :is-dark="isDark"
    @authenticated="handleAuthenticated"
    @toggle-theme="toggleTheme"
  />

  <div
    v-else-if="authBooting"
    class="grid h-dvh place-items-center bg-[#EEF3F7] text-[#111827] dark:bg-[#071014] dark:text-[#E6EDF3]"
  >
    <div class="rounded-2 border border-[#C2D0DC] bg-white px-5 py-4 text-sm shadow-sm dark:border-[#20313D] dark:bg-[#0E171F]">
      <el-icon class="is-loading mr-2"><Loading /></el-icon>
      正在校验安全会话
    </div>
  </div>

  <div v-else class="ag-os security-page h-dvh overflow-hidden">
    <transition name="fade">
      <button
        v-if="isMobile && sidebarOpen"
        type="button"
        class="ag-mobile-scrim fixed inset-0 z-40 lg:hidden"
        aria-label="关闭导航遮罩"
        @click="closeSidebar"
      />
    </transition>

    <div class="ag-shell h-full min-h-0 lg:grid" :style="shellGridStyle">
      <div class="contents lg:relative lg:block lg:h-full lg:min-h-0">
        <aside
          :style="sidebarStyle"
          :class="[
            'ag-sidebar fixed inset-y-0 left-0 z-50 flex h-dvh min-h-0 max-w-[calc(100vw-32px)] flex-col overflow-hidden transition-transform duration-200 lg:relative lg:z-auto lg:h-full lg:max-w-none lg:translate-x-0',
            sidebarOpen ? 'translate-x-0' : '-translate-x-full',
            { 'is-compact': isSidebarCompact && !isMobile },
          ]"
        >
          <div class="ag-brand">
            <div class="ag-brand-main">
              <span class="ag-brand-mark">
                <span>A</span>
              </span>
              <div class="ag-brand-text min-w-0">
                <h1>Agno</h1>
                <p>AIOS</p>
              </div>
              <span class="ag-pro-chip" :title="currentModelName">{{ currentModelLabel }}</span>
            </div>

            <button
              v-if="!isMobile"
              type="button"
              class="ag-sidebar-toggle"
              :aria-label="isSidebarCompact ? '展开导航栏' : '收起导航栏'"
              @click="toggleSidebarSize"
            >
              <el-icon>
                <Expand v-if="isSidebarCompact" />
                <Fold v-else />
              </el-icon>
            </button>

            <el-button v-if="isMobile" text aria-label="关闭侧边栏" @click="closeSidebar">
              <el-icon><Close /></el-icon>
            </el-button>
          </div>

          <nav class="ag-nav min-h-0 flex-1 overflow-y-auto">
            <button
              type="button"
              class="ag-nav-item ag-nav-home"
              :class="{ active: activeTab === 'home' }"
              :aria-current="activeTab === 'home' ? 'page' : undefined"
              @click="selectNav('home')"
            >
              <span class="ag-nav-icon">
                <el-icon><Platform /></el-icon>
              </span>
              <span class="ag-nav-text min-w-0 flex-1">
                <span class="ag-nav-label">{{ homeItem.label }}</span>
              </span>
            </button>

            <button
              type="button"
              class="ag-nav-item ag-nav-dashboard soc-focus"
              :class="{ active: activeTab === 'dashboard' }"
              :aria-current="activeTab === 'dashboard' ? 'page' : undefined"
              @click="selectNav('dashboard')"
            >
              <span class="ag-nav-icon">
                <el-icon><DataBoard /></el-icon>
              </span>
              <span class="ag-nav-text min-w-0 flex-1">
                <span class="ag-nav-label">{{ dashboardItem.label }}</span>
              </span>
              <span v-if="dashboardItem.badge" class="ag-nav-badge">
                {{ dashboardItem.badge }}
              </span>
            </button>

            <div class="ag-nav-divider" aria-hidden="true" />

            <div class="ag-nav-list">
              <template v-for="item in primaryNavItems" :key="item.id">
                <div v-if="item.id === 'chat'" class="ag-nav-chat-block">
                  <div class="ag-nav-chat-row">
                    <button
                      type="button"
                      class="ag-nav-item ag-nav-item-main soc-focus"
                      :class="{ active: item.id === activeTab }"
                      :aria-current="item.id === activeTab ? 'page' : undefined"
                      @click="selectNav(item.id)"
                    >
                      <span class="ag-nav-icon">
                        <el-icon>
                          <component :is="item.icon" />
                        </el-icon>
                      </span>

                      <span class="ag-nav-text min-w-0 flex-1">
                        <span class="ag-nav-label">{{ item.label }}</span>
                      </span>
                    </button>

                    <button
                      type="button"
                      class="ag-chat-session-toggle"
                      :aria-label="chatSessionsExpanded ? '收起 Chat 会话' : '展开 Chat 会话'"
                      :aria-expanded="chatSessionsExpanded"
                      @click.stop="toggleChatSessions"
                    >
                      <el-icon>
                        <ArrowDown v-if="chatSessionsExpanded" />
                        <ArrowRight v-else />
                      </el-icon>
                    </button>
                  </div>

                  <transition name="fade">
                    <div
                      v-if="chatSessionsExpanded && !isSidebarCompact"
                      class="ag-chat-session-panel"
                    >
                      <button type="button" class="ag-chat-new-session" @click="createSidebarChat">
                        <el-icon><Plus /></el-icon>
                        <span>New chat</span>
                      </button>

                      <div class="ag-chat-session-head">
                        <span>Sessions</span>
                        <strong>{{ chatSessions.length }}</strong>
                      </div>

                      <div
                        v-for="session in chatSessions"
                        :key="session.session_id"
                        class="ag-chat-session-row"
                        :class="{ active: currentChatSessionId === session.session_id }"
                      >
                        <button
                          type="button"
                          class="ag-chat-session-item"
                          :title="session.preview || session.session_id"
                          @click="selectChatSession(session.session_id)"
                        >
                          <span class="ag-chat-session-icon">
                            <el-icon><ChatDotRound /></el-icon>
                          </span>
                          <span class="ag-chat-session-copy">
                            <strong>{{ session.preview || 'New chat' }}</strong>
                            <em>{{ formatSessionTime(session.updated_at) }}</em>
                          </span>
                        </button>

                        <el-tooltip content="归档会话" placement="right">
                          <button
                            type="button"
                            class="ag-chat-session-archive"
                            :aria-label="`归档会话 ${session.preview || session.session_id}`"
                            @click.stop="archiveSidebarChatSession(session.session_id)"
                          >
                            <el-icon><Delete /></el-icon>
                          </button>
                        </el-tooltip>
                      </div>

                      <div v-if="!chatSessions.length && !loadingSessions" class="ag-chat-session-empty">
                        No sessions
                      </div>
                    </div>
                  </transition>
                </div>

                <div v-else-if="item.id === 'trace'" class="ag-nav-trace-block">
                  <div class="ag-nav-chat-row">
                    <button
                      type="button"
                      class="ag-nav-item ag-nav-item-main soc-focus"
                      :class="{ active: item.id === activeTab }"
                      :aria-current="item.id === activeTab ? 'page' : undefined"
                      @click="selectNav(item.id)"
                    >
                      <span class="ag-nav-icon">
                        <el-icon>
                          <component :is="item.icon" />
                        </el-icon>
                      </span>

                      <span class="ag-nav-text min-w-0 flex-1">
                        <span class="ag-nav-label">{{ item.label }}</span>
                      </span>
                    </button>

                    <button
                      type="button"
                      class="ag-chat-session-toggle"
                      :aria-label="traceQueueExpanded ? '收起 Trace 队列' : '展开 Trace 队列'"
                      :aria-expanded="traceQueueExpanded"
                      @click.stop="toggleTraceQueue"
                    >
                      <el-icon>
                        <ArrowDown v-if="traceQueueExpanded" />
                        <ArrowRight v-else />
                      </el-icon>
                    </button>
                  </div>

                  <transition name="fade">
                    <div
                      v-if="traceQueueExpanded && !isSidebarCompact"
                      class="ag-trace-queue-panel"
                    >
                      <button type="button" class="ag-chat-new-session" :disabled="loadingTraceQueue" @click="loadSidebarTraceQueue">
                        <el-icon><Refresh /></el-icon>
                        <span>Refresh traces</span>
                      </button>

                      <div class="ag-chat-session-head">
                        <span>Trace Queue</span>
                        <strong>{{ traceQueueItems.length }}</strong>
                      </div>

                      <button
                        v-for="trace in traceQueueItems"
                        :key="trace.trace_id"
                        type="button"
                        class="ag-trace-queue-item"
                        :class="{ active: currentTraceId === trace.trace_id, error: isTraceError(trace) }"
                        :title="trace.name || trace.trace_id"
                        @click="selectTraceFromSidebar(trace)"
                      >
                        <span class="ag-trace-status" :class="traceStatusTone(trace)" />
                        <span class="ag-chat-session-copy">
                          <strong>{{ trace.name || trace.trace_id }}</strong>
                          <em>{{ formatTraceMeta(trace) }}</em>
                        </span>
                      </button>

                      <div v-if="!traceQueueItems.length && !loadingTraceQueue" class="ag-chat-session-empty">
                        No traces
                      </div>
                    </div>
                  </transition>
                </div>

                <button
                  v-else
                  type="button"
                  class="ag-nav-item soc-focus"
                  :class="{ active: item.id === activeTab }"
                  :aria-current="item.id === activeTab ? 'page' : undefined"
                  @click="selectNav(item.id)"
                >
                  <span class="ag-nav-icon">
                    <el-icon>
                      <component :is="item.icon" />
                    </el-icon>
                  </span>

                  <span class="ag-nav-text min-w-0 flex-1">
                    <span class="ag-nav-label">{{ item.label }}</span>
                  </span>

                  <span v-if="item.badge" class="ag-nav-badge">
                    {{ item.badge }}
                  </span>
                </button>
              </template>
            </div>

            <div class="ag-nav-divider" aria-hidden="true" />

            <button
              type="button"
              class="ag-nav-item soc-focus"
              :class="{ active: settingsItem.id === activeTab }"
              :aria-current="settingsItem.id === activeTab ? 'page' : undefined"
              @click="selectNav(settingsItem.id)"
            >
              <span class="ag-nav-icon">
                <el-icon>
                  <component :is="settingsItem.icon" />
                </el-icon>
              </span>

              <span class="ag-nav-text min-w-0 flex-1">
                <span class="ag-nav-label">{{ settingsItem.label }}</span>
              </span>
            </button>
          </nav>

          <div class="ag-sidebar-footer">
            <div class="flex items-center justify-between gap-2">
              <span class="ag-footer-label">当前会话</span>
              <span class="ag-live-dot">
                <span />
                已认证
              </span>
            </div>

            <div class="ag-user-menu-wrap">
              <div class="ag-user-row" :title="currentUserEmail">
                <span>{{ userInitials }}</span>
                <strong class="ag-footer-meta">{{ currentUserEmail }}</strong>
              </div>

              <button
                type="button"
                class="ag-user-menu-trigger"
                aria-label="打开用户菜单"
                :aria-expanded="userMenuOpen"
                @click="toggleUserMenu"
              >
                <el-icon><MoreFilled /></el-icon>
              </button>

              <transition name="fade">
                <div v-if="userMenuOpen" class="ag-user-menu" role="menu">
                  <button type="button" role="menuitem" @click="openUserSettings">
                    <el-icon><Setting /></el-icon>
                    <span>用户设置</span>
                  </button>
                  <button type="button" role="menuitem" :disabled="loggingOut" @click="handleLogout">
                    <el-icon><SwitchButton /></el-icon>
                    <span>{{ loggingOut ? '退出中' : '退出登录' }}</span>
                  </button>
                </div>
              </transition>
            </div>
          </div>
        </aside>
      </div>

      <main class="ag-main">
        <section class="ag-workbench">
          <header class="ag-topbar">
            <div class="ag-topbar-title">
              <el-button v-if="isMobile" text class="!rounded-2" aria-label="打开侧边栏" @click="openSidebar">
                <el-icon size="20"><Menu /></el-icon>
              </el-button>

              <span class="ag-current-icon">
                <el-icon><component :is="currentMeta.icon" /></el-icon>
              </span>

              <div class="min-w-0">
                <div class="ag-os-name">
                  <span>{{ currentMeta.label }}</span>
                  <i />
                </div>
                <p>{{ currentMeta.description }}</p>
              </div>
            </div>

            <div class="ag-topbar-actions">
              <button type="button" class="ag-topbar-button" @click="refreshWorkspace">
                <el-icon><Refresh /></el-icon>
                <span>刷新</span>
              </button>

              <el-tooltip :content="isDark ? '切换浅色模式' : '切换深色模式'" placement="bottom">
                <el-button
                  circle
                  class="ag-icon-button"
                  :aria-label="isDark ? '切换到浅色模式' : '切换到深色模式'"
                  @click="toggleTheme"
                >
                  <el-icon>
                    <Moon v-if="!isDark" />
                    <Sunny v-else />
                  </el-icon>
                </el-button>
              </el-tooltip>

            </div>
          </header>

          <section class="ag-stage">
            <transition name="fade" mode="out-in">
              <div v-if="activeTab === 'home'" key="home" class="ag-home">
                <section class="ag-command">
                  <div class="min-w-0">
                    <span class="ag-command-kicker">AIOS CONTROL PLANE</span>
                    <h2>Agno AIOS 工作台</h2>
                    <p>把安全数据、知识、Agent 和运行观测收束到一个可调度的控制面。</p>
                  </div>

                  <div class="ag-signal-grid">
                    <div v-for="signal in workspaceSignals" :key="signal.label" class="ag-signal">
                      <span>{{ signal.label }}</span>
                      <strong>{{ signal.value }}</strong>
                    </div>
                  </div>
                </section>

                <section v-for="section in homeSections" :key="section.title" class="ag-home-section">
                  <div class="ag-section-heading">
                    <span class="ag-section-caret">⌃</span>
                    <h3>{{ section.title }}</h3>
                  </div>

                  <div class="ag-module-grid">
                    <article
                      v-for="item in section.items"
                      :key="item.id"
                      class="ag-module-card"
                      :class="[`tone-${item.tone}`, { active: item.id === activeTab }]"
                    >
                      <button type="button" class="ag-module-main" @click="selectNav(item.id)">
                        <span class="ag-module-icon">
                          <el-icon><component :is="item.icon" /></el-icon>
                        </span>
                        <span class="min-w-0">
                          <strong>{{ item.label }}</strong>
                          <em>{{ item.description }}</em>
                        </span>
                      </button>

                      <div class="ag-module-actions">
                        <span v-if="item.badge" class="ag-module-badge">{{ item.badge }}</span>
                        <button type="button" @click="selectNav(item.id)">打开</button>
                      </div>
                    </article>
                  </div>
                </section>

                <section class="ag-home-section">
                  <div class="ag-section-heading">
                    <span class="ag-section-caret">⌃</span>
                    <h3>运行平面</h3>
                  </div>

                  <div class="ag-plane-grid">
                    <article v-for="plane in osPlanes" :key="plane.name" class="ag-plane-card">
                      <div class="flex min-w-0 items-center gap-3">
                        <span class="ag-plane-icon">
                          <el-icon><component :is="plane.icon" /></el-icon>
                        </span>
                        <div class="min-w-0">
                          <strong>{{ plane.name }}</strong>
                          <p>{{ plane.description }}</p>
                        </div>
                      </div>
                      <span class="ag-plane-status" :class="plane.status">{{ plane.statusText }}</span>
                      <div class="ag-plane-footer">
                        <span v-for="metric in plane.metrics" :key="metric">{{ metric }}</span>
                      </div>
                    </article>
                  </div>
                </section>
              </div>

              <div v-else key="module" class="ag-module-host">
                <keep-alive>
                  <component
                    :is="activeComponent"
                    v-if="activeComponent"
                    :key="activeComponentKey"
                    :class="contentClass"
                    v-bind="activeComponentProps"
                  />
                </keep-alive>
              </div>
            </transition>
          </section>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, type Component } from "vue"
import { storeToRefs } from "pinia"
import {
  ArrowDown,
  ArrowRight,
  Calendar,
  ChatDotRound,
  Clock,
  Close,
  Connection,
  Cpu,
  DataAnalysis,
  DataBoard,
  Delete,
  Expand,
  Files,
  Fold,
  Finished,
  Loading,
  MagicStick,
  Menu,
  Monitor,
  MoreFilled,
  Moon,
  Platform,
  Plus,
  Refresh,
  Search,
  Setting,
  SetUp,
  Sunny,
  SwitchButton,
  Tickets,
  WarningFilled,
} from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"
import AgentOSControl from "./components/AgentOSControl.vue"
import AuthScreen from "./components/AuthScreen.vue"
import CVE from "./components/CVE.vue"
import Assets from "./components/Assets.vue"
import Chat from "./components/Chat.vue"
import Collect from "./components/Collect.vue"
import Settings from "./components/Settings.vue"
import Dashboard from "./components/Dashboard.vue"
import Trace from "./components/Trace.vue"
import Skills from "./components/Skills.vue"
import MCP from "./components/MCP.vue"
import Knowledge from "./components/Knowledge.vue"
import { useChatHistory, useSettingsApi, useTracingApi } from "./composables/useApi"
import { clearStoredAuthToken, fetchCurrentUser, getStoredAuthToken, logout as authLogout } from "./lib/authClient"
import { useAuthStore } from "./stores/auth"
import { useSessionStore } from "./stores/sessions"
import { useShellStore } from "./stores/shell"
import { useTraceStore } from "./stores/traces"
import type { AuthUser, OsControlModule, TraceItem } from "./types"

type ModuleNavId =
  | "dashboard"
  | "cve"
  | "assets"
  | "knowledge"
  | "collect"
  | "chat"
  | "trace"
  | "mcp"
  | "skills"
  | "sessions"
  | "studio"
  | "memory"
  | "metrics"
  | "evaluation"
  | "approvals"
  | "scheduler"
  | "settings"
type NavId = "home" | ModuleNavId
type NavTone = "red" | "blue" | "green" | "yellow"

type NavItem = {
  id: NavId
  label: string
  description: string
  badge?: string
  icon: Component
  tone: NavTone
}

type HomeSection = {
  title: string
  items: NavItem[]
}

const homeItem: NavItem = {
  id: "home",
  label: "Home",
  description: "工作台总览",
  icon: Platform,
  tone: "blue",
}

const dashboardItem: NavItem = {
  id: "dashboard",
  label: "Dashboard",
  description: "资产、漏洞、响应闭环总览",
  icon: DataBoard,
  badge: "Live",
  tone: "green",
}

const navItems: NavItem[] = [
  { id: "chat", label: "Chat", description: "任务规划、剧本调用与流式分析", icon: ChatDotRound, tone: "blue" },
  { id: "skills", label: "Skills", description: "安全 Skills 模块开关", icon: SetUp, tone: "red" },
  { id: "mcp", label: "MCP", description: "服务、Token 与外部 Agent", icon: Connection, tone: "yellow" },
  { id: "knowledge", label: "Knowledge", description: "RAG 写入、检索与参数治理", icon: Files, tone: "green" },
  { id: "trace", label: "Trace", description: "Trace、Span 与异常追踪", icon: DataAnalysis, tone: "green" },
  { id: "sessions", label: "Sessions", description: "会话库存与上下文历史", icon: Clock, tone: "blue" },
  { id: "studio", label: "Studio", description: "Agent、Team 与组件注册", icon: MagicStick, tone: "yellow" },
  { id: "memory", label: "Memory", description: "用户记忆与增长监测", icon: Cpu, tone: "green" },
  { id: "metrics", label: "Metrics", description: "运行、延迟与错误指标", icon: DataAnalysis, tone: "blue" },
  { id: "evaluation", label: "Evaluation", description: "评测运行与质量基线", icon: Finished, tone: "green" },
  { id: "approvals", label: "Approvals", description: "敏感操作审批队列", icon: Tickets, tone: "red" },
  { id: "scheduler", label: "Scheduler", description: "周期任务与运行窗口", icon: Calendar, tone: "yellow" },
  { id: "cve", label: "CVE", description: "CVE、PoC 与攻击面线索", icon: Search, tone: "red" },
  { id: "assets", label: "Assets", description: "指纹、IP 与暴露面查询", icon: Monitor, tone: "blue" },
  { id: "collect", label: "Collect", description: "网页情报转 Markdown 入库", icon: WarningFilled, tone: "yellow" },
  { id: "settings", label: "Settings", description: "模型路由、MCP 与通知配置", icon: Setting, tone: "blue" },
]

const componentMap: Record<ModuleNavId, Component> = {
  dashboard: Dashboard,
  chat: Chat,
  knowledge: Knowledge,
  trace: Trace,
  mcp: MCP,
  cve: CVE,
  assets: Assets,
  collect: Collect,
  skills: Skills,
  sessions: AgentOSControl,
  studio: AgentOSControl,
  memory: AgentOSControl,
  metrics: AgentOSControl,
  evaluation: AgentOSControl,
  approvals: AgentOSControl,
  scheduler: AgentOSControl,
  settings: Settings,
}

const osControlTabs = new Set<OsControlModule>([
  "sessions",
  "studio",
  "memory",
  "metrics",
  "evaluation",
  "approvals",
  "scheduler",
])
const fullCanvasTabs = new Set<ModuleNavId>([
  "dashboard",
  "chat",
  "trace",
  "mcp",
  ...osControlTabs,
])
const settingsItem = navItems.find((item) => item.id === "settings") as NavItem
const primaryNavItems = navItems.filter((item) => item.id !== "settings")
const moduleNavItems = [dashboardItem, ...navItems]
const navItemById = Object.fromEntries(moduleNavItems.map((item) => [item.id, item])) as Record<ModuleNavId, NavItem>
const homeSections: HomeSection[] = [
  { title: "Operations", items: [navItemById.dashboard, navItemById.chat, navItemById.trace] },
  { title: "Control plane", items: [navItemById.sessions, navItemById.studio, navItemById.memory, navItemById.metrics] },
  { title: "Governance", items: [navItemById.evaluation, navItemById.approvals, navItemById.scheduler] },
  { title: "Security data", items: [navItemById.skills, navItemById.mcp, navItemById.knowledge, navItemById.cve, navItemById.assets, navItemById.collect] },
]
const THEME_STORAGE_KEY = "theme"
const CHAT_MODEL_STORAGE_KEY = "agno-aios-chat-model-id"
const SIDEBAR_EXPANDED_WIDTH = 264
const SIDEBAR_COMPACT_WIDTH = 76
const isMobileViewport = () => typeof window !== "undefined" && window.innerWidth < 1024

const authStore = useAuthStore()
const shellStore = useShellStore()
const sessionStore = useSessionStore()
const traceStore = useTraceStore()

const {
  currentUser,
  authBooting,
  loggingOut,
  userMenuOpen,
} = storeToRefs(authStore)
const {
  activeTab,
  isSidebarCompact,
  isMobile,
  sidebarOpen,
  isDark,
  componentRenderKey,
  chatSessionsExpanded,
  traceQueueExpanded,
} = storeToRefs(shellStore)
const {
  chatSessions,
  currentChatSessionId,
  loadingSessions,
} = storeToRefs(sessionStore)
const {
  traceQueueItems,
  currentTraceId,
  loadingTraceQueue,
} = storeToRefs(traceStore)

shellStore.setIsMobile(isMobileViewport())
const currentModelName = ref("DeepSeek V4 Pro")

const { fetchModels } = useSettingsApi()
const { listSessions, archiveSession } = useChatHistory()
const { listTraces: listSidebarTraces } = useTracingApi()

const activeComponent = computed<Component | null>(() => {
  const tab = activeTab.value as NavId
  if (tab === "home") return null
  return componentMap[tab]
})
const currentMeta = computed<NavItem>(() => {
  if (activeTab.value === "home") return homeItem
  return moduleNavItems.find((item) => item.id === activeTab.value) ?? homeItem
})
const currentUserEmail = computed(() => currentUser.value?.email || "未登录")
const userInitials = computed(() => {
  const email = currentUserEmail.value
  if (!email || email === "未登录") return "AI"
  return email.slice(0, 2).toUpperCase()
})
const activeComponentKey = computed(() => `${activeTab.value}-${componentRenderKey.value}`)
const currentModelLabel = computed(() => formatModelLabel(currentModelName.value))
const currentUserId = computed(() => currentUser.value?.id || currentUser.value?.email || null)
const activeComponentProps = computed(() => {
  const tab = activeTab.value as NavId
  const baseProps = { currentUserId: currentUserId.value }
  if (tab === "trace") {
    return { ...baseProps, selectedTraceId: currentTraceId.value }
  }
  if (tab !== "home" && osControlTabs.has(tab as OsControlModule)) {
    return { ...baseProps, osModule: tab }
  }
  return baseProps
})
const contentClass = computed(() => {
  const base = "block h-full min-h-0"
  const tab = activeTab.value as NavId
  if (tab === "home") return base
  return fullCanvasTabs.has(tab) ? base : `${base} overflow-auto p-4 sm:p-5`
})

const sidebarPixelWidth = computed(() => {
  if (isMobile.value) return SIDEBAR_EXPANDED_WIDTH
  return isSidebarCompact.value ? SIDEBAR_COMPACT_WIDTH : SIDEBAR_EXPANDED_WIDTH
})

const shellGridStyle = computed(() => ({
  gridTemplateColumns: `${sidebarPixelWidth.value}px minmax(0, 1fr)`,
}))

const sidebarStyle = computed(() => ({
  width: isMobile.value ? `min(${SIDEBAR_EXPANDED_WIDTH}px, calc(100vw - 32px))` : `${sidebarPixelWidth.value}px`,
}))

const workspaceSignals = computed(() => [
  { label: "Modules", value: moduleNavItems.length },
  { label: "Data plane", value: "RAG + ASM" },
  { label: "Runtime", value: "Trace" },
  { label: "Session", value: currentUser.value?.is_active ? "Active" : "Ready" },
])
const osPlanes = [
  {
    name: "Agno AIOS",
    description: "运营控制面",
    icon: Platform,
    status: "online",
    statusText: "Current",
    metrics: ["17 modules", "JWT", "Vue"],
  },
  {
    name: "Security Data Fabric",
    description: "资产、漏洞、知识入库",
    icon: Files,
    status: "online",
    statusText: "Online",
    metrics: ["ASM", "CVE", "RAG"],
  },
  {
    name: "Agent Runtime",
    description: "对话、MCP、Trace 观测",
    icon: Connection,
    status: "standby",
    statusText: "Standby",
    metrics: ["Agent", "MCP", "Trace"],
  },
]

const checkMobile = () => {
  isMobile.value = isMobileViewport()
  if (!isMobile.value) sidebarOpen.value = false
}

const formatModelLabel = (name: string) => {
  const compact = name
    .replace(/deepseek/gi, "DS")
    .replace(/\bv(\d)/gi, "v$1")
    .replace(/\s+/g, " ")
    .trim()
  return compact || "Model"
}

const loadCurrentModel = async () => {
  try {
    const config = await fetchModels()
    const savedId = localStorage.getItem(CHAT_MODEL_STORAGE_KEY)
    const selected = config.models.find((model) => model.id === savedId)
      ?? config.models.find((model) => model.id === config.active_model_id)
      ?? config.models.find((model) => model.enabled)
      ?? config.models[0]
    if (selected?.name) currentModelName.value = selected.name
  } catch {
    currentModelName.value = "DeepSeek V4 Pro"
  }
}

const handleModelChange = (event: Event) => {
  const detail = (event as CustomEvent<{ name?: string }>).detail
  if (detail?.name) currentModelName.value = detail.name
}

const formatSessionTime = (timestamp: number) => {
  if (!timestamp) return ""
  return new Date(timestamp * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

const formatTraceTime = (iso?: string | null) => {
  if (!iso) return ""
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ""
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

const compactTraceId = (value?: string | null) => {
  const text = (value || "").trim()
  if (!text) return "-"
  return text.length > 14 ? `${text.slice(0, 6)}...${text.slice(-4)}` : text
}

const isTraceError = (trace: TraceItem) => {
  return trace.status === "ERROR" || Number(trace.error_count || 0) > 0
}

const traceStatusTone = (trace: TraceItem) => {
  if (isTraceError(trace)) return "error"
  if (trace.status === "OK") return "ok"
  return "other"
}

const formatTraceMeta = (trace: TraceItem) => {
  return `${formatTraceTime(trace.start_time)} · ${compactTraceId(trace.trace_id)} · ${trace.total_spans ?? 0} spans`
}

const loadSidebarChatSessions = async () => {
  sessionStore.setLoadingSessions(true)
  sessionStore.setSessionError(null)
  try {
    chatSessions.value = await listSessions()
  } catch (error) {
    chatSessions.value = []
    sessionStore.setSessionError(error instanceof Error ? error.message : "会话加载失败")
  } finally {
    sessionStore.setLoadingSessions(false)
  }
}

const loadSidebarTraceQueue = async () => {
  traceStore.setLoadingTraceQueue(true)
  traceStore.setTraceError(null)
  try {
    const response = await listSidebarTraces({ page: 1, limit: 12 })
    traceQueueItems.value = response.items || []
  } catch (error) {
    traceQueueItems.value = []
    traceStore.setTraceError(error instanceof Error ? error.message : "Trace 队列加载失败")
  } finally {
    traceStore.setLoadingTraceQueue(false)
  }
}

const dispatchChatEvent = (name: string, detail?: Record<string, unknown>) => {
  void nextTick(() => {
    window.dispatchEvent(new CustomEvent(name, { detail }))
  })
}

const toggleChatSessions = () => {
  chatSessionsExpanded.value = !chatSessionsExpanded.value
  if (chatSessionsExpanded.value) void loadSidebarChatSessions()
}

const toggleTraceQueue = () => {
  traceQueueExpanded.value = !traceQueueExpanded.value
  if (traceQueueExpanded.value) void loadSidebarTraceQueue()
}

const selectChatSession = (sessionId: string) => {
  currentChatSessionId.value = sessionId
  activeTab.value = "chat"
  userMenuOpen.value = false
  dispatchChatEvent("agno-aios-chat-session-select", { sessionId })
  closeSidebar()
}

const createSidebarChat = () => {
  currentChatSessionId.value = null
  activeTab.value = "chat"
  userMenuOpen.value = false
  dispatchChatEvent("agno-aios-chat-new")
  closeSidebar()
}

const selectTraceFromSidebar = (trace: TraceItem) => {
  currentTraceId.value = trace.trace_id
  activeTab.value = "trace"
  userMenuOpen.value = false
  dispatchChatEvent("agno-aios-trace-select", { traceId: trace.trace_id })
  closeSidebar()
}

const archiveSidebarChatSession = async (sessionId: string) => {
  const previousSessions = chatSessions.value
  chatSessions.value = chatSessions.value.filter((session) => session.session_id !== sessionId)
  if (currentChatSessionId.value === sessionId) {
    currentChatSessionId.value = null
    dispatchChatEvent("agno-aios-chat-new")
  }
  try {
    await archiveSession(sessionId)
    ElMessage.success("会话已归档")
  } catch {
    chatSessions.value = previousSessions
    ElMessage.error("归档会话失败")
  }
}

const handleChatSessionsChange = (event: Event) => {
  const detail = (event as CustomEvent<{ sessionId?: string | null }>).detail
  if (detail && "sessionId" in detail) currentChatSessionId.value = detail.sessionId ?? null
  void loadSidebarChatSessions()
}

const toggleUserMenu = () => {
  userMenuOpen.value = !userMenuOpen.value
}

const openSidebar = () => {
  sidebarOpen.value = true
}

const closeSidebar = () => {
  sidebarOpen.value = false
}

const toggleSidebarSize = () => {
  isSidebarCompact.value = !isSidebarCompact.value
  userMenuOpen.value = false
}

const refreshWorkspace = () => {
  componentRenderKey.value += 1
  void loadCurrentModel()
  void loadSidebarTraceQueue()
}

const applyTheme = (dark: boolean) => {
  isDark.value = dark
  document.documentElement.classList.toggle("dark", dark)
  document.documentElement.style.colorScheme = dark ? "dark" : "light"
}

const initTheme = () => {
  applyTheme(localStorage.getItem(THEME_STORAGE_KEY) !== "light")
}

const toggleTheme = () => {
  const next = !isDark.value
  applyTheme(next)
  localStorage.setItem(THEME_STORAGE_KEY, next ? "dark" : "light")
}

const handleAuthenticated = (user: AuthUser) => {
  currentUser.value = user
  void loadCurrentModel()
  void loadSidebarChatSessions()
  void loadSidebarTraceQueue()
}

const restoreSession = async () => {
  const token = getStoredAuthToken()
  if (!token) {
    authBooting.value = false
    return
  }

  try {
    currentUser.value = await fetchCurrentUser(token)
    void loadSidebarChatSessions()
    void loadSidebarTraceQueue()
  } catch {
    clearStoredAuthToken()
    currentUser.value = null
  } finally {
    authBooting.value = false
  }
}

const handleLogout = async () => {
  loggingOut.value = true
  try {
    await authLogout(getStoredAuthToken())
  } finally {
    currentUser.value = null
    loggingOut.value = false
    userMenuOpen.value = false
    closeSidebar()
  }
}

const selectNav = (id: NavId) => {
  activeTab.value = id
  userMenuOpen.value = false
  closeSidebar()
}

const openUserSettings = () => {
  userMenuOpen.value = false
  selectNav("settings")
}

onMounted(() => {
  initTheme()
  checkMobile()
  restoreSession()
  void loadCurrentModel()
  window.addEventListener("resize", checkMobile)
  window.addEventListener("agno-aios-model-change", handleModelChange)
  window.addEventListener("agno-aios-chat-sessions-change", handleChatSessionsChange)
})

onUnmounted(() => {
  window.removeEventListener("resize", checkMobile)
  window.removeEventListener("agno-aios-model-change", handleModelChange)
  window.removeEventListener("agno-aios-chat-sessions-change", handleChatSessionsChange)
})
</script>

<style>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.16s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
