<template>
  <div class="settings-page ag-page-flow">
    <div class="settings-tabs-head">
      <div class="settings-tab-list" role="tablist" :aria-label="t('settings.tabsAria')">
        <button
          type="button"
          role="tab"
          class="settings-tab-button"
          :class="{ 'is-active': activeSettingsTab === 'runtime' }"
          :aria-selected="activeSettingsTab === 'runtime'"
          @click="activeSettingsTab = 'runtime'"
        >
          {{ t('settings.tabs.runtime') }}
        </button>
        <button
          type="button"
          role="tab"
          class="settings-tab-button"
          :class="{ 'is-active': activeSettingsTab === 'navigation' }"
          :aria-selected="activeSettingsTab === 'navigation'"
          @click="activeSettingsTab = 'navigation'"
        >
          {{ t('settings.tabs.navigation') }}
        </button>
      </div>
      <el-button
        type="primary"
        :loading="saving"
        :disabled="!canWriteSettings || !hasChanges"
        class="cursor-pointer"
        @click="saveAll"
      >
        <el-icon class="mr-1"><Check /></el-icon>
        {{ t('settings.actions.save') }}
      </el-button>
    </div>

    <div v-if="loadingSettings && !modelItems.length" class="flex justify-center py-12">
      <el-icon class="loading-icon is-loading"><Loading /></el-icon>
    </div>

    <template v-else>
      <template v-if="activeSettingsTab === 'runtime'">
        <section class="settings-section">
          <div class="settings-section-head">
            <div>
              <h4>{{ t('settings.models.sectionTitle') }}</h4>
              <p>{{ t('settings.models.sectionDescription') }}</p>
            </div>
            <div class="model-route-actions">
              <el-select
                v-model="activeModelId"
                class="default-model-select"
                :disabled="!canWriteSettings"
                :placeholder="t('settings.models.defaultPlaceholder')"
              >
                <el-option
                  v-for="model in enabledModels"
                  :key="model.id"
                  :label="model.name"
                  :value="model.id"
                />
              </el-select>
              <el-button
                class="cursor-pointer"
                :disabled="!canWriteSettings"
                :icon="Plus"
                @click="addModel"
              >
                {{ t('settings.actions.addModel') }}
              </el-button>
            </div>
          </div>

          <div class="grid gap-3">
            <article
              v-for="(model, index) in modelItems"
              :key="model.id"
              class="model-card"
            >
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div class="flex min-w-0 items-center gap-3">
                  <span class="model-index">{{ index + 1 }}</span>
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-2">
                      <h5 class="model-title">{{ model.name || t('settings.models.unnamed') }}</h5>
                      <span v-if="model.builtin" class="model-badge">{{ t('settings.models.builtin') }}</span>
                      <span
                        class="model-badge"
                        :class="isConfigured(model) ? 'is-ready' : 'is-warn'"
                      >
                        {{ isConfigured(model) ? t('common.status.ready') : t('settings.models.unconfigured') }}
                      </span>
                      <span
                        v-if="activeModelId === model.id"
                        class="model-badge is-active"
                      >
                        {{ t('settings.models.defaultBadge') }}
                      </span>
                    </div>
                    <p class="model-description">
                      {{ model.description || t('settings.models.customDescription') }}
                    </p>
                  </div>
                </div>

                <div class="flex items-center gap-2">
                  <el-button
                    plain
                    size="small"
                    class="cursor-pointer"
                    :icon="Connection"
                    :loading="testingModelId === model.id"
                    :disabled="!canWriteSettings || !hasRequiredModelFields(model)"
                    @click="testModel(model)"
                  >
                    {{ t('settings.actions.testConnection') }}
                  </el-button>
                  <el-switch
                    v-model="model.enabled"
                    inline-prompt
                    :disabled="!canWriteSettings"
                    :active-text="t('settings.models.enabled')"
                    :inactive-text="t('settings.models.disabled')"
                  />
                  <el-button
                    v-if="!model.builtin"
                    text
                    type="danger"
                    class="cursor-pointer"
                    :disabled="!canWriteSettings"
                    :icon="Delete"
                    @click="removeModel(model.id)"
                  />
                </div>
              </div>

              <div class="mt-3 grid gap-3 lg:grid-cols-2">
                <label class="settings-field">
                  <span>{{ t('settings.models.displayName') }}<i class="required-mark" aria-hidden="true">*</i></span>
                  <el-input
                    v-model="model.name"
                    :disabled="!canWriteSettings"
                    :placeholder="t('settings.models.displayNamePlaceholder')"
                  />
                </label>
                <label class="settings-field">
                  <span>{{ t('settings.models.modelIdLabel') }}<i class="required-mark" aria-hidden="true">*</i></span>
                  <el-input
                    v-model="model.model_id"
                    :disabled="!canWriteSettings"
                    :placeholder="t('settings.models.modelIdPlaceholder')"
                  />
                </label>
                <label class="settings-field">
                  <span>{{ t('settings.models.baseUrlLabel') }}<i class="required-mark" aria-hidden="true">*</i></span>
                  <el-input
                    v-model="model.base_url"
                    :disabled="!canWriteSettings"
                    :placeholder="t('settings.models.baseUrlPlaceholder')"
                  />
                </label>
                <label class="settings-field">
                  <span>{{ t('settings.models.apiKeyLabel') }}<i class="required-mark" aria-hidden="true">*</i></span>
                  <el-input
                    v-model="model.api_key"
                    :placeholder="t('settings.models.apiKeyPlaceholder')"
                    :disabled="!canWriteSettings"
                    type="password"
                    show-password
                  />
                </label>
                <label class="settings-field lg:col-span-2">
                  <span>{{ t('settings.models.descriptionLabel') }}</span>
                  <el-input
                    v-model="model.description"
                    :disabled="!canWriteSettings"
                    :placeholder="t('settings.models.descriptionPlaceholder')"
                  />
                </label>
              </div>
            </article>
          </div>
        </section>

        <section class="settings-section mt-4">
          <div class="settings-section-head">
            <div>
              <h4>{{ t('settings.runtime.sectionTitle') }}</h4>
              <p>{{ t('settings.runtime.sectionDescription') }}</p>
            </div>
          </div>

          <div class="grid gap-3 md:grid-cols-2">
            <div
              v-for="item in configItems"
              :key="item.key"
              class="runtime-card"
            >
              <div class="mb-2 flex items-start justify-between gap-3">
                <div>
                  <label class="runtime-label">
                    {{ item.label }}<i v-if="item.required" class="required-mark" aria-hidden="true">*</i>
                  </label>
                  <p class="runtime-description">{{ item.description }}</p>
                </div>
                <span class="runtime-key">{{ item.key }}</span>
              </div>
              <el-input
                v-model="formData[item.key]"
                :placeholder="item.placeholder"
                :type="item.secret ? 'password' : 'text'"
                :show-password="item.secret"
                :disabled="!canWriteSettings"
                clearable
                class="settings-input"
              />
            </div>
          </div>
        </section>
      </template>

      <template v-else>
        <section class="settings-section">
          <div class="settings-section-head">
            <div>
              <h4>{{ t('settings.navigation.sectionTitle') }}</h4>
              <p>{{ t('settings.navigation.sectionDescription') }}</p>
            </div>
          </div>

          <div class="navigation-config-grid">
              <article
                v-for="group in navigationLayout"
                :key="group.key"
                class="navigation-group-card"
                @dragover.prevent
                @drop="onNavigationDrop(group.key)"
              >
                <div class="navigation-group-head">
                  <strong>{{ navigationGroupTitle(group.key) }}</strong>
                  <span>{{ group.items.length }}</span>
                </div>
                <div class="navigation-order-list">
                  <div
                    v-for="(item, index) in group.items"
                    :key="item.id"
                    class="navigation-order-item"
                    :class="{ 'is-dragging': draggedNavigationItem?.itemId === item.id }"
                    :draggable="canWriteSettings"
                    @dragstart="onNavigationDragStart($event, group.key, item.id)"
                    @dragend="onNavigationDragEnd"
                    @dragover.prevent
                    @drop.stop.prevent="onNavigationDrop(group.key, item.id)"
                  >
                    <b>{{ index + 1 }}</b>
                    <el-icon class="navigation-drag-handle"><Rank /></el-icon>
                    <em>{{ item.id }}</em>
                    <el-input
                      v-model="item.tag"
                      size="small"
                      clearable
                      :disabled="!canWriteSettings"
                      :placeholder="t('settings.navigation.tagPlaceholder')"
                    />
                    <el-button-group class="navigation-move-actions">
                      <el-button
                        size="small"
                        :icon="ArrowUp"
                        :disabled="!canWriteSettings || index === 0"
                        :aria-label="t('settings.navigation.moveUp')"
                        @click="moveNavigationItem(group.key, item.id, -1)"
                      />
                      <el-button
                        size="small"
                        :icon="ArrowDown"
                        :disabled="!canWriteSettings || index === group.items.length - 1"
                        :aria-label="t('settings.navigation.moveDown')"
                        @click="moveNavigationItem(group.key, item.id, 1)"
                      />
                    </el-button-group>
                  </div>
                </div>
              </article>
          </div>
        </section>
      </template>

    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"
