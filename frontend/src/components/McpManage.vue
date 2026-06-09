<template>
  <div class="mcp-console h-full min-h-0 overflow-hidden bg-[#F5F7FA] text-[#15202B] dark:bg-[#071014] dark:text-[#DCE7EF]">
    <div class="grid h-full min-h-0 grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px]">
      <main class="flex min-h-0 flex-col overflow-hidden">
        <header class="border-b border-[#D8E0E7] bg-white/90 p-3 dark:border-[#22313A] dark:bg-[#0A151B]">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center gap-3">
              <div class="mcp-core">
                <el-icon><Connection /></el-icon>
              </div>
              <div>
                <h3 class="text-sm font-semibold text-[#15202B] dark:text-white">MCP 工具中枢</h3>
                <p class="mt-1 text-xs text-[#6B7C8A] dark:text-[#91A4B3]">
                  基于 FastMCP 的服务控制、访问 Token 与外部 Hi-Agent 接入
                </p>
              </div>
            </div>

            <div class="flex items-center gap-2">
              <el-button type="primary" :loading="loading" class="cursor-pointer" @click="loadAll">
                <el-icon class="mr-1"><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </div>

          <div class="mt-3 grid gap-2 md:grid-cols-4">
            <div v-for="metric in metrics" :key="metric.label" class="mcp-metric">
              <span>{{ metric.label }}</span>
              <strong>{{ metric.value }}</strong>
              <em>{{ metric.hint }}</em>
            </div>
          </div>
        </header>

        <div class="min-h-0 flex-1 overflow-y-auto p-3">
          <el-tabs v-model="activeTab" class="mcp-tabs">
            <el-tab-pane label="服务能力" name="services">
              <div class="grid gap-3 lg:grid-cols-3">
                <section
                  v-for="service in services"
                  :key="service.id"
                  class="mcp-card"
                  :class="{ disabled: !service.enabled }"
                >
                  <div class="flex items-start justify-between gap-3">
                    <div class="flex min-w-0 items-center gap-3">
                      <span class="mcp-card-icon">
                        <el-icon><component :is="service.icon" /></el-icon>
                      </span>
                      <span class="min-w-0">
                        <strong>{{ service.name }}</strong>
                        <em>{{ service.description }}</em>
                      </span>
                    </div>
                    <el-switch
                      :model-value="service.enabled"
                      :loading="serviceToggling === service.id"
                      active-color="#2F8FED"
                      @change="(value: boolean) => toggleService(service, value)"
                    />
                  </div>
                  <div class="mt-4 flex items-center justify-between text-xs">
                    <span class="font-mono text-[#6B7C8A] dark:text-[#91A4B3]">{{ service.namespace }}</span>
                    <span class="status-pill" :class="service.enabled ? 'ok' : 'off'">
                      {{ service.enabled ? 'Enabled' : 'Disabled' }}
                    </span>
                  </div>
                </section>
              </div>
            </el-tab-pane>

            <el-tab-pane label="访问 Token" name="tokens">
              <div class="grid gap-3 xl:grid-cols-[360px_minmax(0,1fr)]">
                <section class="mcp-panel">
                  <div class="panel-title">
                    <el-icon><Key /></el-icon>
                    签发访问 Token
                  </div>
                  <div class="mt-4 space-y-3">
                    <el-input v-model="tokenForm.name" placeholder="Token 名称，例如 AgentOS" clearable />
                    <el-select v-model="tokenForm.expiresIn" class="w-full">
                      <el-option label="1 天" :value="86400" />
                      <el-option label="7 天" :value="604800" />
                      <el-option label="30 天" :value="2592000" />
                      <el-option label="永久" :value="0" />
                    </el-select>
                    <el-button type="primary" class="!w-full cursor-pointer" :loading="issuingToken" @click="issueAccessToken">
                      <el-icon class="mr-1"><Plus /></el-icon>
                      生成 Token
                    </el-button>
                  </div>

                  <div v-if="createdToken" class="token-reveal mt-4">
                    <div class="mb-2 text-xs font-semibold text-[#B7791F] dark:text-[#F6C343]">仅显示一次，请立即复制</div>
                    <div class="flex gap-2">
                      <el-input :model-value="createdToken" readonly class="font-mono" />
                      <el-button class="cursor-pointer" @click="copyText(createdToken)">
                        <el-icon><CopyDocument /></el-icon>
                      </el-button>
                    </div>
                  </div>
                </section>

                <section class="mcp-panel min-w-0">
                  <div class="mb-3 flex items-center justify-between">
                    <div class="panel-title">
                      <el-icon><Tickets /></el-icon>
                      已签发 Token
                    </div>
                    <span class="text-xs text-[#6B7C8A] dark:text-[#91A4B3]">{{ tokens.length }} 个</span>
                  </div>

                  <div v-if="tokensLoading" class="py-10 text-center text-xs text-[#6B7C8A] dark:text-[#91A4B3]">加载中...</div>
                  <div v-else-if="!tokens.length" class="empty-box">暂无访问 Token</div>
                  <div v-else class="space-y-2">
                    <div v-for="token in tokens" :key="token.id" class="token-row">
                      <div class="min-w-0">
                        <div class="flex items-center gap-2">
                          <strong class="truncate">{{ token.name }}</strong>
                          <span class="status-pill" :class="isExpired(token.expires_at) ? 'bad' : 'ok'">
                            {{ isExpired(token.expires_at) ? 'Expired' : 'Active' }}
                          </span>
                        </div>
                        <div class="mt-1 grid gap-1 text-[11px] text-[#6B7C8A] dark:text-[#91A4B3] sm:grid-cols-2">
                          <span>创建：{{ formatDate(token.created_at) }}</span>
                          <span>过期：{{ formatDate(token.expires_at) }}</span>
                        </div>
                      </div>
                      <el-button class="cursor-pointer" plain type="danger" @click="deleteAccessToken(token.id)">
                        <el-icon><Delete /></el-icon>
                      </el-button>
                    </div>
                  </div>
                </section>
              </div>
            </el-tab-pane>

            <el-tab-pane label="Hi-Agent" name="hiagent">
              <div class="grid gap-3 xl:grid-cols-[360px_minmax(0,1fr)]">
                <section class="mcp-panel">
                  <div class="panel-title">
                    <el-icon><Cpu /></el-icon>
                    注册外部 MCP
                  </div>
                  <div class="mt-4 space-y-3">
                    <el-input v-model="hiAgentForm.name" placeholder="名称，例如 CVE Hunter" clearable />
                    <el-input v-model="hiAgentForm.url" placeholder="MCP URL" clearable />
                    <el-input v-model="hiAgentForm.description" type="textarea" :rows="3" placeholder="能力描述" />
                    <el-switch v-model="hiAgentForm.enabled" active-text="启用" inactive-text="禁用" />
                    <el-button type="primary" class="!w-full cursor-pointer" :loading="addingHiAgent" @click="addExternalAgent">
                      <el-icon class="mr-1"><Plus /></el-icon>
                      注册 Hi-Agent
                    </el-button>
                  </div>
                </section>

                <section class="mcp-panel min-w-0">
                  <div class="mb-3 flex items-center justify-between">
                    <div class="panel-title">
                      <el-icon><SetUp /></el-icon>
                      已接入 Agent
                    </div>
                    <span class="text-xs text-[#6B7C8A] dark:text-[#91A4B3]">{{ hiAgents.length }} 个</span>
                  </div>

                  <div v-if="hiAgentLoading" class="py-10 text-center text-xs text-[#6B7C8A] dark:text-[#91A4B3]">加载中...</div>
                  <div v-else-if="!hiAgents.length" class="empty-box">暂无 Hi-Agent MCP</div>
                  <div v-else class="space-y-2">
                    <div v-for="agent in hiAgents" :key="agent.url" class="agent-row">
                      <div class="min-w-0 flex-1">
                        <div class="flex items-center gap-2">
                          <strong class="truncate">{{ agent.name }}</strong>
                          <span class="status-pill" :class="agent.enabled ? 'ok' : 'off'">
                            {{ agent.enabled ? 'Enabled' : 'Disabled' }}
                          </span>
                        </div>
                        <p v-if="agent.description" class="mt-1 line-clamp-2 text-xs text-[#6B7C8A] dark:text-[#91A4B3]">{{ agent.description }}</p>
                        <p class="mt-1 truncate font-mono text-[11px] text-[#8A99A6]">{{ agent.url }}</p>
                      </div>
                      <div class="flex shrink-0 items-center gap-2">
                        <el-switch
                          :model-value="agent.enabled"
                          active-color="#2F8FED"
                          @change="(value: boolean) => toggleHiAgent(agent, value)"
                        />
                        <el-button class="cursor-pointer" plain type="danger" @click="deleteExternalAgent(agent.url)">
                          <el-icon><Delete /></el-icon>
                        </el-button>
                      </div>
                    </div>
                  </div>
                </section>
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>
      </main>

      <aside class="hidden min-h-0 border-l border-[#D8E0E7] bg-white/85 p-3 xl:block dark:border-[#22313A] dark:bg-[#0A151B]">
        <section class="mcp-panel">
          <div class="panel-title">
            <el-icon><DataLine /></el-icon>
            接入说明
          </div>
          <dl class="mt-4 space-y-3 text-xs">
            <div class="context-row">
              <dt>管理入口</dt>
              <dd>{{ controlInfo.controlMode }}</dd>
            </div>
            <div class="context-row">
              <dt>FastMCP</dt>
              <dd>{{ controlInfo.fastmcp }}</dd>
            </div>
            <div class="context-row">
              <dt>Config</dt>
              <dd :title="controlInfo.configPath">{{ controlInfo.configPath }}</dd>
            </div>
            <div class="context-row">
              <dt>Token DB</dt>
              <dd :title="controlInfo.tokensDbPath">{{ controlInfo.tokensDbPath }}</dd>
            </div>
          </dl>
        </section>

        <section class="mcp-panel mt-3">
          <div class="panel-title">
            <el-icon><Link /></el-icon>
            Client URL
          </div>
          <p class="mt-3 break-all rounded-lg border border-[#D8E0E7] bg-white p-3 font-mono text-[11px] text-[#526170] dark:border-[#22313A] dark:bg-[#071014] dark:text-[#91A4B3]">
            {{ clientUrl }}
          </p>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, type Component } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import {
  Connection,
  CopyDocument,
  Cpu,
  DataLine,
  Delete,
  Key,
  Link,
  Plus,
  Refresh,
  SetUp,
  Tickets,
  Operation,
  Tools,
} from "@element-plus/icons-vue"
import { useMcpApi } from "../composables/useApi"
import type { HiAgentEntry, McpServiceId, McpTokenInfo } from "../types"

