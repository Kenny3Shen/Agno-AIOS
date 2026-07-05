<template>
  <div class="settings-page ag-page-flow">
    <header class="settings-toolbar ag-content-panel">
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
    </header>

    <div v-if="loadingSettings && !modelItems.length" class="flex justify-center py-12">
      <el-icon class="loading-icon is-loading"><Loading /></el-icon>
    </div>

    <template v-else>
      <el-tabs v-model="activeSettingsTab" class="settings-tabs">
        <el-tab-pane :label="t('settings.tabs.runtime')" name="runtime">
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
        </el-tab-pane>

        <el-tab-pane :label="t('settings.tabs.navigation')" name="navigation">
          <section class="settings-section">
            <div class="settings-section-head">
              <div>
                <h4>{{ t('settings.navigation.sectionTitle') }}</h4>
                <p>{{ t('settings.navigation.sectionDescription') }}</p>
              </div>
            </div>

            <div class="navigation-config-grid">
              <article
                v-for="group in navigationGroups"
                :key="group.key"
                class="navigation-group-card"
              >
                <div class="navigation-group-head">
                  <strong>{{ group.title }}</strong>
                  <span>{{ group.items.length }}</span>
                </div>
                <div class="navigation-order-list">
                  <span
                    v-for="(item, index) in group.items"
                    :key="item"
                    class="navigation-order-item"
                  >
                    <b>{{ index + 1 }}</b>
                    <em>{{ item }}</em>
                    <el-input
                      v-model="navigationTags[item]"
                      size="small"
                      clearable
                      :disabled="!canWriteSettings"
                      :placeholder="t('settings.navigation.tagPlaceholder')"
                    />
                  </span>
                </div>
              </article>
            </div>

            <p class="settings-note mt-3">
              {{ t('settings.navigation.note') }}
            </p>
          </section>
        </el-tab-pane>
      </el-tabs>

    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"
import { useI18n } from "vue-i18n"
import { Check, Connection, Delete, Loading, Plus } from "@element-plus/icons-vue"
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
  required: boolean
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
const navigationTags = reactive<Record<string, string>>({})
const originalNavigationTags = ref("")
const canWriteSettings = computed(() => authStore.hasPermission("settings:write"))

const navigationGroups = computed(() => [
  {
    key: "operations",
    title: t("settings.navigation.groups.operations"),
    items: ["Home", "Dashboard", "Chat", "Trace"],
  },
  {
    key: "knowledge",
    title: t("settings.navigation.groups.knowledge"),
    items: ["Skills", "MCP", "Knowledge", "Studio", "Memory"],
  },
  {
    key: "securityData",
    title: t("settings.navigation.groups.securityData"),
    items: ["CVE", "Collect"],
  },
  {
    key: "settings",
    title: t("settings.navigation.groups.settings"),
    items: ["Settings"],
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

const serializeNavigationTags = () => JSON.stringify(navigationTags)

const navigationItems = computed(() => navigationGroups.value.flatMap((group) => group.items))

const loadNavigationTags = (raw: string) => {
  for (const key of Object.keys(navigationTags)) delete navigationTags[key]
  let parsed: unknown = {}
  try {
    parsed = raw ? JSON.parse(raw) : {}
  } catch {
    parsed = {}
  }
  const source = parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : {}
  for (const item of navigationItems.value) {
    const value = source[item]
    navigationTags[item] = typeof value === "string" ? value : ""
  }
  originalNavigationTags.value = serializeNavigationTags()
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
  if (data.NAV_TAGS !== undefined) {
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

.settings-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
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
  border: var(--ag-container-border);
  border-radius: var(--ag-container-radius);
  background: var(--ag-container-bg);
  padding: var(--ag-space-md);
  box-shadow: var(--ag-container-shadow);
}

.settings-tabs :deep(.el-tabs__header) {
  margin-bottom: 14px;
}

.settings-tabs :deep(.el-tabs__item) {
  color: var(--ag-muted);
  font-weight: 700;
}

.settings-tabs :deep(.el-tabs__item.is-active) {
  color: var(--ag-blue);
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

.navigation-order-item :deep(.el-input) {
  min-width: 92px;
  flex: 1 1 auto;
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
}
</style>
