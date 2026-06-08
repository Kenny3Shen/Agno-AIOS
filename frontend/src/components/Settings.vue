<template>
  <div class="security-page mx-auto max-w-6xl space-y-4 text-[#15202B] dark:text-[#DCE7EF]">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 class="text-lg font-semibold text-[#0F172A] dark:text-white">系统配置</h3>
        <p class="mt-1 text-sm text-[#5F6F7C] dark:text-[#91A4B3]">
          运行时参数与 Agent 模型路由配置
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <el-button class="cursor-pointer" :icon="Plus" @click="addModel">新增模型</el-button>
        <el-button
          type="primary"
          :loading="saving"
          :disabled="!hasChanges"
          class="cursor-pointer"
          @click="saveAll"
        >
          <el-icon class="mr-1"><Check /></el-icon>
          保存
        </el-button>
      </div>
    </div>

    <div v-if="loadingSettings && !modelItems.length" class="flex justify-center py-12">
      <el-icon class="is-loading text-2xl text-[#6B7C8A]"><Loading /></el-icon>
    </div>

    <template v-else>
      <section class="settings-section">
        <div class="settings-section-head">
          <div>
            <h4>模型路由</h4>
            <p>选择 Agent 默认模型，并维护每个模型的调用参数。</p>
          </div>
          <el-select v-model="activeModelId" class="default-model-select" placeholder="默认模型">
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
                    <h5 class="truncate text-sm font-semibold text-[#15202B] dark:text-white">{{ model.name || "未命名模型" }}</h5>
                    <span v-if="model.builtin" class="model-badge">Builtin</span>
                    <span
                      class="model-badge"
                      :class="isConfigured(model) ? 'is-ready' : 'is-warn'"
                    >
                      {{ isConfigured(model) ? "Ready" : "待配置" }}
                    </span>
                    <span
                      v-if="activeModelId === model.id"
                      class="model-badge is-active"
                    >
                      Default
                    </span>
                  </div>
                  <p class="mt-1 truncate text-xs text-[#6B7C8A] dark:text-[#91A4B3]">
                    {{ model.description || "自定义模型参数" }}
                  </p>
                </div>
              </div>

              <div class="flex items-center gap-2">
                <el-switch
                  v-model="model.enabled"
                  inline-prompt
                  active-text="启用"
                  inactive-text="禁用"
                />
                <el-button
                  v-if="!model.builtin"
                  text
                  type="danger"
                  class="cursor-pointer"
                  :icon="Delete"
                  @click="removeModel(model.id)"
                />
              </div>
            </div>

            <div class="mt-3 grid gap-3 lg:grid-cols-2">
              <label class="settings-field">
                <span>显示名称</span>
                <el-input v-model="model.name" placeholder="例如 DeepSeek V4 Flash" />
              </label>
              <label class="settings-field">
                <span>Model ID</span>
                <el-input v-model="model.model_id" placeholder="例如 deepseek-v4-flash" />
              </label>
              <label class="settings-field">
                <span>Base URL</span>
                <el-input v-model="model.base_url" placeholder="https://api.example.com/v1" />
              </label>
              <label class="settings-field">
                <span>API Key</span>
                <el-input
                  v-model="model.api_key"
                  placeholder="sk-..."
                  type="password"
                  show-password
                />
              </label>
              <label class="settings-field lg:col-span-2">
                <span>说明</span>
                <el-input v-model="model.description" placeholder="用于低延迟研判、复杂推理等" />
              </label>
            </div>
          </article>
        </div>
      </section>

      <section class="settings-section">
        <div class="settings-section-head">
          <div>
            <h4>运行时参数</h4>
            <p>非 LLM 的平台参数，修改后立即写入当前进程环境变量。</p>
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
                <label class="text-sm font-medium text-[#15202B] dark:text-white">{{ item.label }}</label>
                <p class="mt-1 text-xs text-[#6B7C8A] dark:text-[#91A4B3]">{{ item.description }}</p>
              </div>
              <span class="runtime-key">{{ item.key }}</span>
            </div>
            <el-input
              v-model="formData[item.key]"
              :placeholder="item.placeholder"
              :type="item.secret ? 'password' : 'text'"
              :show-password="item.secret"
              clearable
              class="settings-input"
            />
          </div>
        </div>
      </section>

      <div class="rounded-2 border border-[#D8E0E7] bg-[#F6F9FC] p-3 text-xs leading-5 text-[#5F6F7C] dark:border-[#22313A] dark:bg-[#0A151B] dark:text-[#91A4B3]">
        敏感字段返回时会脱敏；未修改的脱敏值不会覆盖真实密钥。模型配置保存在 <span class="font-mono">tmp/model_config.json</span>，运行时参数来自环境变量白名单。
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"
import { Check, Delete, Loading, Plus } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useSettingsApi } from "../composables/useApi"
import type { ModelConfig } from "../types"

interface ConfigItem {
  key: string
  label: string
  description: string
  placeholder: string
  secret: boolean
}