import { useI18n } from "vue-i18n"
import { ArrowDown, ArrowUp, Check, Connection, Delete, Loading, Plus, Rank } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useSettingsApi } from "../composables/useSettingsApi"
import { useAuthStore } from "../stores/auth"
import type { ModelConfig } from "../types"

interface ConfigItem {
  key: string
  label: string
  description: string
  placeholder: string
  secret: boolean
  required: boolean
}

interface NavigationItemConfig {
  id: string
  tag: string
}

interface NavigationGroupConfig {
  key: string
  items: NavigationItemConfig[]
}

interface NavigationDragState {
  groupKey: string
  itemId: string
}

const NAVIGATION_LAYOUT_CHANGE_EVENT = "agno-aios-navigation-layout-change"

const { t } = useI18n()
const authStore = useAuthStore()

const configItems = computed<ConfigItem[]>(() => [
  {
    key: "MCP_SERVER_URL",
    label: t("settings.runtime.mcpServerLabel"),
    description: t("settings.runtime.mcpServerDescription"),
    placeholder: "http://127.0.0.1:8000/mcp/",
    secret: false,
    required: true,
  },
  {
    key: "MCP_TOKEN",
    label: t("settings.runtime.mcpTokenLabel"),
    description: t("settings.runtime.mcpTokenDescription"),
    placeholder: t("settings.runtime.mcpTokenPlaceholder"),
    secret: true,
    required: true,
  },
  {
    key: "FEISHU_WEBHOOK_URL",
    label: t("settings.runtime.feishuWebhookLabel"),
    description: t("settings.runtime.feishuWebhookDescription"),
    placeholder: "https://open.feishu.cn/open-apis/bot/v2/hook/...",
    secret: false,
    required: false,
  },
])

