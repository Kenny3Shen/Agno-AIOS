<template>
  <div class="security-page space-y-4">
    <!-- 搜索区域 -->
    <div class="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center">
      <el-input
        v-model="url"
        placeholder="请输入要解析的网址 (例如：https://example.com)"
        class="flex-1"
        clearable
      >
        <template #prefix>
          <el-icon><Link /></el-icon>
        </template>
      </el-input>
      <div class="flex gap-2">
        <el-button
          type="primary"
          @click="handleParse"
          :loading="loading"
          :disabled="loading || !isValidUrl"
          class="flex-1 sm:flex-none"
        >
          <el-icon class="mr-1"><Connection /></el-icon>
          解析
        </el-button>
        <el-button
          type="default"
          @click="clear"
          :disabled="loading"
          class="flex-1 sm:flex-none"
        >
          <el-icon class="mr-1"><Delete /></el-icon>
          清空
        </el-button>
      </div>
    </div>

    <!-- 消息提示 -->
    <transition name="el-fade-in-linear">
      <div v-if="message" class="mt-2">
        <el-alert
          :type="message.type"
          :title="message.title"
          :description="message.description"
          show-icon
          closable
          @close="message = null"
        />
      </div>
    </transition>

    <!-- 结果展示区域 -->
    <transition name="el-fade-in">
      <div v-if="markdownText || renderedHtml" class="flex flex-col gap-4">
        <!-- Tab 切换 -->
        <el-tabs v-model="activeTab" class="w-full">
          <!-- Markdown 文本 Tab -->
          <el-tab-pane label="Markdown 文本" name="markdown">
            <template #label>
              <div class="flex items-center gap-1.5">
                <el-icon><Document /></el-icon>
                <span>Markdown 文本</span>
              </div>
            </template>
            <div class="relative">
              <el-input
                type="textarea"
                :rows="isMobile ? 15 : 20"
                v-model="markdownText"
                placeholder="解析后会在这里显示 Markdown 文本，可以手动编辑或复制"
                class="w-full font-mono text-sm"
              />
              <!-- 复制按钮 - 浮动在右上角 -->
              <el-button
                v-if="markdownText"
                type="primary"
                circle
                size="small"
                @click="copyMarkdown"
                class="!absolute top-2 right-2 z-10"
              >
                <el-icon><DocumentCopy /></el-icon>
              </el-button>
            </div>
          </el-tab-pane>

          <!-- 渲染预览 Tab -->
          <el-tab-pane label="渲染预览" name="preview">
            <template #label>
              <div class="flex items-center gap-1.5">
                <el-icon><View /></el-icon>
                <span>渲染预览</span>
              </div>
            </template>
            <div
              class="prose prose-sm sm:prose max-w-none p-4 bg-white dark:bg-[#212830] border border-[#D0D7DE] dark:border-[#30363D] rounded min-h-[200px] sm:min-h-[300px] overflow-auto"
              v-html="renderedHtml"
            />
          </el-tab-pane>
        </el-tabs>
      </div>
    </transition>

    <!-- 空状态提示 -->
    <transition name="el-fade-in">
      <el-empty
        v-if="!markdownText && !loading && !message"
        description="输入网址并点击解析"
        :image-size="isMobile ? 100 : 120"
      >
        <template #description>
          <p class="text-gray-500">输入网址并点击解析按钮</p>
          <p class="text-gray-400 text-sm mt-2">支持将网页内容转换为 Markdown 格式</p>
        </template>
      </el-empty>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useUrl2MdApi } from '../composables/useApi'
import { ElMessage } from 'element-plus'
import { Link, Connection, Delete, DocumentCopy, Document, View } from '@element-plus/icons-vue'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: true, linkify: true })

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

// Tab 切换状态
const activeTab = ref<'markdown' | 'preview'>('markdown')

// 查询状态
const url = ref('')
const markdownText = ref('')
const message = ref<{
  type: 'success' | 'warning' | 'info' | 'error'
  title: string
  description?: string
} | null>(null)

