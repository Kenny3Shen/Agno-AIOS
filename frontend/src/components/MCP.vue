<template>
  <div class="mcp-console ag-page-flow">
    <section class="mcp-toolbar ag-content-panel">
      <div class="mcp-context">
        <DataChip
          v-for="metric in metrics"
          :key="metric.label"
          :label="metric.label"
          :value="metric.value"
          :title="metric.hint"
        />
        <DataChip class="max-w-[360px]" :label="t('mcp.context.clientUrl')" :value="clientUrl" :title="clientUrl" />
      </div>

      <el-button type="primary" :icon="Plus" class="mcp-toolbar-action" :disabled="!canWriteMcp" @click="uploadPanelOpen = !uploadPanelOpen">
        {{ t('mcp.upload.open') }}
      </el-button>
    </section>

    <main class="mcp-main">
      <section class="mcp-body ag-content-panel">
        <section v-if="uploadPanelOpen" class="mcp-panel mb-3">
          <PanelHeader :title="t('mcp.upload.title')" :subtitle="t('mcp.upload.description')" />
          <div class="mt-4 grid gap-3 md:grid-cols-2">
            <el-input v-model="uploadForm.name" :placeholder="t('mcp.upload.namePlaceholder')" />
            <el-input v-model="uploadForm.description" :placeholder="t('mcp.upload.descriptionPlaceholder')" />
            <label class="mcp-visibility-field">
              <span>{{ t('visibility.label') }}</span>
              <ResourceVisibilityTabs v-model="uploadForm.visibility" />
            </label>
            <el-input v-model="uploadForm.manifest" type="textarea" :rows="4" :placeholder="t('mcp.upload.manifestPlaceholder')" />
          </div>
          <div class="mt-3 flex justify-end gap-2">
            <el-button :disabled="submittingUpload" @click="cancelMcpUpload">
              {{ t('mcp.upload.cancel') }}
            </el-button>
            <el-button type="primary" :loading="submittingUpload" @click="submitMcpUpload">
              {{ t('mcp.upload.submit') }}
            </el-button>
          </div>
        </section>

          <el-tabs v-model="activeTab" class="mcp-tabs">
            <el-tab-pane :label="t('mcp.tabs.services')" name="services">
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
                      :disabled="!canWriteMcp"
                      active-color="var(--ag-blue)"
                      @change="(value: boolean) => toggleService(service, value)"
                    />
                  </div>
                  <div class="mt-4 flex items-center justify-between text-xs">
                    <span class="mcp-muted font-mono">{{ service.namespace }}</span>
                    <StatusChip :tone="service.enabled ? 'green' : 'muted'">
                      {{ service.enabled ? t('mcp.state.enabled') : t('mcp.state.disabled') }}
                    </StatusChip>
                  </div>
                </section>
              </div>
            </el-tab-pane>

            <el-tab-pane :label="t('mcp.tabs.servers')" name="servers">
              <EmptyState v-if="!mcpServers.length" class="min-h-[120px]">{{ t('mcp.servers.empty') }}</EmptyState>
              <div v-else class="grid gap-3 lg:grid-cols-2">
                <section v-for="server in mcpServers" :key="server.name" class="mcp-card">
                  <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0">
                      <strong>{{ server.name }}</strong>
                      <em>{{ server.description || server.kind }}</em>
                    </div>
                  </div>
                  <div class="mt-4 flex items-center justify-between gap-2 text-xs">
                    <span class="mcp-muted font-mono">{{ server.kind }}</span>
                    <ResourceVisibilityTabs
                      :model-value="server.visibility"
                      :aria-label="t('mcp.visibilityLabel', { name: server.name })"
                      :disabled="!canWriteMcp || !server.can_manage"
                      :loading="serverToggling === server.name"
                      @update:model-value="(visibility) => updateMcpServerVisibilityTab(server, visibility)"
                    />
                  </div>
                </section>
              </div>
            </el-tab-pane>

            <el-tab-pane :label="t('mcp.tabs.tokens')" name="tokens">
              <div class="grid gap-3 xl:grid-cols-[360px_minmax(0,1fr)]">
                <section class="mcp-panel">
                  <PanelHeader :title="t('mcp.tokens.issueTitle')" />
                  <div class="mt-4 space-y-3">
                    <el-input
                      v-model="tokenForm.name"
                      :disabled="!canWriteMcp"
                      :placeholder="t('mcp.tokens.namePlaceholder')"
                      clearable
                    />
                    <el-select v-model="tokenForm.expiresIn" class="w-full" :disabled="!canWriteMcp">
                      <el-option :label="t('mcp.tokens.expiry.oneDay')" :value="86400" />
                      <el-option :label="t('mcp.tokens.expiry.sevenDays')" :value="604800" />
                      <el-option :label="t('mcp.tokens.expiry.thirtyDays')" :value="2592000" />
                      <el-option :label="t('mcp.tokens.expiry.forever')" :value="0" />
                    </el-select>
                    <el-button
                      type="primary"
                      class="!w-full cursor-pointer"
                      :disabled="!canWriteMcp"
                      :loading="issuingToken"
                      @click="issueAccessToken"
                    >
                      <el-icon class="mr-1"><Plus /></el-icon>
                      {{ t('mcp.tokens.generate') }}
                    </el-button>
                  </div>

                  <div v-if="createdToken" class="token-reveal mt-4">
                    <div class="mcp-warning-copy mb-2 text-xs font-semibold">{{ t('mcp.tokens.copyOnce') }}</div>
                    <div class="flex gap-2">
                      <el-input :model-value="createdToken" readonly class="font-mono" />
                      <el-button class="cursor-pointer" @click="copyText(createdToken)">
                        <el-icon><CopyDocument /></el-icon>
                      </el-button>
                    </div>
                  </div>
                </section>

                <section class="mcp-panel min-w-0">
                  <PanelHeader class="mb-3 w-full" :title="t('mcp.tokens.issuedTitle')">
                    <template #actions>
                      <span class="mcp-muted text-xs">{{ t('mcp.count', { count: tokens.length }) }}</span>
                    </template>
                  </PanelHeader>

                  <div v-if="tokensLoading" class="mcp-muted py-10 text-center text-xs">{{ t('mcp.loading') }}</div>
                  <EmptyState v-else-if="!tokens.length" class="min-h-[120px]">{{ t('mcp.tokens.empty') }}</EmptyState>
                  <div v-else class="space-y-2">
                    <div v-for="token in tokens" :key="token.id" class="token-row">
                      <div class="min-w-0">
                        <div class="flex items-center gap-2">
                          <strong class="truncate">{{ token.name }}</strong>
                          <StatusChip :tone="isExpired(token.expires_at) ? 'red' : 'green'">
                            {{ isExpired(token.expires_at) ? t('mcp.state.expired') : t('mcp.state.active') }}
                          </StatusChip>
                        </div>
                        <div class="mcp-muted mt-1 grid gap-1 text-[11px] sm:grid-cols-2">
                          <span>{{ t('mcp.tokens.createdAt', { value: formatDate(token.created_at) }) }}</span>
                          <span>{{ t('mcp.tokens.expiresAt', { value: formatDate(token.expires_at) }) }}</span>
                        </div>
                      </div>
                      <el-button
                        class="cursor-pointer"
                        plain
                        type="danger"
                        :disabled="!canWriteMcp"
                        @click="deleteAccessToken(token.id)"
                      >
                        <el-icon><Delete /></el-icon>
                      </el-button>
                    </div>
                  </div>
                </section>
              </div>
            </el-tab-pane>
          </el-tabs>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, onMounted, reactive, ref, type Component } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useI18n } from "vue-i18n"
