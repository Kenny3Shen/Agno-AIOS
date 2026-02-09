<template>
  <div class="max-w-2xl mx-auto space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h3 class="text-lg font-semibold text-slate-900 dark:text-[#C9D1D9]">系统配置</h3>
        <p class="text-sm text-slate-500 dark:text-[#8B949E] mt-1">运行时环境变量配置，修改后立即生效</p>
      </div>
      <el-button
        type="primary"
        :loading="saving"
        :disabled="!hasChanges"
        @click="saveSettings"
        class="cursor-pointer"
      >
        <el-icon class="mr-1"><Check /></el-icon>
        保存
      </el-button>
    </div>

    <!-- 加载状态 -->
    <div v-if="loadingSettings" class="flex justify-center py-12">
      <el-icon class="is-loading text-2xl text-slate-400"><Loading /></el-icon>
    </div>

    <!-- 配置表单 -->
    <div v-else class="space-y-4">
      <div
        v-for="item in configItems"
        :key="item.key"
        class="p-4 rounded-xl border border-[#D0D7DE] dark:border-[#30363D] bg-white dark:bg-[#161B22] transition-colors"
      >
        <div class="flex items-center justify-between mb-2">
          <div>
            <label class="text-sm font-medium text-slate-800 dark:text-[#C9D1D9]">{{ item.label }}</label>
            <p class="text-xs text-slate-500 dark:text-[#8B949E]">{{ item.description }}</p>
          </div>
          <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 dark:bg-[#0D1117] text-slate-500 dark:text-[#8B949E] border border-[#D0D7DE] dark:border-[#30363D]">
            {{ item.key }}
          </span>
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

    <!-- 提示 -->
    <div class="text-xs text-slate-400 dark:text-[#484F58] p-3 rounded-lg bg-slate-50 dark:bg-[#0D1117] border border-[#D0D7DE] dark:border-[#30363D]">
      注意：配置修改仅在运行时生效，服务重启后将恢复环境变量默认值。敏感字段已做脱敏处理，未修改的字段不会被覆盖。
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from "vue"
import { Check, Loading } from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"
import { useSettingsApi } from "../composables/useApi"

interface ConfigItem {
  key: string
  label: string
  description: string
  placeholder: string
  secret: boolean
}

const configItems: ConfigItem[] = [
  {
    key: "LLM_API_KEY",
    label: "LLM API Key",
    description: "大语言模型的 API 密钥",
    placeholder: "sk-...",
    secret: true,
  },
  {
    key: "LLM_URL",
    label: "LLM Base URL",
    description: "大语言模型 API 基础地址",
    placeholder: "https://api.openai.com/v1",
    secret: false,
  },
  {
    key: "LLM_EP",
    label: "LLM Endpoint / Model",
    description: "使用的模型名称或端点",
    placeholder: "gpt-4o",
    secret: false,
  },
  {
    key: "MCP_TOKEN",
    label: "MCP Token",
    description: "MCP 服务器认证令牌",
    placeholder: "token-...",
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

const { loadingSettings, saving, fetchSettings, updateSettings } = useSettingsApi()

const formData = reactive<Record<string, string>>({})
const originalData = ref<Record<string, string>>({})

const hasChanges = computed(() => {
  return configItems.some((item) => formData[item.key] !== originalData.value[item.key])
})

const loadSettings = async () => {
  try {
    const data = await fetchSettings()
    for (const item of configItems) {
      formData[item.key] = data[item.key] || ""
      originalData.value[item.key] = data[item.key] || ""
    }
  } catch {
    ElMessage.error("加载配置失败")
  }
}

const saveSettings = async () => {
  try {
    const changed: Record<string, string> = {}
    for (const item of configItems) {
      const currentVal = formData[item.key]
      if (currentVal !== originalData.value[item.key]) {
        changed[item.key] = currentVal ?? ""
      }
    }
    if (Object.keys(changed).length === 0) return

    const data = await updateSettings(changed)
    for (const item of configItems) {
      const newVal = data[item.key]
      if (newVal !== undefined) {
        formData[item.key] = newVal
        originalData.value[item.key] = newVal
      }
    }
    ElMessage.success("配置已保存")
  } catch {
    ElMessage.error("保存配置失败")
  }
}

onMounted(() => { loadSettings() })
</script>

<style scoped>
.settings-input :deep(.el-input__wrapper) {
  border-radius: 8px;
}
</style>
