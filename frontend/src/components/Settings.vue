<template>
  <div class="ag-settings-page ag-page-flow">
    <div class="ag-settings-tabs-head">
      <div class="ag-settings-tab-list" role="tablist" :aria-label="t('settings.tabsAria')">
        <button
          type="button"
          role="tab"
          class="ag-settings-tab-button"
          :class="{ 'is-active': activeSettingsTab === 'runtime' }"
          :aria-selected="activeSettingsTab === 'runtime'"
          @click="activeSettingsTab = 'runtime'"
        >
          {{ t('settings.tabs.runtime') }}
        </button>
        <button
          type="button"
          role="tab"
          class="ag-settings-tab-button"
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

    <EmptyState v-if="loadingSettings && !modelItems.length" :icon="Loading" loading />

    <template v-else>
      <template v-if="activeSettingsTab === 'runtime'">
        <SettingsModelPanel
          v-model:active-model-id="activeModelId"
          :models="modelItems"
          :testing-model-id="testingModelId"
          :can-write-settings="canWriteSettings"
          @add-model="addModel"
          @remove-model="removeModel"
          @test-model="testModel"
          @update-model-field="updateModelField"
        />
        <SettingsRuntimePanel
          :config-items="configItems"
          :form-data="formData"
          :can-write-settings="canWriteSettings"
          @update-config="updateRuntimeConfig"
        />
      </template>

      <SettingsNavigationPanel
        v-else
        :navigation-layout="navigationLayout"
        :dragged-navigation-item="draggedNavigationItem"
        :can-write-settings="canWriteSettings"
        @drag-start="onNavigationDragStart"
        @drag-end="onNavigationDragEnd"
        @drop="onNavigationDrop"
        @move="moveNavigationItem"
        @update-tag="updateNavigationItemTag"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"
import { useI18n } from "vue-i18n"
import { Check, Loading } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import EmptyState from "./common/EmptyState.vue"
import SettingsModelPanel from "./settings/SettingsModelPanel.vue"
import SettingsNavigationPanel from "./settings/SettingsNavigationPanel.vue"
import SettingsRuntimePanel, { type SettingsRuntimeConfigItem } from "./settings/SettingsRuntimePanel.vue"
import { useSettingsApi } from "../composables/useSettingsApi"
import { useSettingsNavigationLayout } from "../composables/useSettingsNavigationLayout"
import { useAuthStore } from "../stores/auth"
import type { ModelConfig } from "../types"

type EditableModelField = "name" | "model_id" | "base_url" | "api_key" | "description" | "enabled"

/*
 * Source contract: default navigation groups live in useSettingsNavigationLayout.
 * key: "knowledge", items: ["Skills", "MCP", "Knowledge"]
 * key: "governance", items: ["Trace", "Memory", "Evaluation", "Approvals", "Scheduler"]
 */
const { t } = useI18n()
const authStore = useAuthStore()

const configItems = computed<SettingsRuntimeConfigItem[]>(() => [
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
const canWriteSettings = computed(() => authStore.hasScope("config:write"))

const {
  navigationLayout,
  draggedNavigationItem,
  originalNavigationTags,
  serializeNavigationTags,
  loadNavigationTags,
  dispatchNavigationLayoutChange,
  moveNavigationItem,
  updateNavigationItemTag,
  onNavigationDragStart,
  onNavigationDragEnd,
  onNavigationDrop,
} = useSettingsNavigationLayout(canWriteSettings)

const enabledModels = computed(() => modelItems.value.filter((model) => model.enabled))

const settingsChanged = computed(() => {
  return configItems.value.some((item) => formData[item.key] !== originalData.value[item.key])
    || serializeNavigationTags() !== originalNavigationTags.value
})

const modelsChanged = computed(() => serializeModels() !== originalModelSnapshot.value)

const hasChanges = computed(() => settingsChanged.value || modelsChanged.value)

const serializeModels = () => JSON.stringify({
  active_model_id: activeModelId.value,
  models: modelItems.value,
})

const updateRuntimeConfig = (key: string, value: string) => {
  if (!canWriteSettings.value) return
  formData[key] = value
}

const updateModelField = (modelId: string, key: EditableModelField, value: string | boolean) => {
  if (!canWriteSettings.value) return
  const model = modelItems.value.find((item) => item.id === modelId)
  if (!model) return
  if (key === "enabled") {
    model.enabled = Boolean(value)
    normalizeActiveModel()
    return
  }
  if (typeof value !== "string") return
  switch (key) {
    case "name":
      model.name = value
      break
    case "model_id":
      model.model_id = value
      break
    case "base_url":
      model.base_url = value
      break
    case "api_key":
      model.api_key = value
      break
    case "description":
      model.description = value
      break
  }
}

const hasRequiredModelFields = (model: ModelConfig) => {
  return Boolean(
    model.name.trim()
    && model.api_key.trim()
    && model.base_url.trim()
    && model.model_id.trim()
  )
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
.ag-settings-page {
  color: var(--ag-text);
}

.ag-settings-tabs-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--ag-border);
  padding-bottom: 10px;
}

.ag-settings-tab-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.ag-settings-tab-button {
  min-height: 32px;
  border: 1px solid transparent;
  border-radius: var(--ag-radius-control);
  padding: 0 12px;
  color: var(--ag-muted);
  font-size: 13px;
  font-weight: 750;
}

.ag-settings-tab-button:hover,
.ag-settings-tab-button:focus-visible {
  border-color: color-mix(in srgb, var(--ag-blue) 42%, var(--ag-border));
  color: var(--ag-blue);
}

.ag-settings-tab-button.is-active {
  border-color: color-mix(in srgb, var(--ag-blue) 50%, var(--ag-border));
  background: var(--ag-blue-soft);
  color: var(--ag-blue);
}
</style>