type TabId = "services" | "tokens" | "hiagent"

type ServiceItem = {
  id: McpServiceId
  name: string
  description: string
  namespace: string
  enabled: boolean
  icon: Component
}

const activeTab = ref<TabId>("services")
const serviceToggling = ref<McpServiceId | null>(null)
const tokens = ref<McpTokenInfo[]>([])
const hiAgents = ref<HiAgentEntry[]>([])
const tokensLoading = ref(false)
const hiAgentLoading = ref(false)
const issuingToken = ref(false)
const addingHiAgent = ref(false)
const createdToken = ref("")
const controlInfo = reactive({
  controlMode: "integrated",
  fastmcp: "in-process",
  mcpUrl: "/mcp/",
  configPath: "tmp/mcp/mcp_config.toml",
  tokensDbPath: "mysql:mcp_tokens",
})

const services = ref<ServiceItem[]>([
  { id: "playbook", name: "SOAR 剧本", description: "安全剧本编排与处置执行", namespace: "playbook.*", enabled: false, icon: Operation },
  { id: "agent", name: "AI Agent", description: "Agent API 与外部智能体调用", namespace: "agent.*", enabled: false, icon: Cpu },
  { id: "basic", name: "基础工具", description: "飞书通知、通用辅助工具", namespace: "basic.*", enabled: false, icon: Tools },
])

