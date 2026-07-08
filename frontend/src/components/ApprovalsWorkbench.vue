<template>
  <el-alert v-if="error" class="page-alert" type="error" :title="error" show-icon />

  <main :class="['page-workbench approvals-workbench', attrs.class]">
    <section class="page-panel ag-content-panel approvals-list-panel">
      <div class="page-panel-head">
        <div>
          <p>{{ t("workbench.approvals.listTitle") }}</p>
          <span>{{ t("workbench.records.count", { count: approvals.length, time: generatedAt }) }}</span>
        </div>
        <div class="page-panel-actions">
          <el-select v-model="approvalStatusFilter" size="small" class="approval-status-filter" @change="loadModule">
            <el-option :label="t('workbench.approvals.allStatuses')" value="" />
            <el-option :label="t('workbench.approvals.statusPending')" value="pending" />
            <el-option :label="t('workbench.approvals.statusApproved')" value="approved" />
            <el-option :label="t('workbench.approvals.statusRejected')" value="rejected" />
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
          <span class="page-dot" :class="statusTone(approval.status)" />
          <span class="approval-main">
            <strong :title="approval.tool_name || approval.id">{{ approval.tool_name || approval.id }}</strong>
            <small :title="approval.source_name || approval.source_type || ''">
              {{ approval.source_name || approval.source_type || "-" }}
            </small>
          </span>
          <span class="approval-side">
            <b>{{ approval.status }}</b>
            <small>{{ formatTime(approval.updated_at || approval.created_at, locale) }}</small>
          </span>
        </button>
      </div>

      <div v-else-if="!loading" class="page-empty">
        <el-icon><Aim /></el-icon>
        <strong>{{ t("workbench.empty.title") }}</strong>
        <span>{{ t("workbench.empty.approvals") }}</span>
      </div>
    </section>

    <section class="page-panel approvals-detail-panel ag-right-panel">
      <template v-if="selectedApproval">
        <div class="page-panel-head">
          <div>
            <p>{{ selectedApproval.tool_name || t("workbench.approvals.detailTitle") }}</p>
            <span>{{ selectedApproval.run_id || selectedApproval.session_id || selectedApproval.id }}</span>
          </div>
          <div class="page-panel-actions">
            <span class="page-status" :class="statusTone(selectedApproval.status)">
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
              {{ t("workbench.approvals.approve") }}
            </el-button>
            <el-button
              v-if="selectedApproval.status === 'pending'"
              size="small"
              type="danger"
              :loading="resolvingApproval === 'rejected'"
              @click='resolveSelectedApproval("rejected")'
            >
              <el-icon><Delete /></el-icon>
              {{ t("workbench.approvals.reject") }}
            </el-button>
          </div>
        </div>

        <div class="approval-detail-grid">
          <span><b>{{ t("workbench.approvals.runLabel") }}</b>{{ selectedApproval.run_id || "-" }}</span>
          <span><b>{{ t("workbench.approvals.sessionLabel") }}</b>{{ selectedApproval.session_id || "-" }}</span>
          <span><b>{{ t("workbench.approvals.sourceLabel") }}</b>{{ selectedApproval.source_name || selectedApproval.source_type || "-" }}</span>
          <span><b>{{ t("workbench.approvals.userLabel") }}</b>{{ selectedApproval.user_id || "-" }}</span>
          <span><b>{{ t("workbench.approvals.agentLabel") }}</b>{{ selectedApproval.agent_id || "-" }}</span>
          <span><b>{{ t("workbench.approvals.runStatusLabel") }}</b>{{ selectedApproval.run_status || "-" }}</span>
        </div>

        <section class="approval-json-block">
          <p>{{ t("workbench.approvals.argsTitle") }}</p>
          <pre>{{ formatJson(selectedApproval.tool_args || {}) }}</pre>
        </section>
        <section class="approval-json-block">
          <p>{{ t("workbench.approvals.contextTitle") }}</p>
          <pre>{{ formatJson(selectedApproval.context || {}) }}</pre>
        </section>
        <section class="approval-json-block">
          <p>{{ t("workbench.approvals.requirementsTitle") }}</p>
          <pre>{{ formatJson(selectedApproval.requirements || []) }}</pre>
        </section>
        <section v-if="selectedApproval.resolved_by || selectedApproval.resolution_data" class="approval-json-block">
          <p>{{ t("workbench.approvals.resolutionTitle") }}</p>
          <pre>{{ formatJson({ resolved_by: selectedApproval.resolved_by, resolved_at: selectedApproval.resolved_at, resolution_data: selectedApproval.resolution_data }) }}</pre>
        </section>
      </template>

      <div v-else class="page-empty">
        <el-icon><Aim /></el-icon>
        <strong>{{ t("workbench.approvals.selectTitle") }}</strong>
        <span>{{ t("workbench.approvals.selectDescription") }}</span>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, useAttrs } from "vue"
import { Aim, Check, Delete, Refresh } from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import { useApprovalsApi } from "../composables/useApprovalsApi"
import type { ApprovalListResponse, ApprovalRecord } from "../types"
import { formatJson, formatTime, statusTone } from "../modules/pagePayloadFormat"

defineOptions({ inheritAttrs: false })
defineProps<{
  currentUserId?: string | null
  currentUserInitials?: string | null
}>()

const attrs = useAttrs()
const { t, locale } = useI18n()
const { loading, error, listApprovals, getApproval, resolveApproval } = useApprovalsApi()
const payload = ref<ApprovalListResponse | null>(null)
const selectedApprovalId = ref("")
const approvalStatusFilter = ref("")
const resolvingApproval = ref<"approved" | "rejected" | "">("")

const generatedAt = computed(() => formatTime(payload.value?.generated_at, locale.value))
const approvals = computed<ApprovalRecord[]>(() => payload.value?.approvals || [])
const selectedApproval = computed(() => approvals.value.find((approval) => approval.id === selectedApprovalId.value) || null)

const loadModule = async () => {
  payload.value = await listApprovals({
    status: approvalStatusFilter.value || undefined,
    page: 1,
    limit: 50,
  })
  const stillSelected = approvals.value.some((approval) => approval.id === selectedApprovalId.value)
  if (!stillSelected) {
    selectedApprovalId.value = approvals.value[0]?.id || ""
  }
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
    ElMessage.error(err instanceof Error ? err.message : t("workbench.approvals.loadFailed"))
  }
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
        ? t("workbench.approvals.approved")
        : t("workbench.approvals.rejected")
    )
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("workbench.approvals.resolveFailed"))
  } finally {
    resolvingApproval.value = ""
  }
}

onMounted(() => {
  void loadModule()
})
</script>

<style src="../styles/page-workbench.css"></style>
