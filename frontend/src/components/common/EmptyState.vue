<template>
  <div class="ag-empty-state">
    <el-empty class="ag-empty-inner" :image-size="icon ? 32 : 0">
      <template #image>
        <el-icon v-if="icon" class="ag-empty-icon" :class="{ 'is-loading': loading }">
          <component :is="icon" />
        </el-icon>
      </template>
      <template #description><slot /></template>
    </el-empty>
  </div>
</template>

<script setup lang="ts">
import type { Component } from "vue"

withDefaults(defineProps<{
  loading?: boolean
  icon?: Component
}>(), {
  loading: false,
  icon: undefined,
})
</script>

<style scoped>
.ag-empty-inner {
  width: 100%;
  padding: 0;
}

.ag-empty-inner :deep(.el-empty__description) {
  margin-top: 8px;
  color: inherit;
}

.ag-empty-inner :deep(.el-empty__description p) {
  color: inherit;
  font-size: inherit;
}
</style>
