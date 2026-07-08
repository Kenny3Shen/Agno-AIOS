<template>
  <el-alert v-if="error" class="page-alert" type="error" :title="error" show-icon />

  <main :class="['page-workbench scheduler-workbench', attrs.class]">
    <section class="page-panel ag-content-panel scheduler-list-panel">
      <div class="page-panel-head">
        <div>
          <p>{{ t("workbench.scheduler.listTitle") }}</p>
          <span>{{ t("workbench.records.count", { count: schedules.length, time: generatedAt }) }}</span>
        </div>
        <div class="page-panel-actions">
          <el-button size="small" :loading="loading" @click="loadModule">
            <el-icon><Refresh /></el-icon>
          </el-button>
          <el-button size="small" type="primary" @click="showCreateForm = !showCreateForm">
            <el-icon><Plus /></el-icon>
            {{ t("workbench.scheduler.create") }}
          </el-button>
        </div>
      </div>

      <section v-if="showCreateForm" class="scheduler-form">
        <div class="page-scheduler-grid">
          <el-input v-model="scheduleForm.name" :placeholder="t('workbench.scheduler.namePlaceholder')" />
          <el-select v-model="scheduleForm.target_type">
            <el-option :label="t('workbench.scheduler.targets.agent')" value="agent" />
            <el-option :label="t('workbench.scheduler.targets.team')" value="team" />
            <el-option :label="t('workbench.scheduler.targets.workflow')" value="workflow" />
          </el-select>
          <el-input v-model="scheduleForm.target_id" :placeholder="targetPlaceholder" />
          <el-input v-model="scheduleForm.cron_expr" placeholder="*/30 * * * *" />
          <el-input v-model="scheduleForm.description" :placeholder="t('workbench.scheduler.descriptionPlaceholder')" />
          <el-input v-model="scheduleForm.timezone" placeholder="UTC" />
          <el-input-number v-model="scheduleForm.timeout_seconds" :min="1" :max="86400" controls-position="right" class="page-number" />
          <div class="scheduler-enabled-field">
            <el-switch v-model="scheduleForm.enabled" :active-text="t('workbench.scheduler.enabled')" />
          </div>
        </div>
        <el-collapse class="scheduler-advanced">
          <el-collapse-item :title="t('workbench.scheduler.advanced')" name="advanced">
            <div class="page-scheduler-grid compact">
              <el-input-number v-model="scheduleForm.max_retries" :min="0" :max="10" controls-position="right" class="page-number" />
              <el-input-number v-model="scheduleForm.retry_delay_seconds" :min="1" :max="3600" controls-position="right" class="page-number" />
            </div>
          </el-collapse-item>
        </el-collapse>
        <el-input
          v-model="schedulePayloadJson"
          type="textarea"
          :rows="3"
          class="page-scheduler-input"
          :placeholder="t('workbench.scheduler.inputPlaceholder')"
        />
        <div class="page-scheduler-actions">
          <el-button @click="resetCreateForm">{{ t("workbench.scheduler.reset") }}</el-button>
          <el-button type="primary" :loading="creatingSchedule" @click="submitSchedule">
            <el-icon><Plus /></el-icon>
            {{ t("workbench.scheduler.create") }}
          </el-button>
        </div>
      </section>

      <div v-if="schedules.length" class="schedule-table">
        <button
          v-for="schedule in schedules"
          :key="schedule.id"
          type="button"
          class="schedule-row"
          :class="{ selected: schedule.id === selectedScheduleId }"
          @click="selectSchedule(schedule.id)"
        >
          <span class="page-dot" :class="statusTone(schedule.enabled ? 'enabled' : 'disabled')" />
          <span class="schedule-main">
            <strong :title="schedule.name">{{ schedule.name }}</strong>
            <small :title="schedule.endpoint">{{ schedule.endpoint }}</small>
          </span>
          <span class="schedule-side">
            <b>{{ schedule.cron_expr }}</b>
            <small>{{ formatTime(schedule.next_run_at_iso, locale) }}</small>
          </span>
        </button>
      </div>

      <div v-else-if="!loading" class="page-empty">
        <el-icon><Aim /></el-icon>
        <strong>{{ t("workbench.empty.title") }}</strong>
        <span>{{ t("workbench.empty.scheduler") }}</span>
      </div>
    </section>

    <section class="page-panel scheduler-detail-panel ag-right-panel">
      <template v-if="selectedSchedule">
        <div class="page-panel-head">
          <div>
            <p>{{ selectedSchedule.name }}</p>
            <span>{{ selectedSchedule.endpoint }}</span>
          </div>
          <div class="page-panel-actions">
            <span class="page-status" :class="statusTone(selectedSchedule.enabled ? 'enabled' : 'disabled')">
              {{ selectedSchedule.enabled ? t("workbench.scheduler.enabled") : t("workbench.scheduler.disabled") }}
            </span>
            <el-button size="small" :loading="loading" @click="toggleSelectedSchedule">
              <el-icon><SwitchButton /></el-icon>
            </el-button>
            <el-button size="small" type="primary" :loading="loading" @click="triggerSelectedSchedule">
              <el-icon><VideoPlay /></el-icon>
            </el-button>
            <el-button size="small" type="danger" :loading="loading" @click="deleteSelectedSchedule">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </div>

        <div class="scheduler-detail-grid">
          <label>
            <span>{{ t("workbench.scheduler.namePlaceholder") }}</span>
            <el-input v-model="editForm.name" />
          </label>
          <label>
            <span>{{ t("workbench.scheduler.targetType") }}</span>
            <el-select v-model="editForm.target_type">
              <el-option :label="t('workbench.scheduler.targets.agent')" value="agent" />
              <el-option :label="t('workbench.scheduler.targets.team')" value="team" />
              <el-option :label="t('workbench.scheduler.targets.workflow')" value="workflow" />
            </el-select>
          </label>
          <label>
            <span>{{ t("workbench.scheduler.targetPlaceholder") }}</span>
            <el-input v-model="editForm.target_id" />
          </label>
          <label>
            <span>{{ t("workbench.scheduler.cronLabel") }}</span>
            <el-input v-model="editForm.cron_expr" />
          </label>
          <label>
            <span>{{ t("workbench.scheduler.timezone") }}</span>
            <el-input v-model="editForm.timezone" />
          </label>
          <label>
            <span>{{ t("workbench.scheduler.timeout") }}</span>
            <el-input-number v-model="editForm.timeout_seconds" :min="1" :max="86400" controls-position="right" class="page-number" />
          </label>
          <label>
            <span>{{ t("workbench.scheduler.maxRetries") }}</span>
            <el-input-number v-model="editForm.max_retries" :min="0" :max="10" controls-position="right" class="page-number" />
          </label>
          <label>
            <span>{{ t("workbench.scheduler.retryDelay") }}</span>
            <el-input-number v-model="editForm.retry_delay_seconds" :min="1" :max="3600" controls-position="right" class="page-number" />
          </label>
        </div>
        <el-input v-model="editForm.description" :placeholder="t('workbench.scheduler.descriptionPlaceholder')" />
        <el-input v-model="editPayloadJson" type="textarea" :rows="4" class="page-scheduler-input" />
        <div class="page-scheduler-actions">
          <el-button @click="loadSelectedIntoEdit">{{ t("workbench.scheduler.reset") }}</el-button>
          <el-button type="primary" :loading="savingSchedule" @click="saveSelectedSchedule">
            <el-icon><Check /></el-icon>
            {{ t("workbench.scheduler.save") }}
          </el-button>
        </div>

        <div class="runs-head">
          <div>
            <p>{{ t("workbench.scheduler.runsTitle") }}</p>
            <span>{{ t("workbench.scheduler.runsDescription") }}</span>
          </div>
          <el-button size="small" :loading="loadingRuns" @click="loadRuns(selectedSchedule.id)">
            <el-icon><Refresh /></el-icon>
          </el-button>
        </div>
        <div v-if="runs.length" class="run-list">
          <article v-for="run in runs" :key="run.id" class="run-row">
            <span class="page-chip" :class="statusTone(run.status)">{{ run.status }}</span>
            <strong>{{ t("workbench.scheduler.attempt", { attempt: run.attempt }) }}</strong>
            <small>{{ formatTime(run.completed_at_iso || run.triggered_at_iso, locale) }}</small>
            <p v-if="run.error" :title="run.error">{{ run.error }}</p>
          </article>
        </div>
        <div v-else class="page-empty compact-empty">
          <strong>{{ t("workbench.scheduler.noRuns") }}</strong>
        </div>
      </template>

      <div v-else class="page-empty">
        <el-icon><Aim /></el-icon>
        <strong>{{ t("workbench.scheduler.selectTitle") }}</strong>
        <span>{{ t("workbench.scheduler.selectDescription") }}</span>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, useAttrs } from "vue"
