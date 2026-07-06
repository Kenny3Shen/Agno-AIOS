<template>
  <div class="agentos-control ag-page-flow">
    <el-alert v-if="error" class="agentos-alert" type="error" :title="error" show-icon />

    <main v-if="props.osModule === 'scheduler'" class="scheduler-workbench">
      <section class="agentos-panel ag-content-panel scheduler-list-panel">
        <div class="agentos-panel-head">
          <div>
            <p>{{ t("agentOS.scheduler.listTitle") }}</p>
            <span>{{ t("agentOS.ledger.count", { count: schedules.length, time: generatedAt }) }}</span>
          </div>
          <div class="agentos-panel-actions">
            <el-button size="small" :loading="loading" @click="loadModule">
              <el-icon><Refresh /></el-icon>
            </el-button>
            <el-button size="small" type="primary" @click="showCreateForm = !showCreateForm">
              <el-icon><Plus /></el-icon>
              {{ t("agentOS.scheduler.create") }}
            </el-button>
          </div>
        </div>

        <section v-if="showCreateForm" class="scheduler-form">
          <div class="agentos-scheduler-grid">
            <el-input v-model="scheduleForm.name" :placeholder="t('agentOS.scheduler.namePlaceholder')" />
            <el-select v-model="scheduleForm.target_type">
              <el-option :label="t('agentOS.scheduler.targets.agent')" value="agent" />
              <el-option :label="t('agentOS.scheduler.targets.team')" value="team" />
              <el-option :label="t('agentOS.scheduler.targets.workflow')" value="workflow" />
            </el-select>
            <el-input v-model="scheduleForm.target_id" :placeholder="targetPlaceholder" />
            <el-input v-model="scheduleForm.cron_expr" placeholder="*/30 * * * *" />
            <el-input v-model="scheduleForm.description" :placeholder="t('agentOS.scheduler.descriptionPlaceholder')" />
            <el-input v-model="scheduleForm.timezone" placeholder="UTC" />
            <el-input-number v-model="scheduleForm.timeout_seconds" :min="1" :max="86400" controls-position="right" class="agentos-number" />
            <div class="scheduler-enabled-field">
              <el-switch v-model="scheduleForm.enabled" :active-text="t('agentOS.scheduler.enabled')" />
            </div>
          </div>
          <el-collapse class="scheduler-advanced">
            <el-collapse-item :title="t('agentOS.scheduler.advanced')" name="advanced">
              <div class="agentos-scheduler-grid compact">
                <el-input-number v-model="scheduleForm.max_retries" :min="0" :max="10" controls-position="right" class="agentos-number" />
                <el-input-number v-model="scheduleForm.retry_delay_seconds" :min="1" :max="3600" controls-position="right" class="agentos-number" />
              </div>
            </el-collapse-item>
          </el-collapse>
          <el-input
            v-model="schedulePayloadJson"
            type="textarea"
            :rows="3"
            class="agentos-scheduler-input"
            :placeholder="t('agentOS.scheduler.inputPlaceholder')"
          />
          <div class="agentos-scheduler-actions">
            <el-button @click="resetCreateForm">{{ t("agentOS.scheduler.reset") }}</el-button>
            <el-button type="primary" :loading="creatingSchedule" @click="submitSchedule">
              <el-icon><Plus /></el-icon>
              {{ t("agentOS.scheduler.create") }}
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
            <span class="agentos-dot" :class="statusTone(schedule.enabled ? 'enabled' : 'disabled')" />
            <span class="schedule-main">
              <strong :title="schedule.name">{{ schedule.name }}</strong>
              <small :title="schedule.endpoint">{{ schedule.endpoint }}</small>
            </span>
            <span class="schedule-side">
              <b>{{ schedule.cron_expr }}</b>
              <small>{{ formatTime(schedule.next_run_at_iso) }}</small>
            </span>
          </button>
        </div>

        <div v-else-if="!loading" class="agentos-empty">
          <el-icon><Aim /></el-icon>
          <strong>{{ t("agentOS.empty.title") }}</strong>
          <span>{{ emptyMessage }}</span>
        </div>
      </section>

      <section class="agentos-panel scheduler-detail-panel ag-right-panel">
        <template v-if="selectedSchedule">
          <div class="agentos-panel-head">
            <div>
              <p>{{ selectedSchedule.name }}</p>
              <span>{{ selectedSchedule.endpoint }}</span>
            </div>
            <div class="agentos-panel-actions">
              <span class="agentos-status" :class="statusTone(selectedSchedule.enabled ? 'enabled' : 'disabled')">
                {{ selectedSchedule.enabled ? t("agentOS.scheduler.enabled") : t("agentOS.scheduler.disabled") }}
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
              <span>{{ t("agentOS.scheduler.namePlaceholder") }}</span>
              <el-input v-model="editForm.name" />
            </label>
            <label>
              <span>{{ t("agentOS.scheduler.targetType") }}</span>
              <el-select v-model="editForm.target_type">
                <el-option :label="t('agentOS.scheduler.targets.agent')" value="agent" />
                <el-option :label="t('agentOS.scheduler.targets.team')" value="team" />
                <el-option :label="t('agentOS.scheduler.targets.workflow')" value="workflow" />
              </el-select>
            </label>
            <label>
              <span>{{ t("agentOS.scheduler.targetPlaceholder") }}</span>
              <el-input v-model="editForm.target_id" />
            </label>
            <label>
              <span>Cron</span>
              <el-input v-model="editForm.cron_expr" />
            </label>
            <label>
              <span>{{ t("agentOS.scheduler.timezone") }}</span>
              <el-input v-model="editForm.timezone" />
            </label>
            <label>
              <span>{{ t("agentOS.scheduler.timeout") }}</span>
              <el-input-number v-model="editForm.timeout_seconds" :min="1" :max="86400" controls-position="right" class="agentos-number" />
            </label>
            <label>
              <span>{{ t("agentOS.scheduler.maxRetries") }}</span>
              <el-input-number v-model="editForm.max_retries" :min="0" :max="10" controls-position="right" class="agentos-number" />
            </label>
            <label>
              <span>{{ t("agentOS.scheduler.retryDelay") }}</span>
              <el-input-number v-model="editForm.retry_delay_seconds" :min="1" :max="3600" controls-position="right" class="agentos-number" />
            </label>
          </div>
          <el-input v-model="editForm.description" :placeholder="t('agentOS.scheduler.descriptionPlaceholder')" />
          <el-input v-model="editPayloadJson" type="textarea" :rows="4" class="agentos-scheduler-input" />
          <div class="agentos-scheduler-actions">
            <el-button @click="loadSelectedIntoEdit">{{ t("agentOS.scheduler.reset") }}</el-button>
            <el-button type="primary" :loading="savingSchedule" @click="saveSelectedSchedule">
              <el-icon><Check /></el-icon>
              {{ t("agentOS.scheduler.save") }}
            </el-button>
          </div>

          <div class="runs-head">
            <div>
              <p>{{ t("agentOS.scheduler.runsTitle") }}</p>
              <span>{{ t("agentOS.scheduler.runsDescription") }}</span>
            </div>
            <el-button size="small" :loading="loadingRuns" @click="loadRuns(selectedSchedule.id)">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </div>
          <div v-if="runs.length" class="run-list">
            <article v-for="run in runs" :key="run.id" class="run-row">
              <span class="agentos-chip" :class="statusTone(run.status)">{{ run.status }}</span>
              <strong>{{ t("agentOS.scheduler.attempt", { attempt: run.attempt }) }}</strong>
              <small>{{ formatTime(run.completed_at_iso || run.triggered_at_iso) }}</small>
              <p v-if="run.error" :title="run.error">{{ run.error }}</p>
            </article>
          </div>
          <div v-else class="agentos-empty compact-empty">
            <strong>{{ t("agentOS.scheduler.noRuns") }}</strong>
          </div>
        </template>

        <div v-else class="agentos-empty">
          <el-icon><Aim /></el-icon>
          <strong>{{ t("agentOS.scheduler.selectTitle") }}</strong>
          <span>{{ t("agentOS.scheduler.selectDescription") }}</span>
        </div>
      </section>
    </main>

    <main v-else-if="props.osModule === 'approvals'" class="approvals-workbench">
      <section class="agentos-panel ag-content-panel approvals-list-panel">
        <div class="agentos-panel-head">
          <div>
            <p>{{ t("agentOS.approvals.listTitle") }}</p>
            <span>{{ t("agentOS.ledger.count", { count: approvals.length, time: generatedAt }) }}</span>
          </div>
          <div class="agentos-panel-actions">
            <el-select v-model="approvalStatusFilter" size="small" class="approval-status-filter" @change="loadModule">
              <el-option :label="t('agentOS.approvals.allStatuses')" value="" />
              <el-option :label="t('agentOS.approvals.statusPending')" value="pending" />
              <el-option :label="t('agentOS.approvals.statusApproved')" value="approved" />
              <el-option :label="t('agentOS.approvals.statusRejected')" value="rejected" />
            </el-select>
            <el-button size="small" type="primary" :loading="loading" class="cursor-pointer" @click="loadModule">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </div>
        </div>

        <div v-if="approvals.length" class="approval-table">
          <button
            v-for="approval in approvals"
            :key="approval.id"
            type="button"
            class="approval-row"
            :class="{ selected: approval.id === selectedApprovalId }"
            @click="selectApproval(approval.id)"
          >
            <span class="agentos-dot" :class="statusTone(approval.status)" />
            <span class="approval-main">
              <strong :title="approval.tool_name || approval.id">{{ approval.tool_name || approval.id }}</strong>
              <small :title="approval.source_name || approval.source_type || ''">
                {{ approval.source_name || approval.source_type || "-" }}
              </small>
            </span>
            <span class="approval-side">
              <b>{{ approval.status }}</b>
              <small>{{ formatTime(approval.updated_at || approval.created_at) }}</small>
            </span>
          </button>
        </div>

        <div v-else-if="!loading" class="agentos-empty">
          <el-icon><Aim /></el-icon>
          <strong>{{ t("agentOS.empty.title") }}</strong>
          <span>{{ emptyMessage }}</span>
        </div>
      </section>

      <section class="agentos-panel approvals-detail-panel ag-right-panel">
        <template v-if="selectedApproval">
          <div class="agentos-panel-head">
            <div>
              <p>{{ selectedApproval.tool_name || t("agentOS.approvals.detailTitle") }}</p>
              <span>{{ selectedApproval.run_id || selectedApproval.session_id || selectedApproval.id }}</span>
            </div>
            <div class="agentos-panel-actions">
              <span class="agentos-status" :class="statusTone(selectedApproval.status)">
                {{ selectedApproval.status }}
              </span>
              <el-button
                v-if="selectedApproval.status === 'pending'"
                size="small"
                type="success"
                :loading="resolvingApproval === 'approved'"
                @click='resolveSelectedApproval("approved")'
              >
                <el-icon><Check /></el-icon>
                {{ t("agentOS.approvals.approve") }}
              </el-button>
              <el-button
                v-if="selectedApproval.status === 'pending'"
                size="small"
                type="danger"
                :loading="resolvingApproval === 'rejected'"
                @click='resolveSelectedApproval("rejected")'
              >
                <el-icon><Delete /></el-icon>
                {{ t("agentOS.approvals.reject") }}
              </el-button>
            </div>
          </div>

          <div class="approval-detail-grid">
            <span><b>Run</b>{{ selectedApproval.run_id || "-" }}</span>
            <span><b>Session</b>{{ selectedApproval.session_id || "-" }}</span>
            <span><b>Source</b>{{ selectedApproval.source_name || selectedApproval.source_type || "-" }}</span>
            <span><b>User</b>{{ selectedApproval.user_id || "-" }}</span>
            <span><b>Agent</b>{{ selectedApproval.agent_id || "-" }}</span>
            <span><b>Run Status</b>{{ selectedApproval.run_status || "-" }}</span>
          </div>

          <section class="approval-json-block">
            <p>{{ t("agentOS.approvals.argsTitle") }}</p>
            <pre>{{ formatJson(selectedApproval.tool_args || {}) }}</pre>
          </section>
          <section class="approval-json-block">
            <p>{{ t("agentOS.approvals.contextTitle") }}</p>
            <pre>{{ formatJson(selectedApproval.context || {}) }}</pre>
          </section>
          <section class="approval-json-block">
            <p>{{ t("agentOS.approvals.requirementsTitle") }}</p>
            <pre>{{ formatJson(selectedApproval.requirements || []) }}</pre>
          </section>
          <section v-if="selectedApproval.resolved_by || selectedApproval.resolution_data" class="approval-json-block">
            <p>{{ t("agentOS.approvals.resolutionTitle") }}</p>
            <pre>{{ formatJson({ resolved_by: selectedApproval.resolved_by, resolved_at: selectedApproval.resolved_at, resolution_data: selectedApproval.resolution_data }) }}</pre>
          </section>
        </template>

        <div v-else class="agentos-empty">
          <el-icon><Aim /></el-icon>
          <strong>{{ t("agentOS.approvals.selectTitle") }}</strong>
          <span>{{ t("agentOS.approvals.selectDescription") }}</span>
        </div>
      </section>
    </main>

    <main v-else class="agentos-ledger">
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
              <small>{{ formatTime(record.updated_at) }}</small>
            </div>

            <div v-if="metaEntries(record).length" class="agentos-meta">
              <span
                v-for="[key, value] in metaEntries(record)"
                :key="`${record.id}-${key}`"
                :class="{ 'is-id': isIdEntry(key, value) }"
              >
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
import { computed, onMounted, reactive, ref, watch } from "vue"
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
import { useOsControlApi } from "../composables/useApi"
import type {
  ApprovalRecord,
  OsControlModule,
  OsControlRecord,
  OsControlResponse,
  ScheduleTargetType,
  SchedulerRun,
  SchedulerSchedule,
} from "../types"