// API hooks
const { loading, parseUrl } = useUrl2MdApi()

// 计算属性
const renderedHtml = computed(() => {
  try {
    return md.render(markdownText.value || '')
  } catch {
    return ''
  }
})

const isValidUrl = computed(() => {
  if (!url.value) return false
  try {
    new URL(url.value)
    return true
  } catch {
    return false
  }
})

// 工具函数
const decodeHtmlEntities = (s: string) => {
  if (!s) return s
  if (typeof document !== 'undefined') {
    const txt = document.createElement('textarea')
    txt.innerHTML = s
    return txt.value
  }
  return s
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
}

const copyMarkdown = async () => {
  try {
    await navigator.clipboard.writeText(markdownText.value)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

// 事件处理
const handleParse = async () => {
  if (!isValidUrl.value) {
    message.value = {
      type: 'warning',
      title: '无效网址',
      description: '请输入一个有效的 URL'
    }
    return
  }

  try {
    const resp = await parseUrl(url.value)
    if (resp.markdown) {
      const mdData = resp.markdown
      if (Array.isArray(mdData)) {
        const joined = mdData.filter(Boolean).join('\n\n')
        markdownText.value = decodeHtmlEntities(joined)
      } else {
        markdownText.value = decodeHtmlEntities(String(mdData))
      }

      message.value = {
        type: 'success',
        title: '解析成功',
        description: '已获取 Markdown 内容'
      }
    } else {
      message.value = {
        type: 'info',
        title: '未返回内容',
        description: '后端未返回 Markdown 文本'
      }
    }
  } catch (err: unknown) {
    console.error('URL parse error:', err)
    message.value = {
      type: 'error',
      title: '解析失败',
      description: err instanceof Error ? err.message : '网络或后端错误'
    }
  }
}

const clear = () => {
  url.value = ''
  markdownText.value = ''
  message.value = null
}
</script>

<style scoped>
/* Markdown 预览样式优化 */
.prose {
  line-height: 1.6;
}

.prose :deep(h1),
.prose :deep(h2),
.prose :deep(h3),
.prose :deep(h4),
.prose :deep(h5),
.prose :deep(h6) {
  font-weight: 600;
  margin-top: 1.5em;
  margin-bottom: 0.5em;
}

.prose :deep(p) {
  margin-bottom: 1em;
}

.prose :deep(a) {
  color: #2563eb;
  text-decoration: underline;
}

.prose :deep(code) {
  background-color: #f3f4f6;
  padding: 0.2em 0.4em;
  border-radius: 0.25em;
  font-size: 0.875em;
}

html.dark .prose :deep(code) {
  background-color: rgba(148, 163, 184, 0.25);
}

.prose :deep(pre) {
  background-color: #1f2937;
  color: #f9fafb;
  padding: 1em;
  border-radius: 0.5em;
  overflow-x: auto;
}

html.dark .prose :deep(pre) {
  background-color: rgba(0, 0, 0, 0.35);
}

.prose :deep(pre code) {
  background-color: transparent;
  padding: 0;
}

.prose :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 0.5em;
}

.prose :deep(blockquote) {
  border-left: 4px solid #e5e7eb;
  padding-left: 1em;
  margin: 1em 0;
  color: #6b7280;
}

html.dark .prose :deep(blockquote) {
  border-left-color: #30363d;
  color: #8b949e;
}

.prose :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 1em 0;
}

.prose :deep(th),
.prose :deep(td) {
  border: 1px solid #e5e7eb;
  padding: 0.5em;
}

html.dark .prose :deep(th),
html.dark .prose :deep(td) {
  border-color: #30363d;
}

.prose :deep(th) {
  background-color: #f9fafb;
  font-weight: 600;
}

html.dark .prose :deep(th) {
  background-color: rgba(148, 163, 184, 0.12);
}

/* 响应式优化 */
@media (max-width: 640px) {
  .prose {
    font-size: 14px;
  }

  :deep(.el-textarea__inner) {
    font-size: 13px;
  }
}
</style>
