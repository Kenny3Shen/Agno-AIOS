<template>
  <div class="ag-page-flow mem-control">
    <el-alert v-if="error" class="mx-3 mt-3 flex-0" type="error" :title="error" show-icon />

    <MemoryQueryPanel
      :active-filter-count="activeFilterCount"
      :active-filter-summary="activeFilterSummary"
      :filters="filters"
      :loading="loading"
      :priority-cards="priorityCards"
      :topic-options="topicOptions"
      :user-options="userOptions"
      @apply="applyFilters"
      @clear="clearFilters"
      @refresh="loadMemory"
    />

    <main class="mem-workbench">
      <MemoryUserQueue
        :filters="filters"
        :format-time="formatTime"
        :healthy-user-count="healthyUserCount"
        :loading="loading"
        :review-user-count="reviewUserCount"
        :risk-user-count="riskUserCount"
        :status-label="statusLabel"
        :status-tone="statusTone"
        :threshold-summary="thresholdSummary"
        :threshold-title="thresholdTitle"
        :user-bar-style="userBarStyle"
        :user-options="userOptions"
        :user-panel-summary="userPanelSummary"
        @filter-user="filterByUser"
      />

      <MemoryListPanel
        :active-filter-summary="activeFilterSummary"
        :can-delete-memory="canDeleteMemory"
        :can-write-memory="canWriteMemory"
        :filters="filters"
        :loading="loading"
        :memories="memories"
        :memory-status-tone="memoryStatusTone"
        :result-summary="resultSummary"
        :selected-memory="selectedMemory"
        :status-label="statusLabel"
        :total="total"
        @delete="deleteSelectedMemory"
        @edit="openEditMemoryDialog"
        @page-change="changePage"
        @select="selectMemory"
      />

      <MemoryDetailPanel
        :format-time="formatTime"
        :mode-badges="modeBadges"
        :selected-memory="selectedMemory"
        :selected-status="selectedStatus"
        :selected-status-tone="selectedStatusTone"
        :status-label="statusLabel"
      />
    </main>

    <MemoryEditDialog
      v-model:visible="editDialogVisible"
      :edit-form="editForm"
      :loading="loading"
      :topic-options="topicOptions"
      @save="saveMemoryUpdate"
    />
  </div>
</template>

<script setup lang="ts">
import MemoryDetailPanel from "./memory/MemoryDetailPanel.vue"
import MemoryEditDialog from "./memory/MemoryEditDialog.vue"
import MemoryListPanel from "./memory/MemoryListPanel.vue"
import MemoryQueryPanel from "./memory/MemoryQueryPanel.vue"
import MemoryUserQueue from "./memory/MemoryUserQueue.vue"
import { useMemoryWorkbenchController } from "../composables/useMemoryWorkbenchController"

const {
  activeFilterCount,
  activeFilterSummary,
  applyFilters,
  canDeleteMemory,
  canWriteMemory,
  changePage,
  clearFilters,
  deleteSelectedMemory,
  editDialogVisible,
  editForm,
  error,
  filterByUser,
  filters,
  formatTime,
  healthyUserCount,
  loadMemory,
  loading,
  memories,
  memoryStatusTone,
  modeBadges,
  openEditMemoryDialog,
  priorityCards,
  resultSummary,
  reviewUserCount,
  riskUserCount,
  saveMemoryUpdate,
  selectMemory,
  selectedMemory,
  selectedStatus,
  selectedStatusTone,
  statusLabel,
  statusTone,
  thresholdSummary,
  thresholdTitle,
  topicOptions,
  total,
  userBarStyle,
  userOptions,
  userPanelSummary,
} = useMemoryWorkbenchController()
</script>

<style scoped>
.mem-control :where(div, section, aside, main, article, p, span, strong, small, button, dl, dt, dd, pre) {
  min-width: 0;
}

.mem-workbench {
  display: grid;
  flex: 1 1 auto;
  gap: 12px;
  grid-template-columns: minmax(230px, 280px) minmax(300px, 1fr) minmax(280px, 340px);
  min-height: 0;
}

@media (max-width: 1120px) {
  .mem-workbench {
    grid-template-columns: minmax(240px, 300px) minmax(0, 1fr);
  }

  .mem-workbench > :last-child {
    grid-column: 1 / -1;
    max-height: 360px;
  }
}

@media (max-width: 980px) {
  .mem-workbench {
    flex: 0 0 auto;
    grid-template-columns: 1fr;
    min-height: auto;
  }

  .mem-workbench > :last-child {
    grid-column: auto;
    max-height: none;
  }
}
</style>
