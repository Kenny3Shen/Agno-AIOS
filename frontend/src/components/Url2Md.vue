<template>
  <div class="space-y-4">
    <div class="flex gap-4 items-center">
      <el-input
        v-model="url"
        placeholder="请输入要解析的网址 (例如：https://example.com)"
        class="flex-1"
        clearable
      />
      <el-button type="primary" @click="handleParse" :loading="loading" :disabled="loading || !isValidUrl">解析</el-button>
      <el-button type="default" @click="clear" :disabled="loading">清空</el-button>
    </div>

    <div v-if="message" class="mt-2">
      <el-alert :type="message.type" :title="message.title" :description="message.description" show-icon closable @close="message = null" />
    </div>

    <div class="flex flex-col gap-4">
      <div>
        <div class="mb-2 text-sm text-gray-500">Markdown 文本</div>
        <el-input
          type="textarea"
          :rows="18"
          v-model="markdownText"
          placeholder="解析后会在这里显示 Markdown 文本，可以手动编辑或复制"
          class="w-full"
        />
      </div>

      <div>
        <div class="mb-2 text-sm text-gray-500">渲染预览</div>
        <div class="prose max-w-none p-4 bg-white border rounded min-h-[300px]" v-html="renderedHtml"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue' 
import axios from 'axios'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: true, linkify: true })

const url = ref('')
const loading = ref(false)
const markdownText = ref('')
const message = ref<{ type: 'success' | 'warning' | 'info' | 'error'; title: string; description?: string } | null>(null)

// Decode HTML entities (safe in browser). Backend may return escaped HTML like "&lt;p&gt;"
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


const renderedHtml = computed(() => {
  try {
    return md.render((markdownText.value as any) || '')
  } catch (e) {
    return ''
  }
})


const isValidUrl = computed(() => {
  if (!url.value) return false
  try {
    new URL(url.value)
    return true
  } catch (e) {
    return false
  }
})


const handleParse = async () => {
  if (!isValidUrl.value) {
    message.value = { type: 'warning', title: '无效网址', description: '请输入一个有效的 URL' }
    return
  }

  loading.value = true
  message.value = null
  markdownText.value = ''

  try {
    // 后端接口：POST /api/url2md/parse，返回 { markdown: string | string[] }
    const resp = await axios.post('/api/url2md/parse', { url: url.value })
    if (resp.data && resp.data.markdown) {
      // 后端有时返回数组（每个 URL 的结果），将其规范为字符串
      const mdData = resp.data.markdown
      if (Array.isArray(mdData)) {
        // 合并多个结果，或取第一个非空项
        const joined = mdData.filter(Boolean).join('\n\n')
        markdownText.value = decodeHtmlEntities(joined)
      } else {
        markdownText.value = decodeHtmlEntities(String(mdData))
      }

      message.value = { type: 'success', title: '解析成功', description: '已获取 Markdown 内容' }
    } else {
      message.value = { type: 'info', title: '未返回内容', description: '后端未返回 Markdown 文本' }
    }
  } catch (err: any) {
    console.error('URL parse error:', err)
    message.value = { type: 'error', title: '解析失败', description: err.response?.data?.message || err.message || '网络或后端错误' }
  } finally {
    loading.value = false
  }
}

const clear = () => {
  url.value = ''
  markdownText.value = ''
  message.value = null
}


</script>

<style scoped>
.prose img {
  max-width: 100%;
}
</style>