import {
  CopyDocument,
  Delete,
  Plus,
  Operation,
  Tools,
} from "@element-plus/icons-vue"
import { useMcpApi } from "../composables/useMcpApi"
import { copyToClipboard } from "../lib/clipboard"
import { useAuthStore } from "../stores/auth"
import type { McpServerInfo, McpServiceId, McpTokenInfo, ResourceVisibility } from "../types"
import DataChip from "./common/DataChip.vue"
import EmptyState from "./common/EmptyState.vue"
import PanelHeader from "./common/PanelHeader.vue"
import ResourceVisibilityTabs from "./common/ResourceVisibilityTabs.vue"
import StatusChip from "./common/StatusChip.vue"

type TabId = "services" | "servers" | "tokens"

type ServiceItem = {
  id: McpServiceId
  name: string
  description: string
  namespace: string
  enabled: boolean
  icon: Component
}

const activeTab = ref<TabId>("services")
const { t, locale } = useI18n()
const authStore = useAuthStore()
const serviceToggling = ref<McpServiceId | null>(null)
const serverToggling = ref<string | null>(null)
const tokens = ref<McpTokenInfo[]>([])
const mcpServers = ref<McpServerInfo[]>([])
const tokensLoading = ref(false)
const issuingToken = ref(false)
const uploadPanelOpen = ref(false)
const submittingUpload = ref(false)
const createdToken = ref("")
const mcpUrl = ref("/mcp/")