const configItems: ConfigItem[] = [
  {
    key: "MCP_SERVER_URL",
    label: "MCP Server URL",
    description: "Agent 连接 FastMCP 协议入口的地址",
    placeholder: "http://127.0.0.1:8000/mcp/",
    secret: false,
  },
  {
    key: "MCP_TOKEN",
    label: "MCP Access Token",
    description: "Agent 连接 MCP 协议入口时使用的访问 Token",
    placeholder: "YOUR_ACCESS_TOKEN",
    secret: true,
  },
  {
    key: "FEISHU_WEBHOOK_URL",
    label: "飞书 Webhook URL",
    description: "飞书机器人通知 Webhook 地址",
    placeholder: "https://open.feishu.cn/open-apis/bot/v2/hook/...",
    secret: false,
  },
]

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

const enabledModels = computed(() => modelItems.value.filter((model) => model.enabled))

const settingsChanged = computed(() => {
  return configItems.some((item) => formData[item.key] !== originalData.value[item.key])
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
    name: "自定义模型",
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
    for (const item of configItems) {
      formData[item.key] = settings[item.key] || ""
      originalData.value[item.key] = settings[item.key] || ""
    }
    modelItems.value = models.models.map((model) => ({ ...model }))
    activeModelId.value = models.active_model_id
    normalizeActiveModel()
    originalModelSnapshot.value = serializeModels()
  } catch {
    ElMessage.error("加载配置失败")
  }
}

const addModel = () => {
  const model = makeCustomModel()
  modelItems.value.push(model)
  activeModelId.value = activeModelId.value || model.id
}

const removeModel = async (modelId: string) => {
  const model = modelItems.value.find((item) => item.id === modelId)
  if (!model || model.builtin) return

  try {
    await ElMessageBox.confirm("确定要删除这个模型配置吗？", "删除模型", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    })
    modelItems.value = modelItems.value.filter((item) => item.id !== modelId)
    normalizeActiveModel()
  } catch (err: unknown) {
    if (err !== "cancel") ElMessage.error("删除失败")
  }
}

const saveRuntimeSettings = async () => {
  if (!settingsChanged.value) return
  const changed: Record<string, string> = {}
  for (const item of configItems) {
    const currentVal = formData[item.key]
    if (currentVal !== originalData.value[item.key]) {
      changed[item.key] = currentVal ?? ""
    }
  }
  if (!Object.keys(changed).length) return

  const data = await updateSettings(changed)
  for (const item of configItems) {
    const newVal = data[item.key]
    if (newVal !== undefined) {
      formData[item.key] = newVal
      originalData.value[item.key] = newVal
    }
  }
}

const saveModelSettings = async () => {
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
  try {
    await saveRuntimeSettings()
    await saveModelSettings()
    ElMessage.success("配置已保存")
  } catch {
    ElMessage.error("保存配置失败")
  }
}

onMounted(() => { loadSettings() })
</script>

<style scoped>
.settings-section,
.model-card,
.runtime-card {
  border: 1px solid #d8e0e7;
  border-radius: 8px;
  background: #ffffff;
}

.settings-section {
  padding: 16px;
}

.settings-section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.settings-section-head h4 {
  color: #15202b;
  font-size: 14px;
  font-weight: 700;
}

.settings-section-head p {
  margin-top: 4px;
  color: #6b7c8a;
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
  border: 1px solid rgba(47, 143, 237, 0.35);
  border-radius: 8px;
  background: #eaf5ff;
  color: #0969da;
  font-family: "Fira Code", monospace;
  font-size: 12px;
  font-weight: 700;
}

.model-badge,
.runtime-key {
  display: inline-flex;
  align-items: center;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  background: #f8fafc;
  color: #64748b;
  font-size: 10px;
  font-weight: 650;
}

.model-badge {
  height: 20px;
  padding: 0 7px;
}

.model-badge.is-ready {
  border-color: rgba(84, 211, 138, 0.45);
  color: #14824a;
}

.model-badge.is-warn {
  border-color: rgba(246, 195, 67, 0.55);
  color: #9a6400;
}

.model-badge.is-active {
  border-color: rgba(47, 143, 237, 0.45);
  color: #0969da;
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
  color: #5f6f7c;
  font-size: 12px;
  font-weight: 650;
}

.settings-input :deep(.el-input__wrapper),
.settings-field :deep(.el-input__wrapper),
.default-model-select :deep(.el-select__wrapper) {
  border: 1px solid #d8e0e7;
  border-radius: 8px;
  background: #f8fafc;
  box-shadow: none;
}

.default-model-select {
  width: 240px;
}

html.dark .settings-section,
html.dark .model-card,
html.dark .runtime-card {
  border-color: #22313a;
  background: #0f1b22;
}

html.dark .settings-section-head h4 {
  color: #dce7ef;
}

html.dark .settings-section-head p,
html.dark .settings-field span {
  color: #91a4b3;
}

html.dark .model-index {
  border-color: rgba(139, 217, 255, 0.28);
  background: #102638;
  color: #8bd9ff;
}

html.dark .model-badge,
html.dark .runtime-key {
  border-color: #2a3a45;
  background: #0a151b;
  color: #91a4b3;
}

html.dark .model-badge.is-ready {
  color: #7cf0a7;
}

html.dark .model-badge.is-warn {
  color: #ffd166;
}

html.dark .model-badge.is-active {
  color: #8bd9ff;
}

html.dark .settings-input :deep(.el-input__wrapper),
html.dark .settings-field :deep(.el-input__wrapper),
html.dark .default-model-select :deep(.el-select__wrapper) {
  border-color: #22313a;
  background: #0a151b;
  box-shadow: none;
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