const tokenForm = reactive({
  name: "",
  expiresIn: 604800,
})

const hiAgentForm = reactive<HiAgentEntry>({
  name: "",
  url: "",
  description: "",
  enabled: true,
})

const {
  loading,
  fetchConfig,
  updateConfig,
  listTokens,
  issueToken,
  deleteToken,
  listHiAgents,
  addHiAgent,
  updateHiAgent,
  deleteHiAgent,
} = useMcpApi()

const enabledCount = computed(() => services.value.filter((service) => service.enabled).length)
const activeTokenCount = computed(() => tokens.value.filter((token) => !isExpired(token.expires_at)).length)

const metrics = computed(() => [
  { label: "MCP Services", value: `${enabledCount.value}/${services.value.length}`, hint: "启用能力数" },
  { label: "Access Tokens", value: activeTokenCount.value, hint: "可用访问凭证" },
  { label: "Hi-Agent", value: hiAgents.value.filter((agent) => agent.enabled).length, hint: "已启用外部 MCP" },
  { label: "Control", value: "Integrated", hint: "同进程 FastMCP" },
])

const clientUrl = computed(() => `${controlInfo.mcpUrl}?token=YOUR_ACCESS_TOKEN`)

const loadConfig = async () => {
  const data = await fetchConfig()
  services.value = services.value.map((service) => ({
    ...service,
    enabled: Boolean(data.services[service.id]),
  }))
  controlInfo.controlMode = data.control_mode || "integrated"
  controlInfo.fastmcp = data.fastmcp || "in-process"
  controlInfo.mcpUrl = data.mcp_url || "/mcp/"
  controlInfo.configPath = data.config_path || "tmp/mcp/mcp_config.toml"
  controlInfo.tokensDbPath = data.tokens_db_path || "mysql:mcp_tokens"
}