const {
  loadingSettings,
  saving,
  fetchSettings,
  updateSettings,
  fetchModels,
  updateModels,
  testModelConnection,
} = useSettingsApi()

const formData = reactive<Record<string, string>>({})
const originalData = ref<Record<string, string>>({})
const modelItems = ref<ModelConfig[]>([])
const originalModelSnapshot = ref("")
const activeModelId = ref("")
const activeSettingsTab = ref("runtime")
const testingModelId = ref<string | null>(null)
const navigationLayout = ref<NavigationGroupConfig[]>([])
const draggedNavigationItem = ref<NavigationDragState | null>(null)
const originalNavigationTags = ref("")
const canWriteSettings = computed(() => authStore.hasScope("config:write"))

const defaultNavigationGroups = computed<NavigationGroupConfig[]>(() => [
  {
    key: "operations",
    items: ["Home", "Dashboard", "Chat", "Workflow"].map((id) => ({ id, tag: "" })),
  },
  {
    key: "knowledge",
    items: ["Skills", "MCP", "Knowledge"].map((id) => ({ id, tag: "" })),
  },
  {
    key: "governance",
    items: ["Trace", "Memory", "Evaluation", "Approvals", "Scheduler"].map((id) => ({ id, tag: "" })),
  },
  {
    key: "securityData",
    items: ["CVE", "Collect"].map((id) => ({ id, tag: "" })),
  },
  {
    key: "settings",
    items: ["Settings"].map((id) => ({ id, tag: "" })),
  },
])

const enabledModels = computed(() => modelItems.value.filter((model) => model.enabled))

const settingsChanged = computed(() => {
  return configItems.value.some((item) => formData[item.key] !== originalData.value[item.key])
    || serializeNavigationTags() !== originalNavigationTags.value
})

const modelsChanged = computed(() => {
  return serializeModels() !== originalModelSnapshot.value
})

