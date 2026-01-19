<template>
  <div class="min-h-screen flex bg-[#F6F8FA] text-slate-900 dark:bg-[#212830] dark:text-[#C9D1D9]">
    <!-- 移动端遮罩层 -->
    <transition name="el-fade-in">
      <div
        v-if="isMobile && sidebarVisible"
        class="fixed inset-0 bg-black/50 z-40 sm:hidden"
        @click="closeSidebar"
      />
    </transition>

    <!-- 侧边栏 -->
    <aside
      ref="sidebarRef"
      :class="[
        'bg-white dark:bg-[#212830] border border-[#D0D7DE] dark:border-[#30363D] shadow-sm flex flex-col z-50 transition-all duration-300 overflow-hidden',
        isMobile
          ? 'fixed h-full sm:relative rounded-none'
          : 'relative m-4 rounded-2xl h-[calc(100vh-2rem)]',
        isMobile && sidebarVisible
          ? 'translate-x-0'
          : (isMobile ? '-translate-x-full' : 'translate-x-0')
      ]"
      :style="{ width: collapsed && !isMobile ? `${collapsedWidth}px` : `${sidebarWidth}px` }"
    >
      <!-- Logo 区域 -->
      <div class="p-4 sm:p-5 border-b border-[#D0D7DE] dark:border-[#30363D] flex items-center justify-between">
        <div class="flex items-center overflow-hidden">
          <el-icon class="text-slate-900 dark:text-[#C9D1D9] text-xl sm:text-2xl flex-shrink-0">
            <Platform />
          </el-icon>
          <transition name="el-fade-in">
            <h1
              v-if="!collapsed && !isMobile"
              class="ml-3 text-base sm:text-lg font-semibold text-slate-900 dark:text-[#C9D1D9] whitespace-nowrap"
            >
              情报平台
            </h1>
          </transition>
        </div>
        <!-- 移动端关闭按钮 -->
        <el-button
          v-if="isMobile"
          type="text"
          @click="closeSidebar"
          class="text-slate-700 dark:text-[#C9D1D9] hover:bg-slate-100 dark:hover:bg-[#212830]/80 -mr-2"
          aria-label="关闭侧边栏"
        >
          <el-icon><Close /></el-icon>
        </el-button>
      </div>

      <!-- 菜单区域 -->
      <nav class="flex-1 overflow-y-auto">
        <div v-if="!collapsed || isMobile" class="px-3 sm:px-4 pt-3 sm:pt-4">
          <label class="sr-only" for="nav-search">搜索功能</label>
          <el-input
            id="nav-search"
            v-model="navQuery"
            clearable
            size="small"
            placeholder="搜索功能…"
            class="[&_.el-input__wrapper]:!bg-transparent [&_.el-input__wrapper]:!shadow-none [&_.el-input__wrapper]:!border [&_.el-input__wrapper]:!border-[#D0D7DE] dark:[&_.el-input__wrapper]:!border-[#30363D]"
          />
        </div>

        <div class="px-2 sm:px-3 pb-3 sm:pb-4" :class="(!collapsed || isMobile) ? 'pt-3 sm:pt-4' : 'pt-3'">
          <template v-for="section in navSections" :key="section.title">
            <div v-if="(!collapsed && !isMobile)" class="px-2 pb-2 text-[11px] font-semibold tracking-wide text-slate-600 dark:text-[#8B949E]">
              {{ section.title }}
            </div>
            <div class="space-y-1">
              <template v-for="item in section.items" :key="item.id">
                <el-tooltip
                  :disabled="!collapsed || isMobile"
                  :content="item.label"
                  placement="right"
                  :show-after="150"
                >
                  <button
                    type="button"
                    @click="selectNav(item.id)"
                    class="w-full flex items-center justify-between gap-2 px-2.5 py-2 rounded-xl border border-transparent transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0969DA] focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-[#212830]"
                    :class="item.id === activeTab
                      ? 'bg-[#0969DA]/10 dark:bg-[#1F6FEB]/20 text-slate-900 dark:text-[#C9D1D9] border-[#0969DA]/20 dark:border-[#1F6FEB]/30'
                      : 'hover:bg-slate-900/5 dark:hover:bg-[#212830]/80 text-slate-700 dark:text-[#C9D1D9]'"
                    :aria-current="item.id === activeTab ? 'page' : undefined"
                  >
                    <span class="flex items-center gap-3 min-w-0">
                      <span class="grid place-items-center w-8 h-8 rounded-lg bg-slate-900/5 dark:bg-[#0D1117] border border-[#D0D7DE] dark:border-[#30363D] flex-shrink-0">
                        <el-icon class="text-slate-700 dark:text-[#8B949E]">
                          <component :is="item.icon" />
                        </el-icon>
                      </span>

                      <span v-if="!collapsed && !isMobile" class="min-w-0">
                        <div class="text-sm font-medium truncate">{{ item.label }}</div>
                      </span>
                    </span>

                    <span v-if="!collapsed && !isMobile && item.badge" class="text-[11px] px-2 py-0.5 rounded-full border border-[#D0D7DE] dark:border-[#30363D] text-slate-600 dark:text-[#8B949E]">
                      {{ item.badge }}
                    </span>
                  </button>
                </el-tooltip>
              </template>
            </div>

            <div class="h-3" />
          </template>
        </div>
      </nav>

      <!-- 折叠按钮（桌面端） -->
      <transition name="el-fade-in">
        <div
          v-if="!isMobile"
          class="p-2 sm:p-4 border-t border-[#D0D7DE] dark:border-[#30363D] flex justify-center"
        >
          <el-button
            type="text"
            @click="toggleCollapse"
            class="text-slate-700 dark:text-[#C9D1D9] hover:bg-slate-100 dark:hover:bg-[#21262D] w-full rounded-xl"
            aria-label="折叠侧边栏"
          >
            <el-icon>
              <Expand v-if="collapsed" />
              <Fold v-else />
            </el-icon>
          </el-button>
        </div>
      </transition>
    </aside>

    <!-- 拖拽缩放条（仅桌面端） -->
    <div
      v-if="!isMobile"
      class="resizer bg-transparent cursor-col-resize hidden sm:block my-4 rounded-full"
      @mousedown.prevent="startDrag"
      title="拖动调整侧边栏宽度"
    />

    <!-- 主内容区 -->
    <main class="flex-1 flex flex-col min-w-0 overflow-hidden p-3 sm:p-4">
      <!-- 状态栏 -->
      <div
        class="bg-white dark:bg-[#212830] shadow-sm border border-[#D0D7DE] dark:border-[#30363D] px-4 sm:px-5 py-3 rounded-2xl flex items-center justify-between"
      >
        <div class="flex items-center space-x-2 sm:space-x-4">
          <!-- 移动端菜单按钮 -->
          <el-button
            v-if="isMobile"
            type="text"
            @click="openSidebar"
            class="text-slate-700 dark:text-[#C9D1D9] hover:bg-slate-100 dark:hover:bg-[#212830]/80 rounded-xl"
            aria-label="打开侧边栏"
          >
            <el-icon size="20"><Menu /></el-icon>
          </el-button>
          <!-- 面包屑/标题 -->
          <div class="flex items-center space-x-2">
            <el-icon class="text-slate-500 dark:text-[#8B949E] hidden sm:block"><Platform /></el-icon>
            <h2 class="text-base sm:text-lg font-semibold text-slate-900 dark:text-[#C9D1D9]">
              {{ currentTitle }}
            </h2>
          </div>
        </div>
        <!-- 右侧操作区 -->
        <div class="flex items-center space-x-2">
          <el-button
            circle
            type="default"
            class="!border-[#D0D7DE] dark:!border-[#30363D] bg-white dark:bg-[#212830] hover:bg-slate-50 dark:hover:bg-[#212830]/80"
            @click="toggleTheme"
            :aria-label="isDark ? '切换到浅色模式' : '切换到深色模式'"
          >
            <el-icon>
              <Moon v-if="!isDark" />
              <Sunny v-else />
            </el-icon>
          </el-button>
        </div>
      </div>

      <!-- 内容区域 -->
      <div class="flex-1 mt-3 sm:mt-4 overflow-auto">
        <div class="max-w-7xl mx-auto bg-white dark:bg-[#212830] rounded-2xl border border-[#D0D7DE] dark:border-[#30363D] shadow-sm p-4 sm:p-6">
          <transition name="el-fade-in" mode="out-in">
            <keep-alive>
              <component :is="activeComponent" :key="activeTab" />
            </keep-alive>
          </transition>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue"
