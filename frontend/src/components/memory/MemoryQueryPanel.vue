<template>
  <section class="ag-content-panel grid flex-0 gap-3">
    <PanelHeader :title="t('workbench.memory.queryTitle')" :subtitle="activeFilterSummary">
      <template #actions>
        <el-button :disabled="!activeFilterCount" @click="$emit('clear')">
          {{ t("workbench.memory.clearFilters") }}
        </el-button>
        <el-button type="primary" :loading="loading" @click="$emit('apply')">
          <el-icon><Search /></el-icon>
          {{ t("workbench.memory.apply") }}
        </el-button>
        <el-button
          :aria-label="t('common.actions.refresh')"
          :title="t('common.actions.refresh')"
          :loading="loading"
          @click="$emit('refresh')"
        >
          <el-icon><Refresh /></el-icon>
        </el-button>
      </template>
    </PanelHeader>

    <div class="grid gap-3 min-[1180px]:grid-cols-[minmax(220px,0.8fr)_minmax(360px,1fr)] min-[1440px]:grid-cols-[minmax(260px,0.75fr)_minmax(420px,1fr)]">
      <div class="flex min-w-0 flex-wrap gap-2">
        <DataChip
          v-for="card in priorityCards"
          :key="card.key"
          :label="card.label"
          :value="card.value"
          :tone="card.tone"
          :title="card.hint"
        />
      </div>

      <div class="grid min-w-0 gap-2 min-[760px]:grid-cols-[minmax(220px,1fr)_minmax(150px,220px)_minmax(150px,220px)]">
        <el-input
          v-model="filters.search"
          clearable
          :placeholder="t('workbench.memory.searchPlaceholder')"
          @keyup.enter="$emit('apply')"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select
          v-model="filters.user_id"
          clearable
          filterable
          :placeholder="t('workbench.memory.userPlaceholder')"
          @change="$emit('apply')"
        >
          <el-option
            v-for="user in userOptions"
            :key="user.user_id"
            :label="user.user_id"
            :value="user.user_id"
          />
        </el-select>
        <el-select
          v-model="filters.topic"
          clearable
          filterable
          :placeholder="t('workbench.memory.topicPlaceholder')"
          @change="$emit('apply')"
        >
          <el-option
            v-for="topic in topicOptions"
            :key="topic"
            :label="topic"
            :value="topic"
          />
        </el-select>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Refresh, Search } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import DataChip from "../common/DataChip.vue"
import PanelHeader from "../common/PanelHeader.vue"
import type {
  MemoryPriorityCard,
  MemoryWorkbenchFilters,
} from "../../composables/useMemoryWorkbenchController"
import type { MemoryUserSummary } from "../../types"

defineProps<{
  activeFilterCount: number
  activeFilterSummary: string
  filters: MemoryWorkbenchFilters
  loading: boolean
  priorityCards: MemoryPriorityCard[]
  topicOptions: string[]
  userOptions: MemoryUserSummary[]
}>()

defineEmits<{
  apply: []
  clear: []
  refresh: []
}>()

const { t } = useI18n()
</script>
