<template>
  <div class="security-page h-dvh overflow-hidden bg-[#EEF3F7] text-[#111827] dark:bg-[#071014] dark:text-[#E6EDF3]">
    <transition name="fade">
      <button
        v-if="isMobile && sidebarOpen"
        type="button"
        class="fixed inset-0 z-40 bg-black/60 lg:hidden"
        aria-label="关闭导航遮罩"
        @click="closeSidebar"
      />
    </transition>

    <div class="h-full min-h-0 lg:grid lg:grid-cols-[272px_minmax(0,1fr)]">
      <aside
        :class="[
          'fixed inset-y-0 left-0 z-50 flex w-[272px] flex-col overflow-hidden border-r border-[#B8C8D8] bg-[#E1E9F1] transition-transform duration-200 lg:relative lg:z-auto lg:translate-x-0 dark:border-[#20313D] dark:bg-[#0B141B]',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full',
        ]"
      >
        <div class="shrink-0 border-b border-[#B8C8D8] p-4 dark:border-[#20313D]">
          <div class="flex items-center justify-between gap-3">
            <div class="flex min-w-0 items-center gap-3">
              <span class="grid h-10 w-10 shrink-0 place-items-center rounded-2 border border-[#2F8FED]/35 bg-[#EAF5FF] text-[#0969DA] dark:bg-[#102638] dark:text-[#6AD7FF]">
                <el-icon size="21"><Platform /></el-icon>
              </span>
              <div class="min-w-0">
                <h1 class="truncate text-base font-700 text-[#0F172A] dark:text-white">Agno AIOS</h1>
                <p class="mt-1 truncate text-xs text-[#64748B] dark:text-[#8EA0AE]">AI 信息安全中台</p>
              </div>
            </div>

            <el-button v-if="isMobile" text aria-label="关闭侧边栏" @click="closeSidebar">
              <el-icon><Close /></el-icon>
            </el-button>
          </div>

          <div class="mt-4 grid grid-cols-2 gap-2">
            <div v-for="metric in sidebarMetrics" :key="metric.label" class="rounded-2 border border-[#B8C8D8] bg-[#F8FAFC] p-2.5 dark:border-[#20313D] dark:bg-[#0E171F]">
              <div class="text-[11px] text-[#64748B] dark:text-[#8EA0AE]">{{ metric.label }}</div>
              <div class="mt-1 text-sm font-700 text-[#0F172A] dark:text-[#E6EDF3]">{{ metric.value }}</div>
            </div>
          </div>
        </div>

        <div class="shrink-0 border-b border-[#B8C8D8] p-3 dark:border-[#20313D]">
          <label class="sr-only" for="nav-search">搜索模块</label>
          <el-input id="nav-search" v-model="navQuery" clearable size="small" placeholder="搜索模块" class="security-nav-search">
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>

        <nav class="min-h-0 flex-1 overflow-y-auto px-3 py-4">
          <section v-for="section in navSections" :key="section.title" class="mb-5">
            <div class="mb-2 px-2 text-[11px] font-700 tracking-wide text-[#64748B] dark:text-[#6F8394]">
              {{ section.title }}
            </div>

            <div class="space-y-1">
              <button
                v-for="item in section.items"
                :key="item.id"
                type="button"
                class="soc-focus group flex h-12 w-full cursor-pointer items-center gap-3 rounded-2 border px-2.5 text-left transition-colors duration-150"
                :class="item.id === activeTab
                  ? 'border-[#2F8FED]/65 bg-white text-[#0F4F8F] shadow-sm dark:bg-[#102638] dark:text-[#DDF4FF]'
                : 'border-transparent text-[#263342] hover:border-[#B8C8D8] hover:bg-white dark:text-[#B7C4CF] dark:hover:border-[#20313D] dark:hover:bg-[#0E171F]'"
                :aria-current="item.id === activeTab ? 'page' : undefined"
                @click="selectNav(item.id)"
              >
                <span
                  class="grid h-8 w-8 shrink-0 place-items-center rounded-2 border"
                  :class="item.id === activeTab
                    ? 'border-[#2F8FED]/45 bg-white text-[#0969DA] dark:bg-[#0B141B] dark:text-[#6AD7FF]'
                    : 'border-[#CBD6E2] bg-[#F8FAFC] text-[#526170] group-hover:bg-white group-hover:text-[#0969DA] dark:border-[#20313D] dark:bg-[#071014] dark:text-[#8EA0AE]'"
                >
                  <el-icon>
                    <component :is="item.icon" />
                  </el-icon>
                </span>

                <span class="min-w-0 flex-1">
                  <span class="block truncate text-sm font-650">{{ item.label }}</span>
                  <span class="mt-0.5 block truncate text-[11px] text-[#64748B] dark:text-[#6F8394]">{{ item.description }}</span>
                </span>

                <span v-if="item.badge" class="shrink-0 rounded-1 border border-[#CBD5E1] px-1.5 py-0.5 text-[10px] text-[#64748B] dark:border-[#2A3A45] dark:text-[#8EA0AE]">
                  {{ item.badge }}
                </span>
              </button>
            </div>
          </section>
        </nav>

        <div class="shrink-0 border-t border-[#B8C8D8] p-3 dark:border-[#20313D]">
          <div class="rounded-2 border border-[#B8C8D8] bg-[#F8FAFC] p-3 dark:border-[#20313D] dark:bg-[#0E171F]">
            <div class="flex items-center justify-between gap-2">
              <span class="text-xs font-650 text-[#334155] dark:text-[#D8E1E8]">平台联通状态</span>
              <span class="inline-flex items-center gap-1.5 text-[11px] font-650 text-[#14824A] dark:text-[#54D38A]">
                <span class="h-2 w-2 rounded-full bg-[#54D38A]" />
                Online
              </span>
            </div>
            <p class="mt-2 text-[11px] leading-5 text-[#64748B] dark:text-[#8EA0AE]">
              情报、资产、Agent 工具链统一编排。
            </p>
          </div>
        </div>
      </aside>

      <main class="flex h-dvh min-w-0 flex-col overflow-hidden">
        <header class="shrink-0 border-b border-[#B8C8D8] bg-white px-4 py-3 shadow-sm dark:border-[#20313D] dark:bg-[#0B141B] dark:shadow-none">
          <div class="flex min-w-0 flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <div class="flex min-w-0 items-center gap-3">
              <el-button v-if="isMobile" text class="!rounded-2" aria-label="打开侧边栏" @click="openSidebar">
                <el-icon size="20"><Menu /></el-icon>
              </el-button>

              <span class="grid h-10 w-10 shrink-0 place-items-center rounded-2 border border-[#D8E0E7] bg-[#F8FAFC] text-[#0969DA] dark:border-[#20313D] dark:bg-[#0E171F] dark:text-[#6AD7FF]">
                <el-icon><component :is="currentMeta.icon" /></el-icon>
              </span>

              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="rounded-1 border border-[#CBD5E1] bg-[#F8FAFC] px-2 py-0.5 text-[11px] font-650 text-[#475569] dark:border-[#20313D] dark:bg-[#0E171F] dark:text-[#8EA0AE]">
                    Security Command Center
                  </span>
                  <span class="rounded-1 border border-[#2F8FED]/30 bg-[#EAF5FF] px-2 py-0.5 text-[11px] font-650 text-[#0969DA] dark:bg-[#102638] dark:text-[#6AD7FF]">
                    Agent Ready
                  </span>
                </div>
                <h2 class="mt-1 truncate text-xl font-750 text-[#0F172A] dark:text-white">{{ currentMeta.label }}</h2>
                <p class="mt-0.5 truncate text-xs text-[#64748B] dark:text-[#8EA0AE]">{{ currentMeta.description }}</p>
              </div>
            </div>

            <div class="flex flex-wrap items-center gap-2">
              <div v-for="signal in headerSignals" :key="signal.label" class="min-w-[88px] rounded-2 border border-[#C6D3DF] bg-[#F8FAFC] px-3 py-2 dark:border-[#20313D] dark:bg-[#0E171F]">
                <div class="text-[10px] font-650 uppercase tracking-wide text-[#64748B] dark:text-[#6F8394]">{{ signal.label }}</div>
                <div class="mt-0.5 truncate text-sm font-750 text-[#0F172A] dark:text-[#E6EDF3]">{{ signal.value }}</div>
              </div>

              <el-tooltip :content="isDark ? '切换浅色模式' : '切换深色模式'" placement="bottom">
                <el-button
                  circle
                  class="!border-[#CBD5E1] !bg-white dark:!border-[#20313D] dark:!bg-[#0E171F]"
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
          </div>
        </header>

        <section class="hidden shrink-0 grid-cols-4 gap-3 border-b border-[#C6D3DF] bg-[#E8EEF4] px-4 py-3 xl:grid dark:border-[#20313D] dark:bg-[#071014]">
          <article v-for="metric in workspaceMetrics" :key="metric.label" class="rounded-2 border border-[#C6D3DF] bg-white p-3 shadow-sm dark:border-[#20313D] dark:bg-[#0E171F] dark:shadow-none">
            <div class="flex items-center justify-between gap-2">
              <span class="text-xs font-650 text-[#475569] dark:text-[#8EA0AE]">{{ metric.label }}</span>
              <span class="h-2 w-2 rounded-full" :class="metric.dot" />
            </div>
            <div class="mt-2 truncate text-base font-750 text-[#0F172A] dark:text-white">{{ metric.value }}</div>
            <div class="mt-1 truncate text-[11px] text-[#64748B] dark:text-[#6F8394]">{{ metric.note }}</div>
          </article>
        </section>

        <section class="min-h-0 flex-1 overflow-hidden bg-[#EEF3F7] p-3 sm:p-4 dark:bg-[#071014]">
          <div class="h-full min-h-0 overflow-hidden rounded-2 border border-[#C2D0DC] bg-white shadow-sm dark:border-[#20313D] dark:bg-[#0E171F] dark:shadow-none">
            <transition name="fade" mode="out-in">
              <keep-alive>
                <component
                  :is="activeComponent"
                  :key="activeTab"
                  :class="contentClass"
                />
              </keep-alive>
            </transition>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, type Component } from "vue"
