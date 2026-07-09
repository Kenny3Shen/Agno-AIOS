<template>
  <el-dialog
    v-model="dialogVisible"
    class="mem-edit-dialog"
    :title="t('workbench.memory.editMemoryTitle')"
    width="min(560px, calc(100vw - 32px))"
    destroy-on-close
  >
    <el-form label-position="top">
      <el-form-item :label="t('workbench.memory.memoryLabel')">
        <el-input
          v-model="editForm.memory"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 8 }"
          :placeholder="t('workbench.memory.editMemoryPlaceholder')"
        />
      </el-form-item>
      <el-form-item :label="t('workbench.memory.topicsLabel')">
        <el-select
          v-model="editForm.topics"
          class="w-full"
          multiple
          filterable
          allow-create
          default-first-option
          :placeholder="t('workbench.memory.editTopicsPlaceholder')"
        >
          <el-option
            v-for="topic in topicOptions"
            :key="topic"
            :label="topic"
            :value="topic"
          />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">
        {{ t("common.actions.cancel") }}
      </el-button>
      <el-button type="primary" :loading="loading" @click="$emit('save')">
        {{ t("workbench.memory.saveMemory") }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { useI18n } from "vue-i18n"
import type { MemoryEditForm } from "../../composables/useMemoryWorkbenchController"

const props = defineProps<{
  editForm: MemoryEditForm
  loading: boolean
  topicOptions: string[]
  visible: boolean
}>()

const emit = defineEmits<{
  save: []
  "update:visible": [visible: boolean]
}>()

const { t } = useI18n()

const dialogVisible = computed({
  get: () => props.visible,
  set: (value: boolean) => emit("update:visible", value),
})
</script>