import {
  Aim,
  Check,
  Delete,
  Plus,
  Refresh,
  SwitchButton,
  VideoPlay,
} from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import { useSchedulerApi } from "../composables/useSchedulerApi"
import type {
  ScheduleTargetType,
  SchedulerPayloadResponse,
  SchedulerRun,
  SchedulerSchedule,
} from "../types"
import { formatTime, parsePayloadJson, statusTone } from "../modules/pagePayloadFormat"

defineOptions({ inheritAttrs: false })
defineProps<{
  currentUserId?: string | null
  currentUserInitials?: string | null
}>()

const attrs = useAttrs()
const { t, locale } = useI18n()
const {
  loading,
  error,
  fetchSchedules,
  createSchedule,
  updateSchedule,
  setScheduleEnabled,
  triggerSchedule,
  deleteSchedule,
  listScheduleRuns,
} = useSchedulerApi()

const payload = ref<SchedulerPayloadResponse | null>(null)
const creatingSchedule = ref(false)
const savingSchedule = ref(false)
const loadingRuns = ref(false)
const showCreateForm = ref(false)
const selectedScheduleId = ref("")
const runs = ref<SchedulerRun[]>([])
const schedulePayloadJson = ref("{}")
const editPayloadJson = ref("{}")

const scheduleForm = reactive({
  name: "",
  target_type: "workflow" as ScheduleTargetType,
  target_id: "",
  cron_expr: "",
  description: "",
  timezone: "UTC",
  timeout_seconds: 3600,
  max_retries: 0,
  retry_delay_seconds: 60,
  enabled: true,
})

