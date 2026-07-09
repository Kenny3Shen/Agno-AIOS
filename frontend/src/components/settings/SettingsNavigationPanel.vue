<template>
  <section class="ag-content-panel grid gap-3">
    <SectionHeader
      :title="t('settings.navigation.sectionTitle')"
      :subtitle="t('settings.navigation.sectionDescription')"
      :count="navigationLayout.length"
      :count-label="t('settings.navigation.sectionTitle')"
    />

    <div class="grid gap-3 lg:grid-cols-2">
      <article
        v-for="group in navigationLayout"
        :key="group.key"
        class="grid gap-3 rounded-[var(--ag-radius-panel)] border border-[var(--ag-panel-border)] bg-[var(--ag-panel-soft)] p-3"
        @dragover.prevent
        @drop="emit('drop', group.key)"
      >
        <div class="flex items-center justify-between gap-3">
          <strong class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-800 text-[var(--ag-heading)]">
            {{ navigationGroupTitle(group.key) }}
          </strong>
          <DataChip :label="navigationGroupTitle(group.key)" :value="group.items.length" />
        </div>

        <div v-if="group.items.length" class="grid gap-2">
          <div
            v-for="(item, index) in group.items"
            :key="item.id"
            class="ag-settings-navigation-item flex min-w-0 items-center gap-2 rounded-[var(--ag-radius-control)] border border-[var(--ag-border)] bg-[var(--ag-panel-bg)] px-2 py-1.5 transition"
            :class="{ 'is-dragging': draggedNavigationItem?.itemId === item.id }"
            :draggable="canWriteSettings"
            @dragstart="emit('dragStart', $event, group.key, item.id)"
            @dragend="emit('dragEnd')"
            @dragover.prevent
            @drop.stop.prevent="emit('drop', group.key, item.id)"
          >
            <span class="grid h-[22px] w-[22px] shrink-0 place-items-center rounded-[var(--ag-radius-control)] bg-[var(--ag-blue-soft)] font-mono text-[10px] font-700 text-[var(--ag-blue)]">
              {{ index + 1 }}
            </span>
            <el-icon class="shrink-0 text-[15px] text-[var(--ag-muted)]"><Rank /></el-icon>
            <em class="w-[88px] shrink-0 overflow-hidden text-ellipsis whitespace-nowrap text-xs not-italic font-700 text-[var(--ag-text)]">
              {{ navigationItemTitle(item.id) }}
            </em>
            <el-input
              class="min-w-[92px] flex-1"
              :model-value="item.tag"
              size="small"
              clearable
              :disabled="!canWriteSettings"
              :placeholder="t('settings.navigation.tagPlaceholder')"
              @update:model-value="emit('updateTag', group.key, item.id, String($event ?? ''))"
            />
            <el-button-group class="shrink-0">
              <el-button
                size="small"
                :icon="ArrowUp"
                :disabled="!canWriteSettings || index === 0"
                :aria-label="t('settings.navigation.moveUp')"
                @click="emit('move', group.key, item.id, -1)"
              />
              <el-button
                size="small"
                :icon="ArrowDown"
                :disabled="!canWriteSettings || index === group.items.length - 1"
                :aria-label="t('settings.navigation.moveDown')"
                @click="emit('move', group.key, item.id, 1)"
              />
            </el-button-group>
          </div>
        </div>
        <EmptyState v-else :icon="Rank">
          {{ t('settings.navigation.sectionTitle') }}
        </EmptyState>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n"
import { ArrowDown, ArrowUp, Rank } from "@element-plus/icons-vue"
import DataChip from "../common/DataChip.vue"
import EmptyState from "../common/EmptyState.vue"
import SectionHeader from "../common/SectionHeader.vue"
import type {
  SettingsNavigationDragState,
  SettingsNavigationGroupConfig,
} from "../../composables/useSettingsNavigationLayout"

defineProps<{
  navigationLayout: SettingsNavigationGroupConfig[]
  draggedNavigationItem: SettingsNavigationDragState | null
  canWriteSettings: boolean
}>()

const emit = defineEmits<{
  dragStart: [event: DragEvent, groupKey: string, itemId: string]
  dragEnd: []
  drop: [targetGroupKey: string, beforeItemId?: string]
  move: [groupKey: string, itemId: string, direction: -1 | 1]
  updateTag: [groupKey: string, itemId: string, tag: string]
}>()

const { t } = useI18n()

const navigationGroupTitle = (groupKey: string) => t(`settings.navigation.groups.${groupKey}`)
const navigationItemTitle = (itemId: string) => {
  const key = `shell.nav.${itemId}.label`
  const label = t(key)
  return label === key ? itemId : label
}
</script>

<style scoped>
.ag-settings-navigation-item {
  cursor: grab;
}

.ag-settings-navigation-item.is-dragging {
  border-color: var(--ag-blue);
  opacity: 0.54;
  transform: scale(0.99);
}

@media (max-width: 640px) {
  .ag-settings-navigation-item {
    display: grid;
    grid-template-columns: 22px 16px minmax(64px, 1fr) auto;
  }

  .ag-settings-navigation-item :deep(.el-input) {
    grid-column: 1 / -1;
    min-width: 0;
    width: 100%;
  }
}
</style>