const props = defineProps<{
  osModule: OsControlModule
}>()

const {
  loading,
  error,
  fetchModule,
  listApprovals,
  getApproval,
  resolveApproval,
  createSchedule,
  updateSchedule,
  setScheduleEnabled,
  triggerSchedule,
  deleteSchedule,
  listScheduleRuns,
} = useOsControlApi()
const { t, locale } = useI18n()
const payload = ref<OsControlResponse | null>(null)
const creatingSchedule = ref(false)
const savingSchedule = ref(false)
const loadingRuns = ref(false)
const showCreateForm = ref(false)
const selectedScheduleId = ref("")
const selectedApprovalId = ref("")
const approvalStatusFilter = ref("")
const resolvingApproval = ref<"approved" | "rejected" | "">("")
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

const generatedAt = computed(() => formatTime(payload.value?.generated_at))
const schedules = computed<SchedulerSchedule[]>(() => payload.value?.schedules || [])
const approvals = computed<ApprovalRecord[]>(() => payload.value?.approvals || [])
const selectedSchedule = computed(() => schedules.value.find((schedule) => schedule.id === selectedScheduleId.value) || null)
const selectedApproval = computed(() => approvals.value.find((approval) => approval.id === selectedApprovalId.value) || null)
const emptyMessage = computed(() => {
  if (props.osModule === "evaluation") return t("agentOS.empty.evaluation")
  if (props.osModule === "approvals") return t("agentOS.empty.approvals")
  if (props.osModule === "scheduler") return t("agentOS.empty.scheduler")
  return t("agentOS.empty.default")
})
const targetPlaceholder = computed(() => {
  if (scheduleForm.target_type === "agent") return t("agentOS.scheduler.agentPlaceholder")
  if (scheduleForm.target_type === "team") return t("agentOS.scheduler.teamPlaceholder")
  return t("agentOS.scheduler.workflowPlaceholder")
})