const loadTokens = async () => {
  tokensLoading.value = true
  try {
    tokens.value = await listTokens()
  } finally {
    tokensLoading.value = false
  }
}

const loadHiAgents = async () => {
  hiAgentLoading.value = true
  try {
    hiAgents.value = await listHiAgents()
  } finally {
    hiAgentLoading.value = false
  }
}

const loadAll = async () => {
  try {
    await Promise.all([loadConfig(), loadTokens(), loadHiAgents()])
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "加载 MCP 数据失败")
  }
}

const toggleService = async (service: ServiceItem, enabled: boolean) => {
  const previous = service.enabled
  serviceToggling.value = service.id
  service.enabled = enabled
  try {
    const result = await updateConfig(service.id, enabled)
    ElMessage.success(
      result.restart_required
        ? `${service.name} 配置已保存，重启主 API 后生效`
        : `${service.name} 已${enabled ? "启用" : "禁用"}`
    )
  } catch (err) {
    service.enabled = previous
    ElMessage.error(err instanceof Error ? err.message : "更新服务状态失败")
  } finally {
    serviceToggling.value = null
  }
}

const issueAccessToken = async () => {
  issuingToken.value = true
  createdToken.value = ""
  try {
    const data = await issueToken(tokenForm.name.trim() || "Agno AIOS", tokenForm.expiresIn)
    createdToken.value = data.token
    await loadTokens()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "生成 Token 失败")
  } finally {
    issuingToken.value = false
  }
}

const deleteAccessToken = async (id: number) => {
  try {
    await ElMessageBox.confirm("删除后使用该 Token 的 MCP Client 将无法连接。", "删除 Token", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    })
    await deleteToken(id)
    await loadTokens()
    ElMessage.success("Token 已删除")
  } catch (err) {
    if (err !== "cancel") {
      ElMessage.error(err instanceof Error ? err.message : "删除 Token 失败")
    }
  }
}

const addExternalAgent = async () => {
  if (!hiAgentForm.name.trim() || !hiAgentForm.url.trim()) {
    ElMessage.warning("名称和 MCP URL 不能为空")
    return
  }
  addingHiAgent.value = true
  try {
    await addHiAgent({
      name: hiAgentForm.name.trim(),
      url: hiAgentForm.url.trim(),
      description: hiAgentForm.description.trim(),
      enabled: hiAgentForm.enabled,
    })
    hiAgentForm.name = ""
    hiAgentForm.url = ""
    hiAgentForm.description = ""
    hiAgentForm.enabled = true
    await loadHiAgents()
    ElMessage.success("Hi-Agent 已注册")
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "注册 Hi-Agent 失败")
  } finally {
    addingHiAgent.value = false
  }
}

const toggleHiAgent = async (entry: HiAgentEntry, enabled: boolean) => {
  const previous = entry.enabled
  entry.enabled = enabled
  try {
    await updateHiAgent({ url: entry.url, enabled })
  } catch (err) {
    entry.enabled = previous
    ElMessage.error(err instanceof Error ? err.message : "切换 Hi-Agent 失败")
  }
}

