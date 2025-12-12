<template>
  <div class="min-h-screen bg-gray-100 flex">
    <!-- 侧边栏 -->
    <aside
      ref="sidebarRef"
      :style="{ width: collapsed ? `${collapsedWidth}px` : `${sidebarWidth}px` }"
      class="bg-gradient-to-b from-blue-600 to-blue-700 shadow-lg transition-width duration-200 overflow-hidden flex flex-col"
    >
      <div class="p-6 border-b border-blue-500 flex items-center">
        <el-icon class="text-white text-2xl flex-shrink-0">
          <Platform />
        </el-icon>
        <h1 v-if="!collapsed" class="ml-3 text-xl font-bold text-white">情报平台</h1>
      </div>
      <nav class="p-4 flex-1">
        <el-menu
          :default-active="activeTab"
          @select="handleMenuSelect"
          :collapse="collapsed"
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
    </aside>
    <!-- 拖拽缩放条 -->
    <div
      class="resizer bg-transparent cursor-col-resize"
      @mousedown.prevent="startDrag"
      title="拖动调整侧边栏宽度"
    />

    <!-- 主内容区 -->
    <main class="flex-1 flex flex-col min-w-0">
      <!-- 状态栏 -->
      <div class="bg-white shadow-sm border-b border-gray-200 px-6 py-3 flex items-center justify-between">
        <div class="flex items-center space-x-4">
          <el-button type="text" @click="toggleCollapse" size="big">
            <el-icon>
              <Expand v-if="collapsed" />
              <Fold v-else />
            </el-icon>
          </el-button>
        </div>
      </div>
      <!-- 内容区域 -->
      <div class="flex-1 p-8 bg-gray-50">
        <div class="max-w-7xl mx-auto bg-white rounded-lg shadow-lg p-6">
          <keep-alive>
            <component :is="activeComponent" />
          </keep-alive>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue"
import CveSearch from "./components/CveSearch.vue"
import AssetSearch from "./components/AssetSearch.vue"
import LlmChat from "./components/LlmChat.vue"
import Url2Md from "./components/Url2Md.vue"

const activeTab = ref("cve")

// 将 activeTab 映射到组件，配合 keep-alive 使用，以便切换时保留组件状态（例如搜索查询）
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

// Sidebar state
const collapsed = ref(false)
const sidebarRef = ref<HTMLElement | null>(null)
const sidebarWidth = ref(170)
const collapsedWidth = 72
const minWidth = 64
const maxWidth = 380
let dragging = false

const toggleCollapse = () => {
  collapsed.value = !collapsed.value
}

const startDrag = (_: MouseEvent) => {
  if (collapsed.value) return
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
}
</script>

<style>
.el-menu-item {
  margin-bottom: 8px;
  border-radius: 8px;
}

.el-menu-item.is-active {
  background-color: rgba(255, 255, 255, 0.2) !important;
  color: #ffffff !important;
}

.el-menu-item:hover {
  background-color: rgba(255, 255, 255, 0.1);
}

.resizer {
  width: 6px;
  cursor: col-resize;
}

aside.transition-width {
  transition-property: width;
  transition-duration: 200ms;
}
</style>
