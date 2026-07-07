<template>
  <div class="agentos-control ag-page-flow">
    <AgentOSSchedulerWorkbench v-if="props.osModule === 'scheduler'" />
    <AgentOSApprovalsWorkbench v-else-if="props.osModule === 'approvals'" />
    <AgentOSLedger v-else :os-module="controlPlaneModule" />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue"
import AgentOSApprovalsWorkbench from "./agentos/AgentOSApprovalsWorkbench.vue"
import AgentOSLedger from "./agentos/AgentOSLedger.vue"
import AgentOSSchedulerWorkbench from "./agentos/AgentOSSchedulerWorkbench.vue"
import type { ControlPlanePayloadModule } from "../composables/useControlPlaneApi"
import type { OsControlModule } from "../types"

const props = defineProps<{
  osModule: OsControlModule
}>()

const controlPlaneModule = computed(() => props.osModule as ControlPlanePayloadModule)
</script>

<style src="../styles/agentos-control.css"></style>
