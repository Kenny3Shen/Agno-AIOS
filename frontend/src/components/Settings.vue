<template>
  <div class="security-page settings-page mx-auto max-w-6xl space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 class="settings-title">{{ t('settings.title') }}</h3>
        <p class="settings-description">
          {{ t('settings.description') }}
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <el-button
          class="cursor-pointer"
          :disabled="!canWriteSettings"
          :icon="Plus"
          @click="addModel"
        >
          {{ t('settings.actions.addModel') }}
        </el-button>
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
    </div>

    <div v-if="loadingSettings && !modelItems.length" class="flex justify-center py-12">
      <el-icon class="loading-icon is-loading"><Loading /></el-icon>
    </div>

    <template v-else>
      <section class="settings-section">
        <div class="settings-section-head">
          <div>
            <h4>{{ t('settings.models.sectionTitle') }}</h4>
            <p>{{ t('settings.models.sectionDescription') }}</p>
          </div>
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
                <span>{{ t('settings.models.displayName') }}</span>
                <el-input
                  v-model="model.name"
                  :disabled="!canWriteSettings"
                  :placeholder="t('settings.models.displayNamePlaceholder')"
                />
              </label>
              <label class="settings-field">
                <span>{{ t('settings.models.modelIdLabel') }}</span>
                <el-input
                  v-model="model.model_id"
                  :disabled="!canWriteSettings"
                  :placeholder="t('settings.models.modelIdPlaceholder')"
                />
              </label>
              <label class="settings-field">
                <span>{{ t('settings.models.baseUrlLabel') }}</span>
                <el-input
                  v-model="model.base_url"
                  :disabled="!canWriteSettings"
                  :placeholder="t('settings.models.baseUrlPlaceholder')"
                />
              </label>
              <label class="settings-field">
                <span>{{ t('settings.models.apiKeyLabel') }}</span>
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

      <section class="settings-section">
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
                <label class="runtime-label">{{ item.label }}</label>
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

      <div class="settings-note">
        <i18n-t keypath="settings.runtime.note" tag="span">
          <template #file>
            <span class="font-mono">tmp/model_config.json</span>
          </template>
        </i18n-t>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"
import { useI18n } from "vue-i18n"
import { Check, Delete, Loading, Plus } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useSettingsApi } from "../composables/useApi"
import { useAuthStore } from "../stores/auth"
import type { ModelConfig } from "../types"

interface ConfigItem {
  key: string
  label: string
  description: string
  placeholder: string
  secret: boolean
}

const { t } = useI18n()
const authStore = useAuthStore()

const configItems = computed<ConfigItem[]>(() => [
  {
    key: "MCP_SERVER_URL",
    label: t("settings.runtime.mcpServerLabel"),
    description: t("settings.runtime.mcpServerDescription"),
    placeholder: "http://127.0.0.1:8000/mcp/",
    secret: false,
  },
  {
    key: "MCP_TOKEN",
    label: t("settings.runtime.mcpTokenLabel"),
    description: t("settings.runtime.mcpTokenDescription"),
    placeholder: t("settings.runtime.mcpTokenPlaceholder"),
    secret: true,
  },
  {
    key: "FEISHU_WEBHOOK_URL",
    label: t("settings.runtime.feishuWebhookLabel"),
    description: t("settings.runtime.feishuWebhookDescription"),
    placeholder: "https://open.feishu.cn/open-apis/bot/v2/hook/...",
    secret: false,
  },
])

const {
  loadingSettings,
  saving,
  fetchSettings,
  updateSettings,
  fetchModels,
  updateModels,
} = useSettingsApi()

const formData = reactive<Record<string, string>>({})
const originalData = ref<Record<string, string>>({})
const modelItems = ref<ModelConfig[]>([])
const originalModelSnapshot = ref("")
const activeModelId = ref("")
const canWriteSettings = computed(() => authStore.hasPermission("settings:write"))

const enabledModels = computed(() => modelItems.value.filter((model) => model.enabled))

const settingsChanged = computed(() => {
  return configItems.value.some((item) => formData[item.key] !== originalData.value[item.key])
})

const modelsChanged = computed(() => {
  return serializeModels() !== originalModelSnapshot.value
})

const hasChanges = computed(() => settingsChanged.value || modelsChanged.value)

const serializeModels = () => JSON.stringify({
  active_model_id: activeModelId.value,
  models: modelItems.value,
})

const isConfigured = (model: ModelConfig) => {
  return Boolean(model.api_key && model.base_url && model.model_id)
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
  if (!Object.keys(changed).length) return

  const data = await updateSettings(changed)
  for (const item of configItems.value) {
    const newVal = data[item.key]
    if (newVal !== undefined) {
      formData[item.key] = newVal
      originalData.value[item.key] = newVal
    }
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
.settings-section,
.model-card,
.runtime-card {
  border: 1px solid var(--ag-panel-border);
  border-radius: var(--ag-radius-panel);
  background: var(--ag-panel-bg);
}

.settings-page {
  color: var(--ag-text);
}

.settings-title {
  color: var(--ag-heading);
  font-size: 18px;
  font-weight: 700;
}

.settings-description {
  margin-top: 4px;
  color: var(--ag-muted);
  font-size: 14px;
}

.loading-icon {
  color: var(--ag-muted);
  font-size: 24px;
}

.settings-section {
  padding: var(--ag-space-md);
}

.settings-section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
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

@media (max-width: 640px) {
  .settings-section-head {
    display: grid;
  }

  .default-model-select {
    width: 100%;
  }
}
</style>