import {
  ChatDotRound,
  Close,
  Connection,
  DataAnalysis,
  DataBoard,
  Files,
  Menu,
  Monitor,
  Moon,
  Platform,
  Search,
  Setting,
  SetUp,
  Sunny,
  WarningFilled,
} from "@element-plus/icons-vue"
import CveSearch from "./components/CveSearch.vue"
import AssetSearch from "./components/AssetSearch.vue"
import LlmChat from "./components/LlmChat.vue"
import Url2Md from "./components/Url2Md.vue"
import Settings from "./components/Settings.vue"
import AgentSituation from "./components/AgentSituation.vue"
import AgentTracing from "./components/AgentTracing.vue"
import SkillManage from "./components/SkillManage.vue"
import McpManage from "./components/McpManage.vue"
import KnowledgeManage from "./components/KnowledgeManage.vue"

type NavId = "cve" | "asset" | "url2md" | "situation" | "chat" | "knowledge" | "tracing" | "mcp" | "skills" | "settings"
type NavGroup = "AI 工作台" | "情报检索" | "运营配置"

type NavItem = {
  id: NavId
  label: string
  description: string
  badge?: string
  icon: Component
  group: NavGroup
}

const navItems: NavItem[] = [
  { id: "situation", label: "态势总览", description: "Agent 运行态势与异常", icon: DataBoard, group: "AI 工作台", badge: "Live" },
  { id: "chat", label: "Agent 对话", description: "任务编排与流式分析", icon: ChatDotRound, group: "AI 工作台" },
  { id: "knowledge", label: "RAG 知识库", description: "知识写入、检索与参数", icon: Files, group: "AI 工作台" },
  { id: "tracing", label: "运行观测", description: "Agent Trace 与 Span 追踪", icon: DataAnalysis, group: "AI 工作台" },
  { id: "mcp", label: "MCP 工具中枢", description: "服务、Token 与外部 Agent", icon: Connection, group: "AI 工作台" },
  { id: "cve", label: "CVE 情报", description: "漏洞检索与攻击面线索", icon: Search, group: "情报检索" },
  { id: "asset", label: "资产画像", description: "指纹、IP 与暴露面查询", icon: Monitor, group: "情报检索" },
  { id: "url2md", label: "网页解析", description: "情报页面转 Markdown", icon: WarningFilled, group: "情报检索" },
  { id: "skills", label: "Skills 管理", description: "安全能力模块开关", icon: SetUp, group: "运营配置" },
  { id: "settings", label: "系统配置", description: "模型、MCP 与通知配置", icon: Setting, group: "运营配置" },
]