const hasChanges = computed(() => settingsChanged.value || modelsChanged.value)

const serializeModels = () => JSON.stringify({
  active_model_id: activeModelId.value,
  models: modelItems.value,
})

const navigationItemIds = computed(() => defaultNavigationGroups.value.flatMap((group) => group.items.map((item) => item.id)))

const navigationGroupTitle = (groupKey: string) => t(`settings.navigation.groups.${groupKey}`)

const cloneBaseNavigationLayout = (tagSource: Record<string, unknown> = {}) => (
  defaultNavigationGroups.value.map((group) => ({
    key: group.key,
    items: group.items.map((item) => ({
      id: item.id,
      tag: typeof tagSource[item.id] === "string" ? tagSource[item.id] as string : "",
    })),
  }))
)

const serializeNavigationTags = () => JSON.stringify({
  version: 1,
  groups: navigationLayout.value.map((group) => ({
    key: group.key,
    items: group.items.map((item) => ({ id: item.id, tag: item.tag })),
  })),
})

const dispatchNavigationLayoutChange = (raw: string) => {
  window.dispatchEvent(new CustomEvent(NAVIGATION_LAYOUT_CHANGE_EVENT, { detail: { raw } }))
}

const normalizedNavigationGroupsFrom = (source: Record<string, unknown>) => {
  const allowedItems = new Set(navigationItemIds.value)
  const assignedItems = new Set<string>()
  const rawGroups = Array.isArray(source.groups) ? source.groups : []

  const layout = defaultNavigationGroups.value.map((defaultGroup) => {
    const rawGroup = rawGroups.find((group) => {
      return group && typeof group === "object" && (group as Record<string, unknown>).key === defaultGroup.key
    }) as Record<string, unknown> | undefined
    const rawItems = Array.isArray(rawGroup?.items) ? rawGroup.items : []
    const items: NavigationItemConfig[] = []

    for (const rawItem of rawItems) {
      const itemRecord = rawItem && typeof rawItem === "object" ? rawItem as Record<string, unknown> : null
      const id = typeof rawItem === "string" ? rawItem : itemRecord?.id
      if (typeof id !== "string" || !allowedItems.has(id) || assignedItems.has(id)) continue
      assignedItems.add(id)
      const tag = typeof itemRecord?.tag === "string"
        ? itemRecord.tag
        : typeof source[id] === "string" ? source[id] as string : ""
      items.push({ id, tag })
    }

    return { key: defaultGroup.key, items }
  })

  for (const defaultGroup of defaultNavigationGroups.value) {
    const group = layout.find((item) => item.key === defaultGroup.key)
    if (!group) continue
    for (const item of defaultGroup.items) {
      if (assignedItems.has(item.id)) continue
      assignedItems.add(item.id)
      group.items.push({
        id: item.id,
        tag: typeof source[item.id] === "string" ? source[item.id] as string : "",
      })
    }
  }

  return layout
}

const loadNavigationTags = (raw: string) => {
  let parsed: unknown = {}
  try {
    parsed = raw ? JSON.parse(raw) : {}
  } catch {
    parsed = {}
  }
  const source = parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : {}
  navigationLayout.value = Array.isArray(source.groups)
    ? normalizedNavigationGroupsFrom(source)
    : cloneBaseNavigationLayout(source)
  originalNavigationTags.value = serializeNavigationTags()
}

const findNavigationGroup = (groupKey: string) => navigationLayout.value.find((group) => group.key === groupKey)

const moveNavigationItem = (groupKey: string, itemId: string, direction: -1 | 1) => {
  if (!canWriteSettings.value) return
  const group = findNavigationGroup(groupKey)
  if (!group) return
  const index = group.items.findIndex((item) => item.id === itemId)
  const nextIndex = index + direction
  if (index < 0 || nextIndex < 0 || nextIndex >= group.items.length) return
  const [item] = group.items.splice(index, 1)
  group.items.splice(nextIndex, 0, item)
}

const onNavigationDragStart = (event: DragEvent, groupKey: string, itemId: string) => {
  if (!canWriteSettings.value) return
  draggedNavigationItem.value = { groupKey, itemId }
  event.dataTransfer?.setData("text/plain", `${groupKey}:${itemId}`)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = "move"
}

const onNavigationDragEnd = () => {
  draggedNavigationItem.value = null
}