const editForm = reactive({
  name: "",
  target_type: "workflow" as ScheduleTargetType,
  target_id: "",
  cron_expr: "",
  description: "",
  timezone: "UTC",
  timeout_seconds: 3600,
  max_retries: 0,
  retry_delay_seconds: 60,
})

const generatedAt = computed(() => formatTime(payload.value?.generated_at, locale.value))
const schedules = computed<SchedulerSchedule[]>(() => payload.value?.schedules || [])
const selectedSchedule = computed(() => schedules.value.find((schedule) => schedule.id === selectedScheduleId.value) || null)
const targetPlaceholder = computed(() => {
  if (scheduleForm.target_type === "agent") return t("workbench.scheduler.agentPlaceholder")
  if (scheduleForm.target_type === "team") return t("workbench.scheduler.teamPlaceholder")
  return t("workbench.scheduler.workflowPlaceholder")
})

const loadModule = async () => {
  payload.value = await fetchSchedules()
  const stillSelected = schedules.value.some((schedule) => schedule.id === selectedScheduleId.value)
  if (!stillSelected) {
    selectedScheduleId.value = schedules.value[0]?.id || ""
  }
  if (selectedSchedule.value) {
    loadSelectedIntoEdit()
    await loadRuns(selectedSchedule.value.id)
  } else {
    runs.value = []
    showCreateForm.value = true
  }
}

const resetCreateForm = () => {
  scheduleForm.name = ""
  scheduleForm.target_type = "workflow"
  scheduleForm.target_id = ""
  scheduleForm.cron_expr = ""
  scheduleForm.description = ""
  scheduleForm.timezone = "UTC"
  scheduleForm.timeout_seconds = 3600
  scheduleForm.max_retries = 0
  scheduleForm.retry_delay_seconds = 60
  scheduleForm.enabled = true
  schedulePayloadJson.value = "{}"
}