const parsePayloadJson = (value: string) => {
  if (!value.trim()) return {}
  const parsed = JSON.parse(value)
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("invalid")
  return parsed as Record<string, unknown>
}

const loadModule = async () => {
  const nextPayload = props.osModule === "approvals"
    ? await listApprovals({
        status: approvalStatusFilter.value || undefined,
        page: 1,
        limit: 50,
      })
    : await fetchModule(props.osModule)
  payload.value = nextPayload
  if (props.osModule === "approvals") {
    const stillSelected = approvals.value.some((approval) => approval.id === selectedApprovalId.value)
    if (!stillSelected) {
      selectedApprovalId.value = approvals.value[0]?.id || ""
    }
    return
  }
  if (props.osModule !== "scheduler") return
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
  if (props.osModule !== "scheduler") return
  if (!scheduleForm.name.trim() || !scheduleForm.target_id.trim() || !scheduleForm.cron_expr.trim()) {
    ElMessage.warning(t("agentOS.scheduler.required"))
    return
  }
  let payloadJson: Record<string, unknown>
  try {
    payloadJson = parsePayloadJson(schedulePayloadJson.value)
  } catch {
    ElMessage.warning(t("agentOS.scheduler.invalidInput"))
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
    ElMessage.success(t("agentOS.scheduler.created"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("agentOS.scheduler.createFailed"))
  } finally {
    creatingSchedule.value = false
  }
}

const selectSchedule = async (id: string) => {
  selectedScheduleId.value = id
  loadSelectedIntoEdit()
  await loadRuns(id)
}

const selectApproval = async (id: string) => {
  selectedApprovalId.value = id
  try {
    const detail = await getApproval(id)
    const current = approvals.value
    const index = current.findIndex((approval) => approval.id === id)
    if (!payload.value || index < 0) return
    const nextApprovals = [...current]
    nextApprovals[index] = detail
    payload.value = { ...payload.value, approvals: nextApprovals }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("agentOS.approvals.loadFailed"))
  }
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
    ElMessage.warning(t("agentOS.scheduler.invalidInput"))
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
    ElMessage.success(t("agentOS.scheduler.saved"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("agentOS.scheduler.saveFailed"))
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
    ElMessage.success(t("agentOS.scheduler.triggered"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("agentOS.scheduler.triggerFailed"))
  }
}

const deleteSelectedSchedule = async () => {
  const schedule = selectedSchedule.value
  if (!schedule) return
  await deleteSchedule(schedule.id)
  selectedScheduleId.value = ""
  await loadModule()
}

const resolveSelectedApproval = async (status: "approved" | "rejected") => {
  const approval = selectedApproval.value
  if (!approval) return
  resolvingApproval.value = status
  try {
    const resolved = await resolveApproval(approval.id, { status })
    const current = approvals.value
    const index = current.findIndex((item) => item.id === approval.id)
    if (payload.value && index >= 0) {
      const nextApprovals = [...current]
      nextApprovals[index] = resolved
      payload.value = { ...payload.value, approvals: nextApprovals }
    }
    await loadModule()
    if (approvals.value.some((item) => item.id === resolved.id)) {
      selectedApprovalId.value = resolved.id
    }
    ElMessage.success(
      status === "approved"
        ? t("agentOS.approvals.approved")
        : t("agentOS.approvals.rejected")
    )
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("agentOS.approvals.resolveFailed"))
  } finally {
    resolvingApproval.value = ""
  }
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

const statusTone = (status: string) => {
  const text = status.toLowerCase()
  if (["online", "ready", "enabled", "active", "completed", "stored", "success", "approved"].includes(text)) return "green"
  if (["pending", "draft", "idle", "loading", "running", "paused"].includes(text)) return "yellow"
  if (["error", "failed", "disabled", "cancelled", "timeout", "rejected"].includes(text)) return "red"
  return "blue"
}

const formatTime = (value?: string | number | null) => {
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

const formatJson = (value: unknown) => {
  try {
    return JSON.stringify(value ?? {}, null, 2)
  } catch {
    return String(value ?? "")
  }
}

const isIdEntry = (key: string, value: unknown) => {
  if (value == null || value === "") return false
  return key.toLowerCase().endsWith("id") || key.toLowerCase().includes("_id")
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
  color: var(--os-text);
}

.agentos-control :where(div, section, aside, main, article, p, span, strong, small, button, label) {
  min-width: 0;
}

.agentos-panel-actions,
.agentos-record-main,
.agentos-record-side,
.runs-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.agentos-panel-head p,
.runs-head p {
  margin: 0;
  color: var(--os-muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}

.agentos-panel-head span,
.runs-head span {
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

.agentos-dot.green {
  background: var(--os-green);
}

.agentos-dot.yellow {
  background: var(--os-yellow);
}

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

.agentos-alert {
  margin: 12px 16px 0;
}

.scheduler-workbench {
  min-height: 0;
  flex: 1;
  display: grid;
  overflow: hidden;
}

.scheduler-workbench,
.approvals-workbench {
  gap: 12px;
  grid-template-columns: minmax(360px, 0.95fr) minmax(420px, 1.05fr);
}

.approvals-workbench {
  min-height: 0;
  flex: 1;
  display: grid;
  overflow: hidden;
}

.agentos-ledger {
  display: block;
  flex: 0 0 auto;
  min-height: 0;
  overflow: visible;
}

.agentos-panel {
  min-height: 0;
  overflow: hidden;
}

.agentos-ledger > .agentos-panel,
.scheduler-list-panel,
.scheduler-detail-panel,
.approvals-list-panel,
.approvals-detail-panel {
  display: flex;
  flex-direction: column;
}

.agentos-ledger > .agentos-panel {
  width: fit-content;
  min-width: min(260px, 100%);
  max-width: min(720px, 100%);
  max-height: min(720px, calc(100dvh - 180px));
}

.agentos-panel-head,
.runs-head {
  display: flex;
  flex: 0 0 auto;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.scheduler-form {
  flex: 0 0 auto;
  margin-bottom: 10px;
  border-bottom: 1px solid var(--os-border);
  padding-bottom: 12px;
}

.agentos-scheduler-grid,
.scheduler-detail-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.agentos-scheduler-grid.compact {
  grid-template-columns: repeat(2, minmax(0, 180px));
}

.scheduler-detail-grid label {
  display: grid;
  gap: 4px;
}

.scheduler-detail-grid label > span {
  color: var(--os-muted);
  font-size: 11px;
  font-weight: 700;
}

.agentos-number {
  width: 100%;
}

.scheduler-enabled-field {
  display: flex;
  min-width: 0;
  min-height: 32px;
  align-items: center;
  justify-content: flex-start;
  overflow: hidden;
}

.scheduler-enabled-field :deep(.el-switch) {
  flex: 0 0 auto;
  max-width: 100%;
  min-width: 0;
}

.scheduler-enabled-field :deep(.el-switch__core) {
  min-width: 40px;
}

.scheduler-enabled-field :deep(.el-switch__label) {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agentos-scheduler-input,
.scheduler-advanced {
  margin-top: 8px;
}

.agentos-scheduler-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
}

.schedule-table,
.approval-table,
.agentos-records,
.run-list {
  display: grid;
  min-height: 0;
  flex: 1 1 auto;
  align-content: start;
  gap: 8px;
  overflow-y: auto;
  padding-right: 4px;
}

.schedule-row {
  display: grid;
  width: 100%;
  grid-template-columns: auto minmax(0, 1fr) minmax(120px, auto);
  align-items: center;
  gap: 10px;
  border: 1px solid var(--os-border);
  border-radius: 8px;
  background: var(--os-panel-soft);
  padding: 10px;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.approval-row {
  display: grid;
  width: 100%;
  grid-template-columns: auto minmax(0, 1fr) minmax(116px, auto);
  align-items: center;
  gap: 10px;
  border: 1px solid var(--os-border);
  border-radius: 8px;
  background: var(--os-panel-soft);
  padding: 10px;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.approval-row.selected {
  border-color: color-mix(in srgb, var(--os-blue) 48%, var(--os-border));
  background: color-mix(in srgb, var(--os-blue) 8%, var(--os-panel));
}

.schedule-row.selected {
  border-color: color-mix(in srgb, var(--os-blue) 48%, var(--os-border));
  background: color-mix(in srgb, var(--os-blue) 8%, var(--os-panel));
}

.schedule-main strong,
.approval-main strong,
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

.schedule-main small,
.approval-main small,
.schedule-side small,
.approval-side small,
.agentos-record-main p,
.run-row small,
.run-row p {
  color: var(--os-muted);
  font-size: 11px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.schedule-side {
  display: grid;
  justify-items: end;
  gap: 3px;
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
}

.approval-side {
  display: grid;
  justify-items: end;
  gap: 3px;
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
}

.approval-side b {
  color: var(--os-text);
}

.approval-status-filter {
  width: 152px;
}

.approval-detail-grid {
  display: grid;
  flex: 0 0 auto;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.approval-detail-grid span {
  display: grid;
  gap: 3px;
  border: 1px solid var(--os-border);
  border-radius: 8px;
  background: var(--os-panel-soft);
  padding: 8px;
  color: var(--os-muted);
  font-size: 11px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.approval-detail-grid b,
.approval-json-block p {
  color: var(--os-text);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}

.approval-json-block {
  display: grid;
  min-height: 0;
  gap: 6px;
  margin-top: 10px;
}

.approval-json-block p {
  margin: 0;
}

.approval-json-block pre {
  max-height: 180px;
  margin: 0;
  overflow: auto;
  border: 1px solid var(--os-border);
  border-radius: 8px;
  background: var(--os-panel-soft);
  padding: 10px;
  color: var(--os-text);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.schedule-side b {
  color: var(--os-text);
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

.agentos-id-chip {
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  border: 1px solid color-mix(in srgb, var(--os-blue) 28%, var(--os-border));
  border-radius: 6px;
  background: color-mix(in srgb, var(--os-blue) 8%, var(--os-panel-soft));
  padding: 2px 6px;
  color: var(--os-text);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
  font-weight: 750;
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

.agentos-meta span.is-id {
  border-color: color-mix(in srgb, var(--os-blue) 32%, var(--os-border));
  background: color-mix(in srgb, var(--os-blue) 9%, var(--os-panel-soft));
  color: var(--os-text);
}

.run-list {
  flex: 0 1 220px;
  margin-top: 8px;
}

.run-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  border: 1px solid var(--os-border);
  border-radius: 8px;
  background: var(--os-panel-soft);
  padding: 9px;
}

.run-row p {
  grid-column: 1 / -1;
  margin: 0;
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

.compact-empty {
  min-height: 72px;
  padding: 16px;
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
  .scheduler-workbench,
  .approvals-workbench {
    grid-template-columns: 1fr;
    overflow-y: auto;
  }
}

@media (max-width: 760px) {
  .agentos-control {
    overflow-y: auto;
  }

  .agentos-scheduler-grid,
  .scheduler-detail-grid,
  .approval-detail-grid {
    grid-template-columns: 1fr;
  }

  .agentos-ledger {
    display: block;
    overflow: visible;
  }

  .agentos-record,
  .schedule-row,
  .approval-row,
  .run-row {
    grid-template-columns: 1fr;
  }

  .schedule-side,
  .approval-side,
  .agentos-record-side {
    align-items: flex-start;
    justify-items: start;
  }
}
</style>