const onNavigationDrop = (targetGroupKey: string, beforeItemId?: string) => {
  if (!canWriteSettings.value || !draggedNavigationItem.value) return
  if (beforeItemId === draggedNavigationItem.value.itemId) {
    draggedNavigationItem.value = null
    return
  }
  const sourceGroup = findNavigationGroup(draggedNavigationItem.value.groupKey)
  const targetGroup = findNavigationGroup(targetGroupKey)
  if (!sourceGroup || !targetGroup) return

  const sourceIndex = sourceGroup.items.findIndex((item) => item.id === draggedNavigationItem.value?.itemId)
  if (sourceIndex < 0) return
  let targetIndex = beforeItemId
    ? targetGroup.items.findIndex((targetItem) => targetItem.id === beforeItemId)
    : targetGroup.items.length
  if (targetIndex < 0) targetIndex = targetGroup.items.length
  if (sourceGroup === targetGroup && targetIndex > sourceIndex) targetIndex -= 1
  const [item] = sourceGroup.items.splice(sourceIndex, 1)
  targetGroup.items.splice(targetIndex, 0, item)
  draggedNavigationItem.value = null
}

const hasRequiredModelFields = (model: ModelConfig) => {
  return Boolean(
    model.name.trim()
    && model.api_key.trim()
    && model.base_url.trim()
    && model.model_id.trim()
  )
}

const isConfigured = (model: ModelConfig) => {
  return Boolean(model.api_key.trim() && model.base_url.trim() && model.model_id.trim())
}

const makeCustomModel = (): ModelConfig => {
  const id = `custom-${Date.now()}`
  return {
    id,
    name: t("settings.models.customName"),
    model_id: "",
    base_url: "",
    api_key: "",
    description: "",
    enabled: true,
    builtin: false,
    configured: false,
  }
}

const normalizeActiveModel = () => {
  const enabledIds = new Set(enabledModels.value.map((model) => model.id))
  if (!enabledIds.has(activeModelId.value)) {
    activeModelId.value = enabledModels.value[0]?.id ?? modelItems.value[0]?.id ?? ""
  }
}

const loadSettings = async () => {
  try {
    const [settings, models] = await Promise.all([fetchSettings(), fetchModels()])
    for (const item of configItems.value) {
      formData[item.key] = settings[item.key] || ""
      originalData.value[item.key] = settings[item.key] || ""
    }
    loadNavigationTags(settings.NAV_TAGS || "{}")
    modelItems.value = models.models.map((model) => ({ ...model }))
    activeModelId.value = models.active_model_id
    normalizeActiveModel()
    originalModelSnapshot.value = serializeModels()
  } catch {
    ElMessage.error(t("settings.messages.loadFailed"))
  }
}

const addModel = () => {
  if (!canWriteSettings.value) return
  const model = makeCustomModel()
  modelItems.value.push(model)
  activeModelId.value = activeModelId.value || model.id
}

const removeModel = async (modelId: string) => {
  if (!canWriteSettings.value) return
  const model = modelItems.value.find((item) => item.id === modelId)
  if (!model || model.builtin) return

  try {
    await ElMessageBox.confirm(t("settings.confirm.deleteModelMessage"), t("settings.confirm.deleteModelTitle"), {
      confirmButtonText: t("settings.actions.delete"),
      cancelButtonText: t("settings.actions.cancel"),
      type: "warning",
    })
    modelItems.value = modelItems.value.filter((item) => item.id !== modelId)
    normalizeActiveModel()
  } catch (err: unknown) {
    if (err !== "cancel") ElMessage.error(t("settings.messages.deleteFailed"))
  }
}

const testModel = async (model: ModelConfig) => {
  if (!canWriteSettings.value) return
  if (!hasRequiredModelFields(model)) {
    ElMessage.warning(t("settings.messages.requiredMissing"))
    return
  }

  testingModelId.value = model.id
  try {
    const result = await testModelConnection(model)
    if (result.success) {
      ElMessage.success(t("settings.messages.testSucceeded", { latency: result.latency_ms ?? 0 }))
    } else {
      ElMessage.warning(result.message || t("settings.messages.testFailed"))
    }
  } catch (err: unknown) {
    ElMessage.error(err instanceof Error ? err.message : t("settings.messages.testFailed"))
  } finally {
    testingModelId.value = null
  }
}

