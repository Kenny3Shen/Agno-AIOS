<template>
  <el-alert v-if="error" class="agentos-alert" type="error" :title="error" show-icon />

  <main class="agentos-ledger">
    <section class="agentos-panel ag-content-panel">
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
              <p :title="record.subtitle">
                <span class="agentos-id-chip">{{ record.subtitle || record.id }}</span>
              </p>
            </div>
          </div>

          <div class="agentos-record-side">
            <span class="agentos-chip" :class="statusTone(record.status)">{{ record.status }}</span>
            <small>{{ formatTime(record.updated_at, locale) }}</small>
          </div>

          <div v-if="metaEntries(record).length" class="agentos-meta">
            <span
              v-for="[key, value] in metaEntries(record)"
              :key="`${record.id}-${key}`"
              :class="{ 'is-id': isIdEntry(key, value) }"
            >
              <b>{{ key }}</b>
              {{ compactValue(value, locale) }}
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
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { Aim, Refresh } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import { type ControlPlanePayloadModule, useControlPlaneApi } from "../../composables/useControlPlaneApi"
import type { OsControlResponse } from "../../types"
import { compactValue, formatTime, isIdEntry, metaEntries, statusTone } from "./agentosFormat"

const props = defineProps<{
  osModule: ControlPlanePayloadModule
}>()

const { t, locale } = useI18n()
const { loading, error, fetchModule } = useControlPlaneApi()
const payload = ref<OsControlResponse | null>(null)

const generatedAt = computed(() => formatTime(payload.value?.generated_at, locale.value))
const emptyMessage = computed(() => {
  if (props.osModule === "evaluation") return t("agentOS.empty.evaluation")
  return t("agentOS.empty.default")
})

const loadModule = async () => {
  payload.value = await fetchModule(props.osModule)
}

watch(() => props.osModule, () => {
  void loadModule()
})

onMounted(() => {
  void loadModule()
})
</script>
