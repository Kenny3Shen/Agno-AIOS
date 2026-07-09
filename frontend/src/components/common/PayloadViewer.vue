<template>
  <section class="ag-code-panel">
    <header class="flex min-w-0 items-center justify-between gap-2 border-b border-[var(--ag-border)] bg-[var(--ag-panel-soft)] px-3 py-2">
      <div class="flex min-w-0 items-center gap-2">
        <button
          v-for="option in modeOptions"
          :key="option"
          type="button"
          :class="[
            'rounded-[var(--ag-radius-control)] px-2 py-1 text-[11px] font-760 uppercase text-[var(--ag-muted)] transition-colors',
            activeMode === option ? 'bg-[var(--ag-panel)] text-[var(--ag-heading)] shadow-[inset_0_0_0_1px_var(--ag-border)]' : 'hover:text-[var(--ag-blue)]',
          ]"
          :aria-pressed="activeMode === option"
          @click="activeMode = option"
        >
          {{ option }}
        </button>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <button
          type="button"
          class="ag-icon-button-compact"
          :aria-label="copyLabel"
          :title="copyLabel"
          @click="copyPayload"
        >
          <el-icon>
            <Check v-if="copied" />
            <CopyDocument v-else />
          </el-icon>
        </button>
        <button
          type="button"
          class="ag-icon-button-compact"
          :aria-label="expanded ? collapseLabel : expandLabel"
          :title="expanded ? collapseLabel : expandLabel"
          @click="expanded = !expanded"
        >
          <el-icon>
            <ArrowUp v-if="expanded" />
            <ArrowDown v-else />
          </el-icon>
        </button>
      </div>
    </header>

    <div v-if="!displayText.trim()" class="ag-empty-compact m-3">
      {{ emptyText }}
    </div>
    <div
      v-else
      class="overflow-auto p-3"
      :style="expanded ? undefined : { maxHeight: `${maxCollapsedHeight}px` }"
    >
      <MarkdownViewer v-if="activeMode === 'markdown'" :content="displayText" />
      <pre v-else class="m-0 whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">{{ displayText }}</pre>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ArrowDown, ArrowUp, Check, CopyDocument } from "@element-plus/icons-vue"
import { copyToClipboard } from "../../lib/clipboard"
import MarkdownViewer from "./MarkdownViewer.vue"

type PayloadViewMode = "text" | "json" | "markdown"

const props = withDefaults(defineProps<{
  value?: unknown
  text?: string
  mode?: PayloadViewMode
  emptyText?: string
  copyLabel?: string
  expandLabel?: string
  collapseLabel?: string
  maxCollapsedHeight?: number
}>(), {
  value: undefined,
  text: "",
  mode: "text",
  emptyText: "No content",
  copyLabel: "Copy",
  expandLabel: "Expand",
  collapseLabel: "Collapse",
  maxCollapsedHeight: 220,
})

const modeOptions: PayloadViewMode[] = ["text", "json", "markdown"]
const activeMode = ref<PayloadViewMode>(props.mode)
const expanded = ref(false)
const copied = ref(false)
let copiedTimer: ReturnType<typeof window.setTimeout> | undefined

watch(() => props.mode, (mode) => {
  activeMode.value = mode
})

const baseText = computed(() => {
  if (props.text) return props.text
  if (props.value === undefined || props.value === null) return ""
  if (typeof props.value === "string") return props.value
  try {
    return JSON.stringify(props.value, null, 2)
  } catch {
    return String(props.value)
  }
})

const displayText = computed(() => {
  if (activeMode.value !== "json") return baseText.value
  try {
    return JSON.stringify(JSON.parse(baseText.value), null, 2)
  } catch {
    if (typeof props.value === "object" && props.value !== null) {
      try {
        return JSON.stringify(props.value, null, 2)
      } catch {
        return baseText.value
      }
    }
    return baseText.value
  }
})

const copyPayload = async () => {
  if (!displayText.value.trim()) return
  if (await copyToClipboard(displayText.value)) {
    copied.value = true
    if (copiedTimer) window.clearTimeout(copiedTimer)
    copiedTimer = window.setTimeout(() => {
      copied.value = false
    }, 1200)
  }
}
</script>