const saveRuntimeSettings = async () => {
  if (!canWriteSettings.value) return
  if (!settingsChanged.value) return
  const changed: Record<string, string> = {}
  for (const item of configItems.value) {
    const currentVal = formData[item.key]
    if (currentVal !== originalData.value[item.key]) {
      changed[item.key] = currentVal ?? ""
    }
  }
  const navPayload = serializeNavigationTags()
  if (navPayload !== originalNavigationTags.value) {
    changed.NAV_TAGS = navPayload
  }
  if (!Object.keys(changed).length) return

  const data = await updateSettings(changed)
  for (const item of configItems.value) {
    const newVal = data[item.key]
    if (newVal !== undefined) {
      formData[item.key] = newVal
      originalData.value[item.key] = newVal
    }
  }
  if (changed.NAV_TAGS !== undefined) {
    const persistedNavigationTags = data.NAV_TAGS ?? changed.NAV_TAGS
    loadNavigationTags(persistedNavigationTags || "{}")
    dispatchNavigationLayoutChange(persistedNavigationTags || "{}")
  } else if (data.NAV_TAGS !== undefined) {
    loadNavigationTags(data.NAV_TAGS || "{}")
  }
}

const saveModelSettings = async () => {
  if (!canWriteSettings.value) return
  if (!modelsChanged.value) return
  normalizeActiveModel()
  const data = await updateModels({
    active_model_id: activeModelId.value,
    models: modelItems.value,
  })
  modelItems.value = data.models.map((model) => ({ ...model }))
  activeModelId.value = data.active_model_id
  originalModelSnapshot.value = serializeModels()
}

const saveAll = async () => {
  if (!canWriteSettings.value) return
  try {
    await saveRuntimeSettings()
    await saveModelSettings()
    ElMessage.success(t("settings.messages.saved"))
  } catch {
    ElMessage.error(t("settings.messages.saveFailed"))
  }
}

onMounted(() => { loadSettings() })
</script>

<style scoped>
.model-card,
.runtime-card {
  border: 1px solid var(--ag-panel-border);
  border-radius: var(--ag-radius-panel);
  background: var(--ag-panel-bg);
}

.settings-page {
  color: var(--ag-text);
}

.settings-tabs-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--ag-border);
  padding-bottom: 10px;
}

.settings-tab-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.settings-tab-button {
  min-height: 32px;
  border: 1px solid transparent;
  border-radius: var(--ag-radius-control);
  padding: 0 12px;
  color: var(--ag-muted);
  font-size: 13px;
  font-weight: 750;
}

.settings-tab-button:hover,
.settings-tab-button:focus-visible {
  border-color: color-mix(in srgb, var(--ag-blue) 42%, var(--ag-border));
  color: var(--ag-blue);
}

.settings-tab-button.is-active {
  border-color: color-mix(in srgb, var(--ag-blue) 50%, var(--ag-border));
  background: var(--ag-blue-soft);
  color: var(--ag-blue);
}

.loading-icon {
  color: var(--ag-muted);
  font-size: 24px;
}

.settings-section {
  border: var(--ag-container-border);
  border-radius: var(--ag-container-radius);
  background: var(--ag-container-bg);
  padding: var(--ag-space-md);
  box-shadow: var(--ag-container-shadow);
}

.settings-section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.model-route-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.settings-section-head h4 {
  color: var(--ag-heading);
  font-size: 14px;
  font-weight: 700;
}

.settings-section-head p {
  margin-top: 4px;
  color: var(--ag-muted);
  font-size: 12px;
}

.model-card,
.runtime-card {
  padding: 14px;
}

.model-index {
  display: grid;
  width: 30px;
  height: 30px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid color-mix(in srgb, var(--ag-blue) 38%, var(--ag-border));
  border-radius: var(--ag-radius-panel);
  background: var(--ag-blue-soft);
  color: var(--ag-blue);
  font-family: "Fira Code", monospace;
  font-size: 12px;
  font-weight: 700;
}

.model-title {
  color: var(--ag-heading);
  font-size: 14px;
  font-weight: 700;
}

.model-description {
  margin-top: 4px;
  color: var(--ag-muted);
  font-size: 12px;
}

.model-badge,
.runtime-key {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-control);
  background: var(--ag-panel-soft);
  color: var(--ag-muted);
  font-size: 10px;
  font-weight: 650;
}

