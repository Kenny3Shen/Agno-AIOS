<template>
  <div class="agentos-control">
    <section class="agentos-summary-strip">
      <article
        v-for="metric in payload?.metrics || fallbackMetrics"
        :key="metric.label"
        class="agentos-summary-chip"
        :class="`tone-${metric.tone || 'blue'}`"
      >
        <span>{{ metric.label }}</span>
        <strong :title="metric.hint || metric.label">{{ metric.value }}</strong>
      </article>
    </section>

    <el-alert v-if="error" class="agentos-alert" type="error" :title="error" show-icon />

    <main class="agentos-ledger">
      <section class="agentos-panel">
        <div class="agentos-panel-head">
          <div>
            <p>{{ t("agentOS.ledger.title") }}</p>
            <span>{{ t("agentOS.ledger.count", { count: payload?.records.length || 0, time: generatedAt }) }}</span>
          </div>
          <div class="agentos-panel-actions">
            <span class="agentos-status" :class="payload?.status || 'loading'">
              {{ payload?.status || t("agentOS.status.loading") }}
            </span>
            <el-button size="small" type="primary" :loading="loading" class="cursor-pointer" @click="loadModule">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </div>
        </div>

        <div v-if="payload?.records.length" class="agentos-records">
          <article v-for="record in payload.records" :key="record.id" class="agentos-record">
            <div class="agentos-record-main">
              <span class="agentos-dot" :class="statusTone(record.status)" />
              <div class="min-w-0">
                <strong :title="record.title">{{ record.title }}</strong>
                <p :title="record.subtitle">{{ record.subtitle || record.id }}</p>
              </div>
            </div>

            <div class="agentos-record-side">
              <span class="agentos-chip" :class="statusTone(record.status)">{{ record.status }}</span>
              <small>{{ formatTime(record.updated_at) }}</small>
            </div>

            <div v-if="metaEntries(record).length" class="agentos-meta">
              <span v-for="[key, value] in metaEntries(record)" :key="`${record.id}-${key}`">
                <b>{{ key }}</b>
                {{ compactValue(value) }}
              </span>
            </div>
          </article>
        </div>

        <div v-else-if="!loading" class="agentos-empty">
          <el-icon><Aim /></el-icon>
          <strong>{{ t("agentOS.empty.title") }}</strong>
          <span>{{ emptyMessage }}</span>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import {
  Aim,
  Refresh,
} from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import { useOsControlApi } from "../composables/useApi"
import type { OsControlMetric, OsControlModule, OsControlRecord, OsControlResponse } from "../types"

const props = defineProps<{
  osModule: OsControlModule
}>()

const { loading, error, fetchModule } = useOsControlApi()
const { t, locale } = useI18n()
const payload = ref<OsControlResponse | null>(null)

const fallbackMetrics = computed<OsControlMetric[]>(() => [
  {
    label: t("agentOS.metricFallback.label"),
    value: t("agentOS.metricFallback.value"),
    hint: t("agentOS.metricFallback.hint"),
    tone: "blue",
  },
])
const generatedAt = computed(() => formatTime(payload.value?.generated_at))
const emptyMessage = computed(() => {
  if (props.osModule === "evaluation") return t("agentOS.empty.evaluation")
  if (props.osModule === "approvals") return t("agentOS.empty.approvals")
  if (props.osModule === "scheduler") return t("agentOS.empty.scheduler")
  return t("agentOS.empty.default")
})
const loadModule = async () => {
  payload.value = await fetchModule(props.osModule)
}

const statusTone = (status: string) => {
  const text = status.toLowerCase()
  if (["online", "ready", "enabled", "active", "completed", "stored"].includes(text)) return "green"
  if (["pending", "draft", "idle", "loading"].includes(text)) return "yellow"
  if (["error", "failed", "disabled"].includes(text)) return "red"
  return "blue"
}

