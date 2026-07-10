<template>
  <div class="ag-panel-header">
    <span class="ag-panel-header-copy">
      <strong class="ag-panel-title">{{ title }}</strong>
      <em v-if="subtitle" class="ag-panel-subtitle">{{ subtitle }}</em>
    </span>
    <span v-if="$slots.actions" class="flex flex-none items-center gap-2">
      <slot name="actions" />
    </span>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  subtitle?: string
}>()
</script>
