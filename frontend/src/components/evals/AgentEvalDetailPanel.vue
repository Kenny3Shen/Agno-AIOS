<template>
  <aside class="ag-right-panel grid min-w-0 content-start gap-3">
    <template v-if="detailItem">
      <SectionHeader :title="t('agentEvals.panels.detail')" :subtitle="detailTitle">
        <template #actions>
          <StatusChip :tone="detailTone">{{ detailStatus }}</StatusChip>
        </template>
      </SectionHeader>

      <dl class="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-2">
        <div class="min-w-0 rounded-[var(--ag-radius-panel)] border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] p-2">
          <dt class="text-[11px] text-[var(--ag-muted)]">{{ t("agentEvals.fields.suite") }}</dt>
          <dd class="mt-1 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-xs text-[var(--ag-text)]">
            {{ selectedCase?.suite_name || "-" }}
          </dd>
        </div>
        <div class="min-w-0 rounded-[var(--ag-radius-panel)] border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] p-2">
          <dt class="text-[11px] text-[var(--ag-muted)]">{{ t("agentEvals.fields.evalTypes") }}</dt>
          <dd class="mt-1 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-xs text-[var(--ag-text)]">{{ detailEvalType }}</dd>
        </div>
        <div class="min-w-0 rounded-[var(--ag-radius-panel)] border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] p-2">
          <dt class="text-[11px] text-[var(--ag-muted)]">{{ t("agentEvals.fields.targetAgent") }}</dt>
          <dd class="mt-1 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-xs text-[var(--ag-text)]" :title="detailAgent">
            {{ detailAgent }}
          </dd>
        </div>
        <div class="min-w-0 rounded-[var(--ag-radius-panel)] border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] p-2">
          <dt class="text-[11px] text-[var(--ag-muted)]">{{ t("agentEvals.fields.createdAt") }}</dt>
          <dd class="mt-1 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-xs text-[var(--ag-text)]">{{ detailTime }}</dd>
        </div>
      </dl>

      <section class="grid min-w-0 gap-2 rounded-[var(--ag-radius-panel)] border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] p-3">
        <div class="flex min-w-0 flex-wrap items-center gap-1.5">
          <DataChip :label="t('agentEvals.fields.toolCalls')" :value="toolCallStatuses.length" />
          <StatusChip
            v-for="status in toolCallStatuses"
            :key="status"
            :tone="toolCallTone(status)"
          >
            {{ status }}
          </StatusChip>
        </div>
      </section>

      <PayloadViewer
        :value="detailItem"
        mode="json"
        :empty-text="t('agentEvals.empty.detailDescription')"
        :copy-label="t('trace.actions.copy')"
        :expand-label="t('trace.actions.expand')"
        :collapse-label="t('trace.actions.collapse')"
      />
    </template>

    <div v-else class="ag-empty-state h-full min-h-[360px]">
      <span class="text-[10px] font-820 uppercase text-[var(--ag-muted)]">{{ t("agentEvals.panels.detail") }}</span>
      <strong class="text-[14px] text-[var(--ag-heading)]">{{ t("agentEvals.empty.detailTitle") }}</strong>
      <em class="max-w-[260px] text-xs not-italic leading-[1.45]">{{ t("agentEvals.empty.detailDescription") }}</em>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n"
import DataChip from "../common/DataChip.vue"
import PayloadViewer from "../common/PayloadViewer.vue"
import SectionHeader from "../common/SectionHeader.vue"
import StatusChip from "../common/StatusChip.vue"
import type { EvalCaseRow } from "../../composables/useAgentEvalsWorkbench"
import type { EvalTone } from "../../modules/agentEvalsWorkbench"
import type { AgentEvalAgnoRun } from "../../types"

defineProps<{
  detailItem: EvalCaseRow | AgentEvalAgnoRun | null
  selectedCase: EvalCaseRow | null
  detailTitle: string
  detailStatus: string
  detailTone: EvalTone
  detailEvalType: string
  detailAgent: string
  detailTime: string
  toolCallStatuses: string[]
  toolCallTone: (status: string) => EvalTone
}>()

const { t } = useI18n()
</script>
