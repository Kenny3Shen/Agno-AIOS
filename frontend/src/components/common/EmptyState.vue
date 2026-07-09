<template>
  <div class="ag-empty-state">
    <el-icon class="ag-empty-icon" :class="{ 'is-loading': loading }">
      <component :is="icon" v-if="icon" />
    </el-icon>
    <span>
      <slot />
    </span>
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
