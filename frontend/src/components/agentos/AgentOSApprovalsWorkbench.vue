<template>
  <el-alert v-if="error" class="agentos-alert" type="error" :title="error" show-icon />

  <main class="approvals-workbench">
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
            <small>{{ formatTime(approval.updated_at || approval.created_at, locale) }}</small>
          </span>
        </button>
      </div>

      <div v-else-if="!loading" class="agentos-empty">
        <el-icon><Aim /></el-icon>
        <strong>{{ t("agentOS.empty.title") }}</strong>
        <span>{{ t("agentOS.empty.approvals") }}</span>
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
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { Aim, Check, Delete, Refresh } from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import { useApprovalsApi } from "../../composables/useApprovalsApi"
import type { ApprovalControlResponse, ApprovalRecord } from "../../types"
import { formatJson, formatTime, statusTone } from "./agentosFormat"

const { t, locale } = useI18n()
const { loading, error, listApprovals, getApproval, resolveApproval } = useApprovalsApi()
const payload = ref<ApprovalControlResponse | null>(null)
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
    ElMessage.error(err instanceof Error ? err.message : t("agentOS.approvals.loadFailed"))
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
        ? t("agentOS.approvals.approved")
        : t("agentOS.approvals.rejected")
    )
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("agentOS.approvals.resolveFailed"))
  } finally {
    resolvingApproval.value = ""
  }
}

onMounted(() => {
  void loadModule()
})
</script>