const formatTime = (value?: string) => {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(locale.value, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

const compactValue = (value: unknown) => {
  const text = typeof value === "string" ? value : JSON.stringify(value)
  if (!text) return "-"
  if (/^\d{4}-\d{2}-\d{2}T/.test(text)) return formatTime(text)
  return text.length > 48 ? `${text.slice(0, 45)}...` : text
}

const metaEntries = (record: OsControlRecord) => {
  return Object.entries(record.meta || {})
    .filter(([, value]) => value !== "" && value !== false && value != null)
    .slice(0, 6)
}

watch(() => props.osModule, () => {
  void loadModule()
})

onMounted(() => {
  void loadModule()
})
</script>

<style scoped>
.agentos-control {
  --os-bg: #eef3f7;
  --os-panel: #ffffff;
  --os-panel-soft: #f7fafc;
  --os-border: #cfd9e3;
  --os-text: #14202a;
  --os-muted: #637484;
  --os-blue: #147fa2;
  --os-green: #28a66f;
  --os-yellow: #c78624;
  --os-red: #d34a42;
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  background: var(--os-bg);
  color: var(--os-text);
}

.agentos-control :where(div, section, aside, main, article, p, span, strong, small) {
  min-width: 0;
}

.agentos-panel-actions,
.agentos-record-main,
.agentos-record-side {
  display: flex;
  align-items: center;
  gap: 10px;
}

.agentos-panel-head p {
  margin: 0;
  color: var(--os-muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}

.agentos-panel-head span {
  display: block;
  margin-top: 4px;
  color: var(--os-muted);
  font-size: 12px;
  line-height: 1.45;
}

.agentos-status,
.agentos-chip,
.agentos-meta span {
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  border: 1px solid var(--os-border);
  border-radius: 6px;
  background: var(--os-panel-soft);
  padding: 3px 7px;
  color: var(--os-muted);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
  font-weight: 700;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.agentos-summary-strip {
  display: grid;
  flex: 0 0 auto;
  gap: 8px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  padding: 12px 14px 0;
}

.agentos-summary-chip {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--os-border);
  border-radius: 8px;
  background: var(--os-panel-soft);
  padding: 8px 10px;
}

.agentos-summary-chip::before {
  position: absolute;
  inset: 0 auto 0 0;
  width: 2px;
  background: var(--os-blue);
  content: "";
}

.agentos-summary-chip.tone-green::before,
.agentos-dot.green {
  background: var(--os-green);
}

.agentos-summary-chip.tone-yellow::before,
.agentos-dot.yellow {
  background: var(--os-yellow);
}

.agentos-summary-chip.tone-red::before,
.agentos-dot.red {
  background: var(--os-red);
}

.agentos-chip.green,
.agentos-status.green {
  border-color: rgba(40, 166, 111, 0.28);
  background: rgba(40, 166, 111, 0.12);
  color: var(--os-green);
}

.agentos-chip.yellow,
.agentos-status.yellow,
.agentos-status.loading {
  border-color: rgba(199, 134, 36, 0.3);
  background: rgba(199, 134, 36, 0.12);
  color: var(--os-yellow);
}

.agentos-chip.red,
.agentos-status.red {
  border-color: rgba(211, 74, 66, 0.3);
  background: rgba(211, 74, 66, 0.12);
  color: var(--os-red);
}

.agentos-summary-chip span {
  display: block;
  color: var(--os-muted);
  font-size: 10px;
  line-height: 1.35;
}

.agentos-summary-chip strong {
  display: block;
  margin-top: 2px;
  color: var(--os-text);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 13px;
  font-weight: 800;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.agentos-alert {
  margin: 12px 16px 0;
}

.agentos-ledger {
  min-height: 0;
  flex: 1;
  display: block;
  overflow: hidden;
  padding: 14px;
}

.agentos-panel {
  min-height: 0;
  border: 1px solid var(--os-border);
  border-radius: 8px;
  background: var(--os-panel);
  padding: 14px;
}

.agentos-ledger > .agentos-panel {
  display: flex;
  flex-direction: column;
}

.agentos-panel-head {
  display: flex;
  flex: 0 0 auto;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.agentos-records {
  display: grid;
  min-height: 0;
  gap: 8px;
  overflow-y: auto;
  padding-right: 4px;
}

.agentos-record {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px 12px;
  border: 1px solid var(--os-border);
  border-radius: 8px;
  background: var(--os-panel-soft);
  padding: 11px;
}

.agentos-record-main strong {
  display: block;
  color: var(--os-text);
  font-size: 13px;
  font-weight: 800;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agentos-record-main p {
  margin: 3px 0 0;
  color: var(--os-muted);
  font-size: 11px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.agentos-dot {
  width: 9px;
  height: 9px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: var(--os-blue);
  box-shadow: 0 0 0 3px rgba(20, 127, 162, 0.12);
}

.agentos-record-side {
  align-items: flex-end;
  flex-direction: column;
}

.agentos-record-side small {
  color: var(--os-muted);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
}

.agentos-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  grid-column: 1 / -1;
}

.agentos-meta b {
  margin-right: 4px;
  color: var(--os-text);
}

.agentos-empty {
  display: grid;
  width: min(360px, 100%);
  place-items: center;
  justify-self: center;
  margin: auto;
  border: 1px dashed var(--os-border);
  border-radius: 8px;
  background: var(--os-panel-soft);
  padding: 28px;
  text-align: center;
}

.agentos-empty .el-icon {
  color: var(--os-blue);
  font-size: 26px;
}

.agentos-empty strong {
  margin-top: 12px;
  color: var(--os-text);
  font-size: 14px;
}

.agentos-empty span {
  margin-top: 6px;
  color: var(--os-muted);
  font-size: 12px;
  line-height: 1.55;
}

html.dark .agentos-control {
  --os-bg: #15161b;
  --os-panel: #1c1d22;
  --os-panel-soft: #17181d;
  --os-border: #34363d;
  --os-text: #f1f1ec;
  --os-muted: #9a9ba3;
  --os-blue: #6da8ff;
  --os-green: #55d989;
  --os-yellow: #f0bd57;
  --os-red: #ff6f63;
}

@media (max-width: 1180px) {
  .agentos-ledger {
    overflow-y: auto;
  }
}

@media (max-width: 760px) {
  .agentos-control {
    overflow-y: auto;
  }

  .agentos-summary-strip,
  .agentos-ledger {
    padding: 12px;
  }

  .agentos-summary-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .agentos-ledger {
    display: block;
    overflow: visible;
  }

  .agentos-record {
    grid-template-columns: 1fr;
  }

  .agentos-record-side {
    align-items: flex-start;
  }
}
</style>
