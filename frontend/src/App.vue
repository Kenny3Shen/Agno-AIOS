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
      {{ t("shell.authChecking") }}
    </div>
  </div>

  <div v-else class="ag-os security-page h-dvh overflow-hidden">
    <transition name="fade">
      <button
        v-if="isMobile && sidebarOpen"
        type="button"
        class="ag-mobile-scrim fixed inset-0 z-40 lg:hidden"
        :aria-label="t('shell.closeSidebar')"
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
              :aria-label="isSidebarCompact ? t('shell.expandSidebar') : t('shell.collapseSidebar')"
              @click="toggleSidebarSize"
            >
              <el-icon>
                <Expand v-if="isSidebarCompact" />
                <Fold v-else />
              </el-icon>
            </button>

            <el-button v-if="isMobile" text :aria-label="t('shell.closeSidebar')" @click="closeSidebar">
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
              <template v-for="item in mainNavItems" :key="item.id">
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
                      :aria-label="chatSessionsExpanded ? t('shell.sessions.collapse') : t('shell.sessions.expand')"
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
                        <span>{{ t("shell.actions.newChat") }}</span>
                      </button>

                      <div class="ag-chat-session-head">
                        <span>{{ t("shell.sessions.title") }}</span>
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
                            <strong>{{ session.preview || t("shell.actions.newChat") }}</strong>
                            <em>{{ formatSessionTime(session.updated_at) }}</em>
                          </span>
                        </button>

                        <div class="ag-chat-session-menu-wrap">
                          <button
                            type="button"
                            class="ag-chat-session-menu-trigger"
                            :aria-label="t('shell.sessions.actions')"
                            :aria-expanded="openSessionMenuId === session.session_id"
                            @click.stop="toggleSessionMenu(session.session_id)"
                          >
                            :
                          </button>

                          <transition name="fade">
                            <div
                              v-if="openSessionMenuId === session.session_id"
                              class="ag-chat-session-menu"
                              role="menu"
                            >
                              <button type="button" role="menuitem" @click.stop="copySidebarSessionId(session.session_id)">
                                <el-icon><CopyDocument /></el-icon>
                                <span>{{ t("shell.actions.copySessionId") }}</span>
                              </button>
                              <button type="button" role="menuitem" @click.stop="copySidebarSessionRuns(session.session_id)">
                                <el-icon><CopyDocument /></el-icon>
                                <span>{{ t("shell.actions.copyRuns") }}</span>
                              </button>
                              <button type="button" role="menuitem" @click.stop="archiveSidebarChatSession(session.session_id)">
                                <el-icon><Delete /></el-icon>
                                <span>{{ t("shell.actions.archiveSession") }}</span>
                              </button>
                            </div>
                          </transition>
                        </div>
                      </div>

                      <div v-if="!chatSessions.length && !loadingSessions" class="ag-chat-session-empty">
                        {{ t("shell.actions.noSessions") }}
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

            <template v-if="securityDataNavItems.length">
              <div class="ag-nav-divider" aria-hidden="true" />

              <div class="ag-nav-list ag-nav-security-data">
                <button
                  v-for="item in securityDataNavItems"
                  :key="item.id"
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
              </div>
            </template>

            <div v-if="visibleSettingsItem" class="ag-nav-divider" aria-hidden="true" />

            <button
              v-if="visibleSettingsItem"
              type="button"
              class="ag-nav-item soc-focus"
              :class="{ active: visibleSettingsItem.id === activeTab }"
              :aria-current="visibleSettingsItem.id === activeTab ? 'page' : undefined"
              @click="selectNav(visibleSettingsItem.id)"
            >
              <span class="ag-nav-icon">
                <el-icon>
                  <component :is="visibleSettingsItem.icon" />
                </el-icon>
              </span>

              <span class="ag-nav-text min-w-0 flex-1">
                <span class="ag-nav-label">{{ visibleSettingsItem.label }}</span>
              </span>
            </button>
          </nav>

          <div class="ag-sidebar-footer">
            <div class="flex items-center justify-between gap-2">
              <span class="ag-footer-label">{{ t("shell.footer.currentSession") }}</span>
              <span class="ag-live-dot">
                <span />
                {{ t("shell.footer.authenticated") }}
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
                :aria-label="t('shell.userSettings')"
                :aria-expanded="userMenuOpen"
                @click="toggleUserMenu"
              >
                <el-icon><MoreFilled /></el-icon>
              </button>

              <transition name="fade">
                <div v-if="userMenuOpen" class="ag-user-menu" role="menu">
                  <button type="button" role="menuitem" @click="openUserSettings">
                    <el-icon><Setting /></el-icon>
                    <span>{{ t("shell.userSettings") }}</span>
                  </button>
                  <button type="button" role="menuitem" :disabled="loggingOut" @click="handleLogout">
                    <el-icon><SwitchButton /></el-icon>
                    <span>{{ loggingOut ? t("shell.loggingOut") : t("shell.logout") }}</span>
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
            <div class="ag-topbar-title" :title="currentMeta.description">
              <el-button v-if="isMobile" text class="!rounded-2" :aria-label="t('shell.openSidebar')" @click="openSidebar">
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
              </div>
            </div>

            <div class="ag-topbar-actions">
              <el-tooltip :content="t('shell.actions.refresh')" placement="bottom">
                <el-button
                  circle
                  class="ag-icon-button ag-topbar-icon"
                  :aria-label="t('shell.actions.refresh')"
                  @click="refreshWorkspace"
                >
                  <el-icon><Refresh /></el-icon>
                </el-button>
              </el-tooltip>

              <el-tooltip :content="isDark ? t('shell.theme.toLight') : t('shell.theme.toDark')" placement="bottom">
                <el-button
                  circle
                  class="ag-icon-button ag-topbar-icon"
                  :aria-label="isDark ? t('shell.theme.toLight') : t('shell.theme.toDark')"
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
                <section class="ag-home-summary">
                  <div class="ag-home-summary-copy">
                    <strong>{{ t("shell.home.title") }}</strong>
                    <span>{{ t("shell.home.description") }}</span>
                  </div>

                  <div class="ag-home-summary-strip">
                    <div v-for="signal in workspaceSignals" :key="signal.label" class="ag-home-signal ag-stat-chip">
                      <span>{{ signal.label }}</span>
                      <strong>{{ signal.value }}</strong>
                    </div>
                  </div>
                </section>

                <section v-for="section in homeSections" :key="section.title" class="ag-home-section">
                  <div class="ag-section-heading">
                    <h3>{{ section.title }}</h3>
                    <span class="ag-section-count">{{ section.items.length }}</span>
                  </div>

                  <div class="ag-module-grid">
                    <button
                      v-for="item in section.items"
                      :key="item.id"
                      type="button"
                      class="ag-module-card ag-module-tile"
                      :class="[`tone-${item.tone}`, { active: item.id === activeTab }]"
                      @click="selectNav(item.id)"
                    >
                      <span class="ag-module-icon">
                        <el-icon><component :is="item.icon" /></el-icon>
                      </span>
                      <span class="ag-module-copy">
                        <strong>{{ item.label }}</strong>
                        <em>{{ item.description }}</em>
                      </span>
                      <span v-if="item.badge" class="ag-module-badge">{{ item.badge }}</span>
                    </button>
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
import { computed, nextTick, onMounted, onUnmounted, ref, watch, type Component } from "vue"
import { useI18n } from "vue-i18n"
import { storeToRefs } from "pinia"
import {
  ArrowDown,
  ArrowRight,
  Calendar,
  ChatDotRound,
  Close,
  Connection,
  CopyDocument,
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
  Share,
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
import Workflow from "./components/Workflow.vue"
import Skills from "./components/Skills.vue"
import MCP from "./components/MCP.vue"
import Knowledge from "./components/Knowledge.vue"
import { useChatHistory, useSettingsApi } from "./composables/useApi"
import { setI18nLocale } from "./i18n"
import { clearStoredAuthToken, fetchCurrentUser, getStoredAuthToken, logout as authLogout, type AuthClientFallbackKey } from "./lib/authClient"
import { copyToClipboard } from "./lib/clipboard"
import {
  buildShellHomeSections,
  canAccessShellNav,
  osControlTabs,
  shellContentClass,
  splitPrimaryShellNavItems,
  type ActiveOsControlModule,
  type HomeSection,
  type ModuleNavId,
  type NavId,
  type NavItem,
} from "./modules/shellNavigation"
import { useAuthStore } from "./stores/auth"
import { useSessionStore } from "./stores/sessions"
import { useShellStore } from "./stores/shell"
import type { AuthUser } from "./types"

const { t } = useI18n()

const homeItem = computed<NavItem>(() => ({
  id: "home",
  label: t("shell.nav.home.label"),
  description: t("shell.nav.home.description"),
  icon: Platform,
  tone: "blue",
}))

const dashboardItem = computed<NavItem>(() => ({
  id: "dashboard",
  label: t("shell.nav.dashboard.label"),
  description: t("shell.nav.dashboard.description"),
  icon: DataBoard,
  badge: t("shell.badges.live"),
  tone: "green",
}))

const navItems = computed<NavItem[]>(() => [
  { id: "chat", label: t("shell.nav.chat.label"), description: t("shell.nav.chat.description"), icon: ChatDotRound, tone: "blue" },
  { id: "skills", label: t("shell.nav.skills.label"), description: t("shell.nav.skills.description"), icon: SetUp, tone: "red" },
  { id: "mcp", label: t("shell.nav.mcp.label"), description: t("shell.nav.mcp.description"), icon: Connection, tone: "yellow" },
  { id: "knowledge", label: t("shell.nav.knowledge.label"), description: t("shell.nav.knowledge.description"), icon: Files, tone: "green" },
  { id: "trace", label: t("shell.nav.trace.label"), description: t("shell.nav.trace.description"), icon: DataAnalysis, tone: "green" },
  { id: "workflow", label: t("shell.nav.workflow.label"), description: t("shell.nav.workflow.description"), icon: Share, tone: "yellow" },
  { id: "studio", label: t("shell.nav.studio.label"), description: t("shell.nav.studio.description"), icon: MagicStick, tone: "yellow" },
  { id: "memory", label: t("shell.nav.memory.label"), description: t("shell.nav.memory.description"), icon: Cpu, tone: "green" },
  { id: "evaluation", label: t("shell.nav.evaluation.label"), description: t("shell.nav.evaluation.description"), icon: Finished, tone: "green" },
  { id: "approvals", label: t("shell.nav.approvals.label"), description: t("shell.nav.approvals.description"), icon: Tickets, tone: "red" },
  { id: "scheduler", label: t("shell.nav.scheduler.label"), description: t("shell.nav.scheduler.description"), icon: Calendar, tone: "yellow" },
  { id: "cve", label: t("shell.nav.cve.label"), description: t("shell.nav.cve.description"), icon: Search, tone: "red" },
  { id: "assets", label: t("shell.nav.assets.label"), description: t("shell.nav.assets.description"), icon: Monitor, tone: "blue" },
  { id: "collect", label: t("shell.nav.collect.label"), description: t("shell.nav.collect.description"), icon: WarningFilled, tone: "yellow" },
  { id: "settings", label: t("shell.nav.settings.label"), description: t("shell.nav.settings.description"), icon: Setting, tone: "blue" },
])
const componentMap: Record<ModuleNavId, Component> = {
  dashboard: Dashboard,
  chat: Chat,
  knowledge: Knowledge,
  trace: Trace,
  workflow: Workflow,
  mcp: MCP,
  cve: CVE,
  assets: Assets,
  collect: Collect,
  skills: Skills,
  sessions: AgentOSControl,
  studio: AgentOSControl,
  memory: AgentOSControl,
  evaluation: AgentOSControl,
  approvals: AgentOSControl,
  scheduler: AgentOSControl,
  settings: Settings,
}

const availableNavIds = computed(() => new Set<NavId>(["home", "dashboard", ...navItems.value.map((item) => item.id)]))
const canAccessNav = (id: NavId) => {
  return canAccessShellNav(id, availableNavIds.value, (permission) => authStore.hasPermission(permission))
}
const settingsItem = computed<NavItem>(() => navItems.value.find((item) => item.id === "settings") as NavItem)
const visibleNavItems = computed<NavItem[]>(() => navItems.value.filter((item) => canAccessNav(item.id)))
const visibleSettingsItem = computed<NavItem | null>(() => {
  const item = settingsItem.value
  return canAccessNav(item.id) ? item : null
})
const shellNavGroups = computed(() => splitPrimaryShellNavItems(visibleNavItems.value))
const mainNavItems = computed<NavItem[]>(() => shellNavGroups.value.mainNavItems)
const securityDataNavItems = computed<NavItem[]>(() => shellNavGroups.value.securityDataNavItems)
const moduleNavItems = computed<NavItem[]>(() => [dashboardItem.value, ...navItems.value])
const visibleModuleNavItems = computed<NavItem[]>(() => [dashboardItem.value, ...visibleNavItems.value.filter((item) => item.id !== "dashboard")])
const navItemById = computed<Record<ModuleNavId, NavItem>>(() => (
  Object.fromEntries(moduleNavItems.value.map((item) => [item.id, item])) as Record<ModuleNavId, NavItem>
))
const homeSections = computed<HomeSection[]>(() => buildShellHomeSections({
  operations: t("shell.sections.operations"),
  controlPlane: t("shell.sections.controlPlane"),
  governance: t("shell.sections.governance"),
  securityData: t("shell.sections.securityData"),
}, navItemById.value, canAccessNav))
const THEME_STORAGE_KEY = "theme"
const CHAT_MODEL_STORAGE_KEY = "agno-aios-chat-model-id"
const SIDEBAR_EXPANDED_WIDTH = 264
const SIDEBAR_COMPACT_WIDTH = 76
const isMobileViewport = () => typeof window !== "undefined" && window.innerWidth < 1024

const authStore = useAuthStore()
const shellStore = useShellStore()
const sessionStore = useSessionStore()

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
  locale,
} = storeToRefs(shellStore)
const {
  chatSessions,
  currentChatSessionId,
  loadingSessions,
} = storeToRefs(sessionStore)