const componentMap: Record<NavId, Component> = {
  situation: AgentSituation,
  chat: LlmChat,
  knowledge: KnowledgeManage,
  tracing: AgentTracing,
  mcp: McpManage,
  cve: CveSearch,
  asset: AssetSearch,
  url2md: Url2Md,
  skills: SkillManage,
  settings: Settings,
}

const fullCanvasTabs = new Set<NavId>(["situation", "chat", "tracing", "mcp"])
const navGroups: NavGroup[] = ["AI 工作台", "情报检索", "运营配置"]
const THEME_STORAGE_KEY = "theme"

const activeTab = ref<NavId>("situation")
const navQuery = ref("")
const isMobile = ref(false)
const sidebarOpen = ref(false)
const isDark = ref(true)

const sidebarMetrics = computed(() => [
  { label: "能力模块", value: String(navItems.length) },
  { label: "工作模式", value: "SOC" },
])

const headerSignals = [
  { label: "LLM", value: "Routing" },
  { label: "MCP", value: "Direct" },
  { label: "Risk", value: "Watched" },
]

const workspaceMetrics = [
  { label: "情报源", value: "CVE / Exploit", note: "漏洞与利用线索聚合", dot: "bg-[#2F8FED]" },
  { label: "资产面", value: "Fingerprint", note: "按 IP 或技术栈定位", dot: "bg-[#54D38A]" },
  { label: "AI 编排", value: "AgentOS", note: "支持技能驱动分析", dot: "bg-[#F6C343]" },
  { label: "运行态势", value: "Run / Trace", note: "异常可观测、链路可追溯", dot: "bg-[#F06A6A]" },
]