import CveSearch from "./components/CveSearch.vue"
import AssetSearch from "./components/AssetSearch.vue"
import LlmChat from "./components/LlmChat.vue"
import Url2Md from "./components/Url2Md.vue"

const activeTab = ref("cve")

// 将 activeTab 映射到组件
const activeComponent = computed(() => {
  switch (activeTab.value) {
    case "asset":
      return AssetSearch
    case "chat":
      return LlmChat
    case "url2md":
      return Url2Md
    case "cve":
    default:
      return CveSearch
  }
})

// 当前页面标题
const currentTitle = computed(() => {
  switch (activeTab.value) {
    case "asset":
      return "资产搜索"
    case "chat":
      return "LLM 聊天"
    case "url2md":
      return "网页解析"
    case "cve":
    default:
      return "CVE 搜索"
  }
})

// 响应式检测
const isMobile = ref(false)
const checkMobile = () => {
  isMobile.value = window.innerWidth < 640
}

// 主题（深色模式）
const THEME_STORAGE_KEY = "theme"
const isDark = ref(false)

const applyTheme = (dark: boolean) => {
  isDark.value = dark
  document.documentElement.classList.toggle("dark", dark)
  document.documentElement.style.colorScheme = dark ? "dark" : "light"
}

const initTheme = () => {
  const saved = localStorage.getItem(THEME_STORAGE_KEY)
  if (saved === "dark") {
    applyTheme(true)
    return
  }
  if (saved === "light") {
    applyTheme(false)
    return
  }

  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)")?.matches
  applyTheme(Boolean(prefersDark))
}

