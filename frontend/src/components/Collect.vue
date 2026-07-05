<template>
  <div class="collect-console ag-page-flow">
    <section class="collect-query-panel ag-content-panel">
      <div class="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
        <el-input
          v-model="url"
          :placeholder="t('collect.input.urlPlaceholder')"
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
            :loading="loading"
            :disabled="loading || !isValidUrl"
            class="flex-1 sm:flex-none"
            @click="handleParse"
          >
            <el-icon class="mr-1"><Connection /></el-icon>
            {{ t('collect.actions.parse') }}
          </el-button>
          <el-button
            type="default"
            :disabled="loading"
            class="flex-1 sm:flex-none"
            @click="clear"
          >
            <el-icon class="mr-1"><Delete /></el-icon>
            {{ t('collect.actions.clear') }}
          </el-button>
        </div>
      </div>
    </section>

    <!-- 消息提示 -->
    <transition name="el-fade-in-linear">
      <div v-if="message">
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

    <section class="collect-result-panel ag-content-panel">
      <transition name="el-fade-in">
        <div v-if="markdownText || renderedHtml" class="flex flex-col gap-4">
          <el-tabs v-model="activeTab" class="w-full">
            <el-tab-pane :label="t('collect.tabs.markdown')" name="markdown">
              <template #label>
                <div class="flex items-center gap-1.5">
                  <el-icon><Document /></el-icon>
                  <span>{{ t('collect.tabs.markdown') }}</span>
                </div>
              </template>
              <div class="relative">
                <el-input
                  v-model="markdownText"
                  type="textarea"
                  :rows="isMobile ? 15 : 20"
                  :placeholder="t('collect.editor.placeholder')"
                  class="w-full font-mono text-sm"
                />
                <el-button
                  v-if="markdownText"
                  type="primary"
                  circle
                  size="small"
                  class="!absolute top-2 right-2 z-10"
                  @click="copyMarkdown"
                >
                  <el-icon><DocumentCopy /></el-icon>
                </el-button>
              </div>
            </el-tab-pane>

            <el-tab-pane :label="t('collect.tabs.preview')" name="preview">
              <template #label>
                <div class="flex items-center gap-1.5">
                  <el-icon><View /></el-icon>
                  <span>{{ t('collect.tabs.preview') }}</span>
                </div>
              </template>
              <div
                class="markdown-preview prose prose-sm sm:prose max-w-none min-h-[200px] sm:min-h-[300px] overflow-auto"
                v-html="renderedHtml"
              />
            </el-tab-pane>
          </el-tabs>
        </div>
      </transition>

      <transition name="el-fade-in">
        <el-empty
          v-if="!markdownText && !loading && !message"
          :description="t('collect.empty.description')"
          :image-size="isMobile ? 100 : 120"
        >
          <template #description>
            <p class="empty-title">{{ t('collect.empty.title') }}</p>
            <p class="empty-hint">{{ t('collect.empty.hint') }}</p>
          </template>
        </el-empty>
      </transition>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import { useUrl2MdApi } from '../composables/useApi'
import { useSecurityDataStore } from '../stores/securityData'
import { useShellStore } from '../stores/shell'
import { copyToClipboard } from '../lib/clipboard'
import { ElMessage } from 'element-plus'
import { Link, Connection, Delete, DocumentCopy, Document, View } from '@element-plus/icons-vue'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: true, linkify: true })
const { t } = useI18n()
const shellStore = useShellStore()
const securityDataStore = useSecurityDataStore()

const isMobile = computed(() => shellStore.isMobile)

const {
  collectActiveTab: activeTab,
  collectUrl: url,
  collectMarkdownText: markdownText,
  collectMessage: message,
} = storeToRefs(securityDataStore)

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
  if (await copyToClipboard(markdownText.value)) {
    ElMessage.success(t('collect.messages.copied'))
  } else {
    ElMessage.error(t('collect.messages.copyFailed'))
  }
}

// 事件处理
const handleParse = async () => {
  if (!isValidUrl.value) {
    message.value = {
      type: 'warning',
      title: t('collect.messages.invalidUrlTitle'),
      description: t('collect.messages.invalidUrlDescription')
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
        title: t('collect.messages.parseSuccessTitle'),
        description: t('collect.messages.parseSuccessDescription')
      }
    } else {
      message.value = {
        type: 'info',
        title: t('collect.messages.emptyContentTitle'),
        description: t('collect.messages.emptyContentDescription')
      }
    }
  } catch (err: unknown) {
    console.error('URL parse error:', err)
    message.value = {
      type: 'error',
      title: t('collect.messages.parseFailedTitle'),
      description: err instanceof Error ? err.message : t('collect.messages.networkError')
    }
  }
}

const clear = () => {
  securityDataStore.resetCollect()
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
  color: var(--ag-blue);
  text-decoration: underline;
}

.prose :deep(code) {
  background-color: var(--ag-code-bg);
  color: var(--ag-code-text);
  padding: 0.2em 0.4em;
  border-radius: 0.25em;
  font-size: 0.875em;
}

.prose :deep(pre) {
  background-color: var(--ag-code-bg);
  color: var(--ag-code-text);
  padding: 1em;
  border-radius: 0.5em;
  overflow-x: auto;
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
  border-left: 4px solid var(--ag-border);
  padding-left: 1em;
  margin: 1em 0;
  color: var(--ag-muted);
}

.prose :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 1em 0;
}

.prose :deep(th),
.prose :deep(td) {
  border: 1px solid var(--ag-border);
  padding: 0.5em;
}

.prose :deep(th) {
  background-color: var(--ag-panel-soft);
  font-weight: 600;
}

.markdown-preview {
  border: 1px solid var(--ag-panel-border);
  border-radius: var(--ag-radius-panel);
  background: var(--ag-panel-bg);
  padding: var(--ag-space-md);
  color: var(--ag-text);
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