const services = ref<ServiceItem[]>([
  { id: "playbook", name: "SOAR", description: t("mcp.services.playbook"), namespace: "playbook.*", enabled: false, icon: markRaw(Operation) },
  { id: "basic", name: t("mcp.services.basicName"), description: t("mcp.services.basic"), namespace: "basic.*", enabled: false, icon: markRaw(Tools) },
])

const tokenForm = reactive({
  name: "",
  expiresIn: 604800,
})

const uploadForm = reactive({
  name: "",
  description: "",
  manifest: "",
  visibility: "private" as ResourceVisibility,
})

const {
  fetchConfig,
  updateConfig,
  listTokens,
  issueToken,
  deleteToken,
  uploadMcp,
  updateMcpServerVisibility,
} = useMcpApi()

const enabledCount = computed(() => services.value.filter((service) => service.enabled).length)
const activeTokenCount = computed(() => tokens.value.filter((token) => !isExpired(token.expires_at)).length)
const canWriteMcp = computed(() => authStore.hasScope("mcp:write"))

const metrics = computed(() => [
  { label: t("mcp.metricLabels.services"), value: `${enabledCount.value}/${services.value.length}`, hint: t("mcp.metrics.enabledServices") },
  { label: t("mcp.metricLabels.tokens"), value: activeTokenCount.value, hint: t("mcp.metrics.activeTokens") },
])

const clientUrl = computed(() => `${mcpUrl.value}?token=YOUR_ACCESS_TOKEN`)

const loadConfig = async () => {
  const data = await fetchConfig()
  services.value = services.value.map((service) => ({
    ...service,
    enabled: Boolean(data.services[service.id]),
  }))
  mcpServers.value = data.mcp_servers || []
  mcpUrl.value = data.mcp_url || "/mcp/"
}

const loadTokens = async () => {
  tokensLoading.value = true
  try {
    tokens.value = await listTokens()
  } finally {
    tokensLoading.value = false
  }
}

const loadAll = async () => {
  try {
    await Promise.all([loadConfig(), loadTokens()])
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("mcp.messages.loadFailed"))
  }
}

const toggleService = async (service: ServiceItem, enabled: boolean) => {
  if (!canWriteMcp.value) return
  const previous = service.enabled
  serviceToggling.value = service.id
  service.enabled = enabled
  try {
    const result = await updateConfig(service.id, enabled)
    ElMessage.success(
      result.restart_required
        ? t("mcp.messages.serviceSavedRestart", { name: service.name })
        : t("mcp.messages.serviceToggled", { name: service.name, state: enabled ? t("common.state.enabled") : t("common.state.disabled") })
    )
  } catch (err) {
    service.enabled = previous
    ElMessage.error(err instanceof Error ? err.message : t("mcp.messages.updateServiceFailed"))
  } finally {
    serviceToggling.value = null
  }
}

const issueAccessToken = async () => {
  if (!canWriteMcp.value) return
  issuingToken.value = true
  createdToken.value = ""
  try {
    const data = await issueToken(tokenForm.name.trim() || t("mcp.tokens.defaultName"), tokenForm.expiresIn)
    createdToken.value = data.token
    await loadTokens()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("mcp.messages.issueTokenFailed"))
  } finally {
    issuingToken.value = false
  }
}

const deleteAccessToken = async (id: number) => {
  if (!canWriteMcp.value) return
  try {
    await ElMessageBox.confirm(t("mcp.confirm.deleteTokenMessage"), t("mcp.confirm.deleteTokenTitle"), {
      confirmButtonText: t("common.actions.delete"),
      cancelButtonText: t("common.actions.cancel"),
      type: "warning",
    })
    await deleteToken(id)
    await loadTokens()
    ElMessage.success(t("mcp.messages.tokenDeleted"))
  } catch (err) {
    if (err !== "cancel") {
      ElMessage.error(err instanceof Error ? err.message : t("mcp.messages.deleteTokenFailed"))
    }
  }
}

