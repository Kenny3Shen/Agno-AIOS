<template>
  <div class="trace-span-hierarchy">
    <el-tree
      v-if="tree.length"
      :data="tree"
      node-key="span.span_id"
      :expand-on-click-node="false"
      default-expand-all
      class="trace-tree trace-hierarchy-tree"
      @node-click="(node: SpanTreeNode) => emit('nodeClick', node)"
    >
      <template #default="{ data }">
        <button
          type="button"
          class="trace-tree-node trace-hierarchy-node"
          :class="{ active: selectedSpan?.span_id === data.span.span_id, error: data.span.status_code === 'ERROR' }"
          @click.stop="emit('selectSpan', data.span, 'input')"
        >
          <span class="trace-status-dot" :class="statusClass(data.span.status_code)" />
          <span class="trace-hierarchy-node-copy">
            <strong :title="data.span.name">{{ data.span.name }}</strong>
            <small>{{ data.span.kind || 'span' }} · {{ formatDuration(data.span.duration_ms) }}</small>
          </span>
        </button>
      </template>
    </el-tree>

    <div v-else-if="spans.length" class="trace-hierarchy-fallback">
      <button
        v-for="span in spans"
        :key="span.span_id"
        type="button"
        class="trace-tree-node trace-hierarchy-node"
        :class="{ active: selectedSpan?.span_id === span.span_id, error: span.status_code === 'ERROR' }"
        @click="emit('selectSpan', span, 'input')"
      >
        <span class="trace-status-dot" :class="statusClass(span.status_code)" />
        <span class="trace-hierarchy-node-copy">
          <strong :title="span.name">{{ span.name }}</strong>
          <small>{{ span.kind || 'span' }} · {{ formatDuration(span.duration_ms) }}</small>
        </span>
      </button>
    </div>

    <div v-else class="empty-observe">
      <el-icon><Connection /></el-icon>
      <strong>{{ t('trace.empty.noSpansTitle') }}</strong>
      <span>{{ t('trace.empty.noSpansDescription') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Connection } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import {
  formatTraceDuration,
  traceStatusClass,
  type TraceDetailSection,
} from "../../modules/traceWorkbench"
import type { SpanItem, SpanTreeNode } from "../../types"

defineProps<{
  tree: SpanTreeNode[]
  spans: SpanItem[]
  selectedSpan: SpanItem | null
}>()

const emit = defineEmits<{
  selectSpan: [span: SpanItem, section: TraceDetailSection]
  nodeClick: [node: SpanTreeNode]
}>()

const { t } = useI18n()
const formatDuration = formatTraceDuration
const statusClass = traceStatusClass
</script>
