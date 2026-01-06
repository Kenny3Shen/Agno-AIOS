<template>
  <div class="min-h-screen bg-gray-100 flex">
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
        'bg-gradient-to-b from-blue-600 to-blue-700 shadow-lg flex flex-col z-50 transition-all duration-300',
        isMobile
          ? 'fixed h-full sm:relative'
          : 'relative',
        isMobile && sidebarVisible
          ? 'translate-x-0'
          : (isMobile ? '-translate-x-full' : 'translate-x-0')
      ]"
      :style="{ width: collapsed && !isMobile ? `${collapsedWidth}px` : `${sidebarWidth}px` }"
    >
      <!-- Logo 区域 -->
      <div class="p-4 sm:p-6 border-b border-blue-500 flex items-center justify-between">
        <div class="flex items-center overflow-hidden">
          <el-icon class="text-white text-xl sm:text-2xl flex-shrink-0">
            <Platform />
          </el-icon>
          <transition name="el-fade-in">
            <h1
              v-if="!collapsed && !isMobile"
              class="ml-3 text-lg sm:text-xl font-bold text-white whitespace-nowrap"
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
          class="text-white hover:bg-blue-500 -mr-2"
        >
          <el-icon><Close /></el-icon>
        </el-button>
      </div>

      <!-- 菜单区域 -->
      <nav class="p-2 sm:p-4 flex-1 overflow-y-auto">
        <el-menu
          :default-active="activeTab"
          @select="handleMenuSelect"
          :collapse="collapsed && !isMobile"
          class="border-none bg-transparent"
          text-color="#e0e7ff"
          active-text-color="#ffffff"
        >
          <el-menu-item index="cve">
            <el-icon><Search /></el-icon>
            <span>CVE 搜索</span>
          </el-menu-item>
          <el-menu-item index="asset">
            <el-icon><Monitor /></el-icon>
            <span>资产搜索</span>
          </el-menu-item>
          <el-menu-item index="url2md">
            <el-icon><WarningFilled /></el-icon>
            <span>网页解析</span>
          </el-menu-item>
          <el-menu-item index="chat">
            <el-icon><ChatDotRound /></el-icon>
            <span>LLM 聊天</span>
          </el-menu-item>
        </el-menu>
      </nav>

      <!-- 折叠按钮（桌面端） -->
      <transition name="el-fade-in">
        <div
          v-if="!isMobile"
          class="p-2 sm:p-4 border-t border-blue-500 flex justify-center"
        >
          <el-button
            type="text"
            @click="toggleCollapse"
            class="text-white hover:bg-blue-500 w-full"
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
      class="resizer bg-transparent cursor-col-resize hidden sm:block"
      @mousedown.prevent="startDrag"
      title="拖动调整侧边栏宽度"
    />

    <!-- 主内容区 -->
    <main class="flex-1 flex flex-col min-w-0 overflow-hidden">
      <!-- 状态栏 -->
      <div
        class="bg-white shadow-sm border-b border-gray-200 px-4 sm:px-6 py-3 flex items-center justify-between"
      >
        <div class="flex items-center space-x-2 sm:space-x-4">
          <!-- 移动端菜单按钮 -->
          <el-button
            v-if="isMobile"
            type="text"
            @click="openSidebar"
            class="text-gray-700 hover:bg-gray-100"
          >
            <el-icon size="20"><Menu /></el-icon>
          </el-button>
          <!-- 面包屑/标题 -->
          <div class="flex items-center space-x-2">
            <el-icon class="text-gray-500 hidden sm:block"><Platform /></el-icon>
            <h2 class="text-base sm:text-lg font-semibold text-gray-800">
              {{ currentTitle }}
            </h2>
          </div>
        </div>
        <!-- 右侧操作区 -->
        <div class="flex items-center space-x-2">
          <el-tag type="info" size="small" class="hidden sm:inline-block">
            V 1.0.0
          </el-tag>
        </div>
      </div>

      <!-- 内容区域 -->
      <div class="flex-1 p-4 sm:p-6 lg:p-8 bg-gray-50 overflow-auto">
        <div class="max-w-7xl mx-auto bg-white rounded-lg shadow-lg p-4 sm:p-6">
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

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
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

const handleMenuSelect = (index: string) => {
  activeTab.value = index
  // 移动端选择后关闭侧边栏
  if (isMobile.value) {
    closeSidebar()
  }
}
</script>

<style>
/* 全局样式重置 */
* {
  box-sizing: border-box;
}

/* Element Plus 菜单项样式优化 */
.el-menu-item {
  margin-bottom: 6px;
  border-radius: 8px;
  transition: all 0.2s ease;
}

.el-menu-item.is-active {
  background-color: rgba(255, 255, 255, 0.2) !important;
  color: #ffffff !important;
  font-weight: 500;
}

.el-menu-item:hover {
  background-color: rgba(255, 255, 255, 0.1);
  transform: translateX(2px);
}

/* 拖拽调整条样式 */
.resizer {
  width: 6px;
  cursor: col-resize;
  transition: background-color 0.2s;
}

.resizer:hover {
  background-color: rgba(59, 130, 246, 0.3);
}

.resizer:active {
  background-color: rgba(59, 130, 246, 0.5);
}

/* 移动端过渡动画 */
@media (max-width: 640px) {
  aside {
    transition: transform 0.3s ease;
  }

  .el-menu {
    border-right: none;
  }

  .el-menu-item {
    margin-bottom: 4px;
    border-radius: 6px;
  }
}

/* 响应式字体大小 */
@media (max-width: 640px) {
  .el-menu-item span {
    font-size: 15px;
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
  .el-menu-item:active {
    background-color: rgba(255, 255, 255, 0.15) !important;
  }
}
</style>