.model-badge {
  height: 20px;
  padding: 0 7px;
}

.model-badge.is-ready {
  border-color: color-mix(in srgb, var(--ag-green) 48%, var(--ag-border));
  color: var(--ag-green);
}

.model-badge.is-warn {
  border-color: color-mix(in srgb, var(--ag-yellow) 55%, var(--ag-border));
  color: var(--ag-yellow);
}

.model-badge.is-active {
  border-color: color-mix(in srgb, var(--ag-blue) 48%, var(--ag-border));
  color: var(--ag-blue);
}

.runtime-key {
  max-width: 160px;
  padding: 2px 6px;
  overflow: hidden;
  font-family: "Fira Code", monospace;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.settings-field {
  display: grid;
  gap: 6px;
}

.required-mark {
  margin-left: 3px;
  color: var(--ag-red);
  font-style: normal;
  font-weight: 800;
}

.settings-field span {
  color: var(--ag-muted);
  font-size: 12px;
  font-weight: 650;
}

.runtime-label {
  color: var(--ag-heading);
  font-size: 14px;
  font-weight: 650;
}

.runtime-description {
  margin-top: 4px;
  color: var(--ag-muted);
  font-size: 12px;
}

.settings-input :deep(.el-input__wrapper),
.settings-field :deep(.el-input__wrapper),
.default-model-select :deep(.el-select__wrapper) {
  border: 1px solid var(--ag-panel-border);
  border-radius: var(--ag-radius-panel);
  background: var(--ag-panel-soft);
  box-shadow: none;
}

.default-model-select {
  width: 240px;
}

.settings-note {
  border: 1px solid var(--ag-panel-border);
  border-radius: var(--ag-radius-panel);
  background: var(--ag-panel-soft);
  padding: 12px;
  color: var(--ag-muted);
  font-size: 12px;
  line-height: 1.6;
}

.navigation-config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.navigation-group-card {
  border: 1px solid var(--ag-panel-border);
  border-radius: var(--ag-radius-panel);
  background: var(--ag-panel-soft);
  padding: 12px;
}

.navigation-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.navigation-group-head strong {
  color: var(--ag-heading);
  font-size: 13px;
  font-weight: 800;
}

.navigation-group-head span {
  display: grid;
  min-width: 24px;
  height: 22px;
  place-items: center;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-control);
  color: var(--ag-muted);
  font-family: "Fira Code", monospace;
  font-size: 11px;
}

.navigation-order-list {
  display: grid;
  gap: 7px;
  margin-top: 12px;
}

.navigation-order-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-control);
  background: var(--ag-panel-bg);
  padding: 7px 8px;
  cursor: grab;
  transition: border-color 0.16s ease, opacity 0.16s ease, transform 0.16s ease;
}

.navigation-order-item.is-dragging {
  border-color: var(--ag-blue);
  opacity: 0.54;
  transform: scale(0.99);
}

.navigation-order-item b {
  display: grid;
  width: 22px;
  height: 22px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 999px;
  background: var(--ag-blue-soft);
  color: var(--ag-blue);
  font-family: "Fira Code", monospace;
  font-size: 10px;
}

.navigation-order-item em {
  flex: 0 0 88px;
  overflow: hidden;
  color: var(--ag-text);
  font-size: 12px;
  font-style: normal;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.navigation-drag-handle {
  flex: 0 0 auto;
  color: var(--ag-muted);
  font-size: 15px;
}

.navigation-order-item :deep(.el-input) {
  min-width: 92px;
  flex: 1 1 auto;
}

.navigation-move-actions {
  flex: 0 0 auto;
}

@media (max-width: 640px) {
  .settings-section-head {
    display: grid;
  }

  .default-model-select {
    width: 100%;
  }

  .navigation-config-grid {
    grid-template-columns: 1fr;
  }

  .navigation-order-item {
    display: grid;
    grid-template-columns: 22px 16px minmax(64px, 1fr) auto;
    align-items: center;
  }

  .navigation-order-item em {
    flex: initial;
    min-width: 0;
  }

  .navigation-order-item :deep(.el-input) {
    grid-column: 1 / -1;
    min-width: 0;
    width: 100%;
  }

  .navigation-move-actions {
    justify-self: end;
  }
}
</style>