const deleteExternalAgent = async (url: string) => {
  try {
    await ElMessageBox.confirm("确认删除该 Hi-Agent MCP 接入？", "删除 Hi-Agent", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    })
    await deleteHiAgent(url)
    await loadHiAgents()
    ElMessage.success("Hi-Agent 已删除")
  } catch (err) {
    if (err !== "cancel") {
      ElMessage.error(err instanceof Error ? err.message : "删除 Hi-Agent 失败")
    }
  }
}

const formatDate = (timestamp: number) => {
  if (!timestamp) return "永不过期"
  return new Date(timestamp * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

const isExpired = (timestamp: number) => {
  return Boolean(timestamp && timestamp < Date.now() / 1000)
}

const copyText = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success("已复制")
  } catch {
    ElMessage.warning("复制失败")
  }
}

onMounted(() => {
  loadAll()
})
</script>

<style>
.mcp-console {
  font-family: "Fira Sans", "Microsoft YaHei", sans-serif;
}

.mcp-core,
.mcp-card-icon {
  display: grid;
  place-items: center;
  border: 1px solid rgba(47, 143, 237, 0.35);
  border-radius: 8px;
  background: #eaf5ff;
  color: #0969da;
}

.mcp-core {
  width: 40px;
  height: 40px;
}

.mcp-card-icon {
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
}

.mcp-metric,
.mcp-card,
.mcp-panel,
.token-row,
.agent-row {
  border: 1px solid #d8e0e7;
  border-radius: 8px;
  background: #ffffff;
}

.mcp-metric {
  padding: 10px;
}

.mcp-metric span,
.mcp-metric em {
  display: block;
  color: #6b7c8a;
  font-size: 11px;
  font-style: normal;
}

.mcp-metric strong {
  display: block;
  margin-top: 3px;
  color: #15202b;
  font-size: 16px;
  font-weight: 700;
}

.mcp-card,
.mcp-panel {
  padding: 14px;
}

.mcp-card.disabled {
  opacity: 0.72;
}

.mcp-card strong,
.token-row strong,
.agent-row strong,
.panel-title {
  color: #15202b;
  font-size: 13px;
  font-weight: 700;
}

.mcp-card em {
  display: block;
  margin-top: 3px;
  color: #6b7c8a;
  font-size: 12px;
  font-style: normal;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.token-reveal {
  border: 1px solid #f6c343;
  border-radius: 8px;
  background: #fff8e5;
  padding: 12px;
}

.token-row,
.agent-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
}

.status-pill {
  display: inline-flex;
  border: 1px solid #d8e0e7;
  border-radius: 999px;
  padding: 1px 7px;
  font-size: 10px;
  font-weight: 700;
}

.status-pill.ok {
  border-color: rgba(84, 211, 138, 0.35);
  background: rgba(84, 211, 138, 0.1);
  color: #14824a;
}

.status-pill.off {
  color: #6b7c8a;
}

.status-pill.bad {
  border-color: rgba(240, 106, 106, 0.35);
  background: rgba(240, 106, 106, 0.1);
  color: #cf3c3c;
}

.empty-box {
  border: 1px dashed #d8e0e7;
  border-radius: 8px;
  padding: 36px;
  color: #6b7c8a;
  font-size: 12px;
  text-align: center;
}

.context-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.context-row dt {
  color: #6b7c8a;
}

.context-row dd {
  max-width: 160px;
  overflow: hidden;
  color: #15202b;
  font-family: "Fira Code", monospace;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

html.dark .mcp-core,
html.dark .mcp-card-icon {
  border-color: rgba(139, 217, 255, 0.28);
  background: #102638;
  color: #8bd9ff;
}

html.dark .mcp-metric,
html.dark .mcp-card,
html.dark .mcp-panel,
html.dark .token-row,
html.dark .agent-row {
  border-color: #22313a;
  background: #0f1b22;
}

html.dark .mcp-metric span,
html.dark .mcp-metric em,
html.dark .mcp-card em,
html.dark .context-row dt {
  color: #758998;
}

html.dark .mcp-metric strong,
html.dark .mcp-card strong,
html.dark .token-row strong,
html.dark .agent-row strong,
html.dark .panel-title,
html.dark .context-row dd {
  color: #dce7ef;
}

html.dark .token-reveal {
  border-color: rgba(246, 195, 67, 0.45);
  background: rgba(246, 195, 67, 0.08);
}

html.dark .empty-box {
  border-color: #22313a;
  color: #758998;
}
</style>