const toggleTheme = () => {
  const next = !isDark.value
  applyTheme(next)
  localStorage.setItem(THEME_STORAGE_KEY, next ? "dark" : "light")
}

type NavItem = {
  id: string
  label: string
  badge?: string
  icon: string
  group: "搜索" | "工具"
}

const navQuery = ref("")
const navItems = computed<NavItem[]>(() => [
  { id: "cve", label: "CVE 搜索", icon: "Search", group: "搜索" },
  { id: "asset", label: "资产搜索", icon: "Monitor", group: "搜索" },
  { id: "url2md", label: "网页解析", icon: "WarningFilled", group: "工具" },
  { id: "chat", label: "LLM 聊天", icon: "ChatDotRound", group: "工具", badge: "Beta" }
])

const navSections = computed(() => {
  const q = navQuery.value.trim().toLowerCase()
  const items = navItems.value.filter((it) => {
    if (!q) return true
    return [it.label, it.group].filter(Boolean).some((s) => String(s).toLowerCase().includes(q))
  })

  const groups: Array<NavItem["group"]> = ["搜索", "工具"]
  return groups
    .map((g) => ({ title: g, items: items.filter((it) => it.group === g) }))
    .filter((s) => s.items.length > 0)
})

const selectNav = (id: string) => {
  activeTab.value = id
  if (isMobile.value) closeSidebar()
}

onMounted(() => {
  initTheme()
  checkMobile()
  window.addEventListener("resize", checkMobile)
})

onUnmounted(() => {
  window.removeEventListener("resize", checkMobile)
})

// Sidebar state
const collapsed = ref(false)
const sidebarVisible = ref(false)
const sidebarRef = ref<HTMLElement | null>(null)
const sidebarWidth = ref(170)
const collapsedWidth = 72
const minWidth = 64
const maxWidth = 380
let dragging = false

// 移动端侧边栏控制
const openSidebar = () => {
  sidebarVisible.value = true
}

const closeSidebar = () => {
  sidebarVisible.value = false
}

// 桌面端折叠控制
const toggleCollapse = () => {
  collapsed.value = !collapsed.value
}

// 拖拽调整宽度（仅桌面端）
const startDrag = (_: MouseEvent) => {
  if (collapsed.value || isMobile.value) return
  dragging = true
  window.addEventListener('mousemove', onDrag)
  window.addEventListener('mouseup', stopDrag)
}

const onDrag = (e: MouseEvent) => {
  if (!dragging) return
  const sidebarRect = sidebarRef.value?.getBoundingClientRect()
  if (!sidebarRect) return
  const newWidth = e.clientX - sidebarRect.left
  if (newWidth >= minWidth && newWidth <= maxWidth) {
    sidebarWidth.value = newWidth
  }
}

const stopDrag = () => {
  if (!dragging) return
  dragging = false
  window.removeEventListener('mousemove', onDrag)
  window.removeEventListener('mouseup', stopDrag)
}
</script>

<style>
/* 全局样式重置 */
* {
  box-sizing: border-box;
}

/* 拖拽调整条样式 */
.resizer {
  width: 6px;
  cursor: col-resize;
  transition: background-color 0.2s;
}

.resizer:hover {
  background-color: rgba(48, 54, 61, 0.35);
}

.resizer:active {
  background-color: rgba(48, 54, 61, 0.55);
}

html.dark .resizer:hover {
  background-color: rgba(148, 163, 184, 0.25);
}

html.dark .resizer:active {
  background-color: rgba(148, 163, 184, 0.4);
}

/* 移动端过渡动画 */
@media (max-width: 640px) {
  aside {
    transition: transform 0.3s ease;
  }
}

/* 滚动条美化 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: rgba(156, 163, 175, 0.5);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: rgba(156, 163, 175, 0.7);
}

html.dark ::-webkit-scrollbar-thumb {
  background: rgba(48, 54, 61, 0.65);
}

html.dark ::-webkit-scrollbar-thumb:hover {
  background: rgba(48, 54, 61, 0.85);
}

/* Element Plus 过渡动画优化 */
.el-fade-in-enter-active,
.el-fade-in-leave-active {
  transition: opacity 0.3s ease;
}

.el-fade-in-enter-from,
.el-fade-in-leave-to {
  opacity: 0;
}

/* 移动端优化触摸反馈 */
@media (hover: none) and (pointer: coarse) {
  button:active { opacity: 0.98; }
}

@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
</style>