shellStore.setIsMobile(isMobileViewport())
const currentModelName = ref("DeepSeek V4 Pro")
const openSessionMenuId = ref<string | null>(null)
const authClientFallbacks = computed<Record<AuthClientFallbackKey, string>>(() => ({
  fetchUnsupported: t("auth.errors.fetchUnsupported"),
  loginFailed: t("auth.errors.loginFailed"),
  registerFailed: t("auth.errors.registerFailed"),
  currentUserFailed: t("auth.errors.currentUserFailed"),
  oauthProvidersFailed: t("auth.errors.oauthProvidersFailed"),
  oauthAuthorizeFailed: t("auth.errors.oauthAuthorizeFailed"),
  oauthMissingAuthorizationUrl: t("auth.errors.oauthMissingAuthorizationUrl"),
}))

const { fetchModels } = useSettingsApi()
const { listSessions, archiveSession } = useChatHistory()

watch(locale, (value) => setI18nLocale(value), { immediate: true })

const activeComponent = computed<Component | null>(() => {
  const tab = activeTab.value as NavId
  if (tab === "home") return null
  if (!canAccessNav(tab)) return null
  return componentMap[tab]
})
const currentMeta = computed<NavItem>(() => {
  if (activeTab.value === "home") return homeItem.value
  return visibleModuleNavItems.value.find((item) => item.id === activeTab.value) ?? homeItem.value
})
const currentUserEmail = computed(() => currentUser.value?.email || t("shell.user.anonymous"))
const userInitials = computed(() => {
  const email = currentUser.value?.email
  if (!email) return "AI"
  return email.slice(0, 2).toUpperCase()
})
const activeComponentKey = computed(() => `${activeTab.value}-${componentRenderKey.value}`)
const currentModelLabel = computed(() => formatModelLabel(currentModelName.value))
const currentUserId = computed(() => currentUser.value?.id || currentUser.value?.email || null)
const activeComponentProps = computed(() => {
  const tab = activeTab.value as NavId
  const baseProps = { currentUserId: currentUserId.value, currentUserInitials: userInitials.value }
  if (tab !== "home" && osControlTabs.has(tab as ActiveOsControlModule)) {
    return { ...baseProps, osModule: tab }
  }
  return baseProps
})
const contentClass = computed(() => {
  return shellContentClass(activeTab.value as NavId)
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
  { label: t("shell.signals.modules"), value: visibleModuleNavItems.value.length },
  { label: t("shell.signals.dataPlane"), value: t("shell.signalValues.dataPlane") },
  { label: t("shell.signals.runtime"), value: t("shell.signalValues.runtime") },
  { label: t("shell.signals.session"), value: currentUser.value?.is_active ? t("common.status.active") : t("common.status.ready") },
])

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
  if (!currentUser.value) {
    currentModelName.value = "DeepSeek V4 Pro"
    return
  }
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
  return new Date(timestamp * 1000).toLocaleString(locale.value, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

const loadSidebarChatSessions = async () => {
  if (!authStore.hasPermission("session:read:own")) {
    chatSessions.value = []
    return
  }
  sessionStore.setLoadingSessions(true)
  sessionStore.setSessionError(null)
  try {
    chatSessions.value = await listSessions()
  } catch (error) {
    chatSessions.value = []
    sessionStore.setSessionError(error instanceof Error ? error.message : t("shell.errors.sessionLoadFailed"))
  } finally {
    sessionStore.setLoadingSessions(false)
  }
}

const dispatchChatEvent = (name: string, detail?: Record<string, unknown>) => {
  void nextTick(() => {
    window.dispatchEvent(new CustomEvent(name, { detail }))
  })
}

const toggleChatSessions = () => {
  if (!authStore.hasPermission("session:read:own")) return
  chatSessionsExpanded.value = !chatSessionsExpanded.value
  if (chatSessionsExpanded.value) void loadSidebarChatSessions()
}

const toggleSessionMenu = (sessionId: string) => {
  openSessionMenuId.value = openSessionMenuId.value === sessionId ? null : sessionId
}

const copySidebarSessionId = async (sessionId: string) => {
  openSessionMenuId.value = null
  if (await copyToClipboard(sessionId)) {
    ElMessage.success(t("shell.messages.sessionIdCopied"))
  } else {
    ElMessage.warning(t("common.clipboard.failed"))
  }
}

const copySidebarSessionRuns = async (sessionId: string) => {
  openSessionMenuId.value = null
  try {
    const session = (await listSessions({ includeRuns: true }))
      .find((item) => item.session_id === sessionId)
    const payload = {
      session_id: sessionId,
      user_id: session?.user_id ?? null,
      runs: session?.runs ?? [],
    }
    if (await copyToClipboard(JSON.stringify(payload, null, 2))) {
      ElMessage.success(t("shell.messages.runsCopied"))
    } else {
      ElMessage.warning(t("common.clipboard.failed"))
    }
  } catch {
    ElMessage.warning(t("common.clipboard.failed"))
  }
}

const selectChatSession = (sessionId: string) => {
  openSessionMenuId.value = null
  currentChatSessionId.value = sessionId
  activeTab.value = "chat"
  userMenuOpen.value = false
  dispatchChatEvent("agno-aios-chat-session-select", { sessionId })
  closeSidebar()
}

const createSidebarChat = () => {
  openSessionMenuId.value = null
  currentChatSessionId.value = null
  activeTab.value = "chat"
  userMenuOpen.value = false
  dispatchChatEvent("agno-aios-chat-new")
  closeSidebar()
}

const archiveSidebarChatSession = async (sessionId: string) => {
  openSessionMenuId.value = null
  const previousSessions = chatSessions.value
  chatSessions.value = chatSessions.value.filter((session) => session.session_id !== sessionId)
  if (currentChatSessionId.value === sessionId) {
    currentChatSessionId.value = null
    dispatchChatEvent("agno-aios-chat-new")
  }
  try {
    await archiveSession(sessionId)
    ElMessage.success(t("shell.messages.sessionArchived"))
  } catch {
    chatSessions.value = previousSessions
    ElMessage.error(t("shell.messages.archiveSessionFailed"))
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
  openSessionMenuId.value = null
}

const refreshWorkspace = () => {
  componentRenderKey.value += 1
  void loadCurrentModel()
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
  if (authStore.hasPermission("session:read:own")) void loadSidebarChatSessions()
}

const restoreSession = async () => {
  const token = getStoredAuthToken()
  if (!token) {
    authBooting.value = false
    return
  }

  try {
    currentUser.value = await fetchCurrentUser(token, { fallbacks: authClientFallbacks.value })
    void loadCurrentModel()
    if (authStore.hasPermission("session:read:own")) void loadSidebarChatSessions()
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
    await authLogout(getStoredAuthToken(), { fallbacks: authClientFallbacks.value })
  } finally {
    currentUser.value = null
    loggingOut.value = false
    userMenuOpen.value = false
    closeSidebar()
  }
}

const selectNav = (id: NavId) => {
  if (!canAccessNav(id)) {
    activeTab.value = "home"
    userMenuOpen.value = false
    closeSidebar()
    return
  }
  activeTab.value = id
  userMenuOpen.value = false
  closeSidebar()
}

watch(
  () => [activeTab.value, currentUser.value?.role, currentUser.value?.is_superuser] as const,
  () => {
    if (!canAccessNav(activeTab.value as NavId)) activeTab.value = "home"
  },
  { immediate: true },
)

const openUserSettings = () => {
  userMenuOpen.value = false
  selectNav("settings")
}

onMounted(() => {
  initTheme()
  checkMobile()
  restoreSession()
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