const activeComponent = computed(() => componentMap[activeTab.value])
const fallbackMeta = navItems[0]!
const currentMeta = computed<NavItem>(() => navItems.find((item) => item.id === activeTab.value) ?? fallbackMeta)
const contentClass = computed(() => {
  const base = "block h-full min-h-0"
  return fullCanvasTabs.has(activeTab.value) ? base : `${base} overflow-auto p-4 sm:p-5`
})

const navSections = computed(() => {
  const query = navQuery.value.trim().toLowerCase()
  const items = navItems.filter((item) => {
    if (!query) return true
    return [item.label, item.description, item.group].some((text) => text.toLowerCase().includes(query))
  })

  return navGroups
    .map((group) => ({ title: group, items: items.filter((item) => item.group === group) }))
    .filter((section) => section.items.length > 0)
})

const checkMobile = () => {
  isMobile.value = window.innerWidth < 1024
  if (!isMobile.value) sidebarOpen.value = false
}

const openSidebar = () => {
  sidebarOpen.value = true
}

const closeSidebar = () => {
  sidebarOpen.value = false
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

const selectNav = (id: NavId) => {
  activeTab.value = id
  closeSidebar()
}

onMounted(() => {
  initTheme()
  checkMobile()
  window.addEventListener("resize", checkMobile)
})

onUnmounted(() => {
  window.removeEventListener("resize", checkMobile)
})
</script>

<style>
.security-nav-search .el-input__wrapper {
  background: #f8fafc;
  border: 1px solid #d8e0e7;
  border-radius: 8px;
  box-shadow: none;
}

html.dark .security-nav-search .el-input__wrapper {
  background: #071014;
  border-color: #20313d;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.16s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
