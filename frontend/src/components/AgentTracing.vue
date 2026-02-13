<template>
  <div class="h-full min-h-0 flex flex-col gap-4">
    <!-- Filters -->
    <div class="flex flex-wrap items-center gap-2">
      <div class="flex items-center gap-2">
        <span class="text-xs text-slate-500 dark:text-[#8B949E]">Session</span>
        <el-input
          v-model="filters.session_id"
          size="small"
          clearable
          placeholder="session_id（可从聊天侧边栏复制）"
          class="w-[260px]"
        />
      </div>

      <div class="flex items-center gap-2">
        <span class="text-xs text-slate-500 dark:text-[#8B949E]">状态</span>
        <el-select v-model="filters.status" size="small" clearable placeholder="全部" class="w-[120px]">
          <el-option label="OK" value="OK" />
          <el-option label="ERROR" value="ERROR" />
          <el-option label="UNSET" value="UNSET" />
        </el-select>
      </div>

      <div class="flex items-center gap-2">
        <span class="text-xs text-slate-500 dark:text-[#8B949E]">时间</span>
        <el-date-picker
          v-model="filters.timeRange"
          type="datetimerange"
          size="small"
          unlink-panels
          start-placeholder="开始"
          end-placeholder="结束"
          value-format="YYYY-MM-DDTHH:mm:ssXXX"
        />
      </div>

      <div class="flex-1"></div>

      <el-button size="small" :loading="loading" @click="refresh" class="cursor-pointer">
        <el-icon class="mr-1"><Refresh /></el-icon>
        刷新
      </el-button>

      <el-button size="small" :disabled="!selectedTrace" @click="copySelectedTraceId" class="cursor-pointer">
        <el-icon class="mr-1"><CopyDocument /></el-icon>
        复制 Trace ID
      </el-button>
    </div>

    <!-- Main split -->
    <div class="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-4">
      <!-- Trace list -->
      <section class="min-h-0 lg:col-span-4 flex flex-col rounded-xl border border-[#D0D7DE] dark:border-[#30363D] bg-white dark:bg-[#0D1117] overflow-hidden">
        <div class="px-4 py-3 border-b border-[#D0D7DE] dark:border-[#30363D] flex items-center justify-between">
          <div>
            <div class="text-sm font-semibold text-slate-900 dark:text-[#C9D1D9]">Traces</div>
            <div class="text-xs text-slate-500 dark:text-[#8B949E]">每次 Agent 运行会生成一个 Trace，可向下钻取 Spans</div>
          </div>
          <div class="text-xs text-slate-500 dark:text-[#8B949E]">共 {{ totalCount }} 条</div>
        </div>

        <div class="flex-1 min-h-0 overflow-auto">
          <el-table
            :data="traceItems"
            size="small"
            highlight-current-row
            @current-change="onTraceSelect"
            class="w-full"
          >
            <el-table-column label="时间" width="165">
              <template #default="{ row }">
                <div class="text-[11px] text-slate-600 dark:text-[#8B949E]">
                  {{ fmt(row.start_time) }}
                </div>
              </template>
            </el-table-column>

            <el-table-column label="名称" min-width="200">
              <template #default="{ row }">
                <div class="text-xs font-medium text-slate-900 dark:text-[#C9D1D9] truncate" :title="row.name">
                  {{ row.name }}
                </div>
                <div class="text-[10px] text-slate-500 dark:text-[#8B949E] truncate" :title="row.trace_id">
                  {{ row.trace_id }}
                </div>
              </template>
            </el-table-column>

            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="tagType(row.status)" effect="light" size="small">
                  {{ row.status }}
                </el-tag>
              </template>
            </el-table-column>

            <el-table-column label="耗时" width="90" align="right">
              <template #default="{ row }">
                <span class="text-xs tabular-nums text-slate-700 dark:text-[#C9D1D9]">{{ formatDuration(row.duration_ms) }}</span>
              </template>
            </el-table-column>

            <el-table-column label="Spans" width="70" align="right">
              <template #default="{ row }">
                <span class="text-xs tabular-nums text-slate-600 dark:text-[#8B949E]">{{ row.total_spans ?? '-' }}</span>
              </template>
            </el-table-column>

            <el-table-column label="Errors" width="70" align="right">
              <template #default="{ row }">
                <span class="text-xs tabular-nums" :class="(row.error_count ?? 0) > 0 ? 'text-red-600 dark:text-red-400' : 'text-slate-600 dark:text-[#8B949E]'">
                  {{ row.error_count ?? 0 }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="px-4 py-3 border-t border-[#D0D7DE] dark:border-[#30363D] flex items-center justify-between">
          <el-pagination
            small
            background
            layout="prev, pager, next"
            :total="totalCount"
            :page-size="limit"
            :current-page="page"
            @current-change="onPageChange"
          />
          <div class="text-[11px] text-slate-500 dark:text-[#8B949E]">
            limit {{ limit }}
          </div>
        </div>
      </section>

      <!-- Detail -->
      <section class="min-h-0 lg:col-span-8 flex flex-col rounded-xl border border-[#D0D7DE] dark:border-[#30363D] bg-white dark:bg-[#0D1117] overflow-hidden">
        <div class="px-4 py-3 border-b border-[#D0D7DE] dark:border-[#30363D] flex items-center justify-between">
          <div>
            <div class="text-sm font-semibold text-slate-900 dark:text-[#C9D1D9]">详情</div>
            <div class="text-xs text-slate-500 dark:text-[#8B949E]">Trace 元信息 + Span 树（点击节点查看 attributes）</div>
          </div>
        </div>

        <div v-if="!selectedTrace" class="flex-1 min-h-0 grid place-items-center p-6">
          <div class="text-center">
            <div class="text-sm font-medium text-slate-700 dark:text-[#C9D1D9]">请选择一个 Trace</div>
            <div class="text-xs text-slate-500 dark:text-[#8B949E] mt-1">左侧列表中点击即可查看运行细节</div>
          </div>
        </div>

        <div v-else class="flex-1 min-h-0 overflow-auto p-4 space-y-4">
          <div class="rounded-lg border border-[#D0D7DE] dark:border-[#30363D] bg-white dark:bg-[#161B22] p-3">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="text-sm font-semibold text-slate-900 dark:text-[#C9D1D9] truncate" :title="selectedTrace.name">{{ selectedTrace.name }}</div>
                <div class="text-[11px] text-slate-500 dark:text-[#8B949E] mt-1 break-all">{{ selectedTrace.trace_id }}</div>
              </div>
              <el-tag :type="tagType(selectedTrace.status)" effect="light" size="small">{{ selectedTrace.status }}</el-tag>
            </div>

            <div class="grid grid-cols-2 gap-2 mt-3 text-[12px]">
              <div class="text-slate-500 dark:text-[#8B949E]">开始：<span class="text-slate-800 dark:text-[#C9D1D9]">{{ fmt(selectedTrace.start_time) }}</span></div>
              <div class="text-slate-500 dark:text-[#8B949E]">结束：<span class="text-slate-800 dark:text-[#C9D1D9]">{{ fmt(selectedTrace.end_time) }}</span></div>
              <div class="text-slate-500 dark:text-[#8B949E]">耗时：<span class="text-slate-800 dark:text-[#C9D1D9]">{{ formatDuration(selectedTrace.duration_ms) }}</span></div>
              <div class="text-slate-500 dark:text-[#8B949E]">Spans：<span class="text-slate-800 dark:text-[#C9D1D9]">{{ selectedTrace.total_spans ?? '-' }}</span></div>
            </div>

            <div class="mt-3 flex flex-wrap gap-2">
              <el-button size="small" plain class="cursor-pointer" @click="copyText(selectedTrace.session_id || '')" :disabled="!selectedTrace.session_id">
                复制 session_id
              </el-button>
              <el-button size="small" plain class="cursor-pointer" @click="copyText(selectedTrace.run_id || '')" :disabled="!selectedTrace.run_id">
                复制 run_id
              </el-button>
              <el-button size="small" plain class="cursor-pointer" @click="refreshSelectedTrace" :loading="loadingDetail">
                重新拉取详情
              </el-button>
            </div>
          </div>

          <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div class="rounded-lg border border-[#D0D7DE] dark:border-[#30363D] bg-white dark:bg-[#161B22] p-3 min-h-[280px]">
              <div class="flex items-center justify-between">
                <div class="text-sm font-semibold text-slate-900 dark:text-[#C9D1D9]">Span 树</div>
                <div class="text-[11px] text-slate-500 dark:text-[#8B949E]">{{ spans.length }} spans</div>
              </div>
              <div class="mt-2">
                <el-tree
                  v-if="tree.length"
                  :data="tree"
                  node-key="span.span_id"
                  :expand-on-click-node="false"
                  default-expand-all
                  class="bg-transparent"
                  @node-click="onSpanNodeClick"
                >
                  <template #default="{ data }">
                    <div class="flex items-center gap-2 min-w-0 w-full">
                      <span class="text-xs text-slate-900 dark:text-[#C9D1D9] truncate" :title="data.span.name">{{ data.span.name }}</span>
                      <span class="text-[11px] tabular-nums text-slate-500 dark:text-[#8B949E]">{{ formatDuration(data.span.duration_ms) }}</span>
                      <span
                        class="text-[10px] px-1.5 py-0.5 rounded border"
                        :class="data.span.status_code === 'ERROR'
                          ? 'border-red-300 text-red-700 dark:border-red-700/40 dark:text-red-300'
                          : 'border-[#D0D7DE] text-slate-600 dark:border-[#30363D] dark:text-[#8B949E]'"
                      >
                        {{ data.span.status_code }}
                      </span>
                    </div>
                  </template>
                </el-tree>

                <div v-else class="text-xs text-slate-500 dark:text-[#8B949E] py-8 text-center">暂无 spans</div>
              </div>
            </div>

            <div class="rounded-lg border border-[#D0D7DE] dark:border-[#30363D] bg-white dark:bg-[#161B22] p-3 min-h-[280px]">
              <div class="flex items-center justify-between">
                <div class="text-sm font-semibold text-slate-900 dark:text-[#C9D1D9]">Span 详情</div>
                <el-button size="small" plain class="cursor-pointer" :disabled="!selectedSpan" @click="copySpanJson">
                  复制 JSON
                </el-button>
              </div>

              <div v-if="!selectedSpan" class="text-xs text-slate-500 dark:text-[#8B949E] py-10 text-center">
                点击左侧 Span 节点查看 attributes / 错误信息
              </div>

              <div v-else class="mt-2 space-y-2">
                <div class="text-xs text-slate-500 dark:text-[#8B949E]">名称</div>
                <div class="text-sm font-medium text-slate-900 dark:text-[#C9D1D9] break-words">{{ selectedSpan.name }}</div>

                <div class="grid grid-cols-2 gap-2 text-[12px]">
                  <div class="text-slate-500 dark:text-[#8B949E]">状态：<span class="text-slate-800 dark:text-[#C9D1D9]">{{ selectedSpan.status_code }}</span></div>
                  <div class="text-slate-500 dark:text-[#8B949E]">耗时：<span class="text-slate-800 dark:text-[#C9D1D9]">{{ formatDuration(selectedSpan.duration_ms) }}</span></div>
                </div>

                <div v-if="selectedSpan.status_message" class="rounded-md border border-red-300 dark:border-red-700/40 bg-red-50 dark:bg-red-900/10 p-2">
                  <div class="text-[11px] font-semibold text-red-700 dark:text-red-300">错误信息</div>
                  <div class="text-xs text-red-700 dark:text-red-300 break-words mt-1">{{ selectedSpan.status_message }}</div>
                </div>

                <div class="text-xs text-slate-500 dark:text-[#8B949E] mt-2">attributes</div>
                <pre class="text-[11px] leading-snug overflow-auto rounded-md border border-[#D0D7DE] dark:border-[#30363D] bg-white dark:bg-[#0D1117] p-2 max-h-[260px]">{{ prettyJson(selectedSpan.attributes) }}</pre>
              </div>
            </div>
          </div>
        </div>

        <div v-if="apiError" class="px-4 pb-4">
          <el-alert type="error" :title="apiError" show-icon />
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { ElMessage } from "element-plus"
import { useTracingApi } from "../composables/useApi"
import type { TraceItem, SpanItem, SpanTreeNode, TraceStatus } from "../types"

const { loading, error, listTraces, getTrace } = useTracingApi()

const page = ref(1)
const limit = ref(20)
const totalCount = ref(0)

const traceItems = ref<TraceItem[]>([])

const filters = reactive<{ session_id: string; status: TraceStatus | ""; timeRange: [string, string] | null }>(
  {
    session_id: "",
    status: "",
    timeRange: null,
  }
)

const selectedTrace = ref<TraceItem | null>(null)
const spans = ref<SpanItem[]>([])
const tree = ref<SpanTreeNode[]>([])
const selectedSpan = ref<SpanItem | null>(null)

const loadingDetail = ref(false)
const apiError = computed(() => error.value)

const fmt = (iso: string) => {
  if (!iso) return ""
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

const tagType = (status: string) => {
  if (status === "OK") return "success"
  if (status === "ERROR") return "danger"
  if (status === "UNSET") return "info"
  return "warning"
}

const formatDuration = (durationMs: number | string | null | undefined): string => {
  const n = Number(durationMs)
  if (!Number.isFinite(n) || n < 0) return "-"

  if (n < 1000) {
    if (n < 10) return `${n.toFixed(2)} ms`
    if (n < 100) return `${n.toFixed(1)} ms`
    return `${Math.round(n)} ms`
  }

  const sec = n / 1000
  if (sec < 60) {
    return sec < 10 ? `${sec.toFixed(2)} s` : `${sec.toFixed(1)} s`
  }

  const min = Math.floor(sec / 60)
  const remSec = sec % 60
  if (min < 60) return `${min}m ${remSec.toFixed(1)}s`

  const hour = Math.floor(min / 60)
  const remMin = min % 60
  return `${hour}h ${remMin}m ${Math.round(remSec)}s`
}

const prettyJson = (obj: any) => {
  try {
    if (!obj) return "{}"
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

const refresh = async () => {
  selectedTrace.value = null
  selectedSpan.value = null
  spans.value = []
  tree.value = []

  const [start_time, end_time] = filters.timeRange || ["", ""]
  const resp = await listTraces({
    page: page.value,
    limit: limit.value,
    status: filters.status || "",
    session_id: filters.session_id.trim() || undefined,
    start_time: start_time || undefined,
    end_time: end_time || undefined,
  })

  traceItems.value = resp.items || []
  totalCount.value = resp.total_count || 0
}

const refreshSelectedTrace = async () => {
  if (!selectedTrace.value) return
  loadingDetail.value = true
  try {
    const resp = await getTrace(selectedTrace.value.trace_id)
    selectedTrace.value = resp.trace
    spans.value = resp.spans || []
    tree.value = resp.tree || []
    selectedSpan.value = null
  } finally {
    loadingDetail.value = false
  }
}

const onTraceSelect = async (row: TraceItem | null) => {
  if (!row) return
  selectedTrace.value = row
  selectedSpan.value = null
  spans.value = []
  tree.value = []
  await refreshSelectedTrace()
}

const onSpanNodeClick = (node: SpanTreeNode) => {
  selectedSpan.value = node.span
}

const onPageChange = async (p: number) => {
  page.value = p
  await refresh()
}

const copyText = async (text: string) => {
  const t = (text || "").trim()
  if (!t) return
  try {
    await navigator.clipboard.writeText(t)
    ElMessage.success("已复制")
  } catch {
    ElMessage.warning("复制失败（请检查浏览器权限）")
  }
}

const copySelectedTraceId = async () => {
  if (!selectedTrace.value) return
  await copyText(selectedTrace.value.trace_id)
}

const copySpanJson = async () => {
  if (!selectedSpan.value) return
  await copyText(JSON.stringify(selectedSpan.value, null, 2))
}

watch(
  () => [filters.session_id, filters.status, filters.timeRange],
  () => {
    page.value = 1
  }
)

onMounted(async () => {
  try {
    await refresh()
  } catch (e: any) {
    // prefer showing API error message
    ElMessage.error(e?.message || "加载 traces 失败")
  }
})
</script>

<style scoped>
:deep(.el-tree) {
  background: transparent;
}

:deep(.el-tree-node__content) {
  height: 30px;
}
</style>