const resetMcpUpload = () => {
  uploadForm.name = ""
  uploadForm.description = ""
  uploadForm.manifest = ""
  uploadForm.visibility = "private"
}

const cancelMcpUpload = () => {
  resetMcpUpload()
  uploadPanelOpen.value = false
}

const submitMcpUpload = async () => {
  if (!uploadForm.name.trim()) {
    ElMessage.warning(t("mcp.messages.uploadNameRequired"))
    return
  }
  if (!uploadForm.manifest.trim()) {
    ElMessage.warning(t("mcp.messages.uploadTargetRequired"))
    return
  }
  submittingUpload.value = true
  try {
    await uploadMcp({
      name: uploadForm.name.trim(),
      description: uploadForm.description.trim(),
      manifest: uploadForm.manifest,
      visibility: uploadForm.visibility,
    })
    resetMcpUpload()
    uploadPanelOpen.value = false
    await loadConfig()
    ElMessage.success(t("mcp.messages.uploadSubmitted"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("mcp.messages.uploadFailed"))
  } finally {
    submittingUpload.value = false
  }
}

const updateMcpServerVisibilityTab = async (server: McpServerInfo, visibility: ResourceVisibility) => {
  if (!canWriteMcp.value || !server.can_manage) return
  if (visibility === server.visibility) return
  serverToggling.value = server.name
  try {
    const result = await updateMcpServerVisibility(server.name, visibility)
    server.visibility = result.visibility
    ElMessage.success(t("visibility.updated"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("visibility.updateFailed"))
  } finally {
    serverToggling.value = null
  }
}

const formatDate = (timestamp: number) => {
  if (!timestamp) return t("mcp.tokens.neverExpires")
  return new Date(timestamp * 1000).toLocaleString(locale.value, {
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
  if (await copyToClipboard(text)) {
    ElMessage.success(t("common.clipboard.copied"))
  } else {
    ElMessage.warning(t("common.clipboard.failed"))
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

.mcp-main {
  display: flex;
  flex-direction: column;
  gap: var(--ag-section-gap);
}

.mcp-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.mcp-context {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  gap: 8px;
}

.mcp-toolbar-action {
  flex: 0 0 auto;
}

.mcp-card-icon {
  display: grid;
  place-items: center;
  border: 1px solid color-mix(in srgb, var(--ag-blue) 36%, var(--ag-border));
  border-radius: var(--ag-radius-panel);
  background: var(--ag-blue-soft);
  color: var(--ag-blue);
}

.mcp-card-icon {
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
}

.mcp-body {
  display: block;
}

.mcp-visibility-field {
  display: grid;
  gap: 7px;
  min-width: 0;
}

.mcp-visibility-field > span {
  color: var(--ag-muted);
  font-size: 12px;
  font-weight: 700;
}

.mcp-card,
.mcp-panel,
.token-row,
.agent-row {
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-panel);
  background: var(--ag-panel);
}

.mcp-card,
.mcp-panel {
  padding: 12px;
}

.mcp-card.disabled {
  opacity: 0.72;
}

.mcp-card strong,
.token-row strong,
.agent-row strong {
  color: var(--ag-heading);
  font-size: 13px;
  font-weight: 700;
}

.mcp-card em {
  display: block;
  margin-top: 3px;
  color: var(--ag-muted);
  font-size: 12px;
  font-style: normal;
}

.mcp-muted {
  color: var(--ag-muted);
}

.mcp-url {
  color: var(--ag-muted-strong);
}

.mcp-warning-copy {
  color: var(--ag-yellow);
}

.token-reveal {
  border: 1px solid var(--ag-yellow);
  border-radius: var(--ag-radius-panel);
  background: var(--ag-yellow-soft);
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

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

@media (max-width: 640px) {
  .mcp-toolbar {
    display: grid;
    grid-template-columns: 1fr;
    align-items: stretch;
  }

  .mcp-context,
  .mcp-toolbar-action {
    width: 100%;
  }

  .mcp-context {
    display: grid;
  }
}

</style>