const submitSchedule = async () => {
  if (!scheduleForm.name.trim() || !scheduleForm.target_id.trim() || !scheduleForm.cron_expr.trim()) {
    ElMessage.warning(t("workbench.scheduler.required"))
    return
  }
  let payloadJson: Record<string, unknown>
  try {
    payloadJson = parsePayloadJson(schedulePayloadJson.value)
  } catch {
    ElMessage.warning(t("workbench.scheduler.invalidInput"))
    return
  }
  creatingSchedule.value = true
  try {
    const created = await createSchedule({
      name: scheduleForm.name.trim(),
      target_type: scheduleForm.target_type,
      target_id: scheduleForm.target_id.trim(),
      cron_expr: scheduleForm.cron_expr.trim(),
      description: scheduleForm.description.trim(),
      timezone: scheduleForm.timezone.trim() || "UTC",
      timeout_seconds: scheduleForm.timeout_seconds,
      max_retries: scheduleForm.max_retries,
      retry_delay_seconds: scheduleForm.retry_delay_seconds,
      enabled: scheduleForm.enabled,
      payload: payloadJson,
    })
    selectedScheduleId.value = created.id
    resetCreateForm()
    showCreateForm.value = false
    await loadModule()
    ElMessage.success(t("workbench.scheduler.created"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("workbench.scheduler.createFailed"))
  } finally {
    creatingSchedule.value = false
  }
}

const selectSchedule = async (id: string) => {
  selectedScheduleId.value = id
  loadSelectedIntoEdit()
  await loadRuns(id)
}

const loadSelectedIntoEdit = () => {
  const schedule = selectedSchedule.value
  if (!schedule) return
  editForm.name = schedule.name
  editForm.target_type = schedule.target_type || "workflow"
  editForm.target_id = schedule.target_id
  editForm.cron_expr = schedule.cron_expr
  editForm.description = schedule.description || ""
  editForm.timezone = schedule.timezone || "UTC"
  editForm.timeout_seconds = schedule.timeout_seconds || 3600
  editForm.max_retries = schedule.max_retries || 0
  editForm.retry_delay_seconds = schedule.retry_delay_seconds || 60
  editPayloadJson.value = JSON.stringify(schedule.payload || {}, null, 2)
}

const saveSelectedSchedule = async () => {
  const schedule = selectedSchedule.value
  if (!schedule) return
  let payloadJson: Record<string, unknown>
  try {
    payloadJson = parsePayloadJson(editPayloadJson.value)
  } catch {
    ElMessage.warning(t("workbench.scheduler.invalidInput"))
    return
  }
  savingSchedule.value = true
  try {
    await updateSchedule(schedule.id, {
      name: editForm.name.trim(),
      target_type: editForm.target_type,
      target_id: editForm.target_id.trim(),
      cron_expr: editForm.cron_expr.trim(),
      description: editForm.description.trim(),
      timezone: editForm.timezone.trim() || "UTC",
      timeout_seconds: editForm.timeout_seconds,
      max_retries: editForm.max_retries,
      retry_delay_seconds: editForm.retry_delay_seconds,
      payload: payloadJson,
    })
    await loadModule()
    ElMessage.success(t("workbench.scheduler.saved"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("workbench.scheduler.saveFailed"))
  } finally {
    savingSchedule.value = false
  }
}

const toggleSelectedSchedule = async () => {
  const schedule = selectedSchedule.value
  if (!schedule) return
  await setScheduleEnabled(schedule.id, !schedule.enabled)
  await loadModule()
}

const triggerSelectedSchedule = async () => {
  const schedule = selectedSchedule.value
  if (!schedule) return
  try {
    await triggerSchedule(schedule.id)
    await loadRuns(schedule.id)
    ElMessage.success(t("workbench.scheduler.triggered"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("workbench.scheduler.triggerFailed"))
  }
}

const deleteSelectedSchedule = async () => {
  const schedule = selectedSchedule.value
  if (!schedule) return
  await deleteSchedule(schedule.id)
  selectedScheduleId.value = ""
  await loadModule()
}

const loadRuns = async (id: string) => {
  loadingRuns.value = true
  try {
    const response = await listScheduleRuns(id)
    runs.value = response.items
  } finally {
    loadingRuns.value = false
  }
}

onMounted(() => {
  void loadModule()
})
</script>

<style src="../styles/page-workbench.css"></style>
