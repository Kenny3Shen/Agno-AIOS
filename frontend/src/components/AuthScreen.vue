<template>
  <main class="auth-screen">
    <section class="auth-card" aria-label="Agno AIOS 认证入口">
      <div class="auth-panel">
        <div class="auth-brand">
          <span class="auth-logo">
            <el-icon><Platform /></el-icon>
          </span>
          <div>
            <h1>Agno AIOS</h1>
            <p>AI 信息安全中台</p>
          </div>
        </div>

        <div class="auth-tabs" role="tablist" aria-label="认证方式">
          <button
            type="button"
            :class="{ active: mode === 'login' }"
            role="tab"
            :aria-selected="mode === 'login'"
            @click="mode = 'login'"
          >
            登录
          </button>
          <button
            type="button"
            :class="{ active: mode === 'register' }"
            role="tab"
            :aria-selected="mode === 'register'"
            @click="mode = 'register'"
          >
            注册
          </button>
        </div>

        <form class="auth-form" @submit.prevent="submitAuth">
          <label class="auth-field">
            <span>邮箱</span>
            <el-input
              v-model="email"
              autocomplete="email"
              clearable
              placeholder="operator@example.com"
              size="large"
            />
          </label>

          <label class="auth-field">
            <span>密码</span>
            <el-input
              v-model="password"
              autocomplete="current-password"
              placeholder="至少 8 位"
              show-password
              size="large"
              type="password"
            />
          </label>

          <el-alert
            v-if="errorMessage"
            :title="errorMessage"
            class="auth-alert"
            show-icon
            type="error"
          />

          <el-button
            class="auth-submit"
            native-type="submit"
            size="large"
            type="primary"
            :loading="submitting"
          >
            {{ mode === 'login' ? '进入工作台' : '创建账号并进入' }}
          </el-button>
        </form>

        <div v-if="oauthProviders.length" class="auth-oauth">
          <span>也可以使用 OAuth 登录</span>
          <div>
            <el-button
              v-for="provider in oauthProviders"
              :key="provider"
              class="oauth-button"
              :loading="oauthLoading === provider"
              @click="startOAuth(provider)"
            >
              {{ providerLabel(provider) }}
            </el-button>
          </div>
        </div>

        <div class="auth-footer">
          <span>JWT 认证</span>
          <span>PgVector 知识库</span>
          <span>MCP 工具链</span>
        </div>
      </div>

      <aside class="lineage-panel" aria-label="平台能力矩阵">
        <div class="lineage-header">
          <span>Security data fabric</span>
          <button
            type="button"
            class="theme-chip"
            :aria-label="isDark ? '切换到浅色模式' : '切换到深色模式'"
            @click="$emit('toggle-theme')"
          >
            <el-icon>
              <Sunny v-if="isDark" />
              <Moon v-else />
            </el-icon>
          </button>
        </div>

        <div class="lineage-grid">
          <span
            v-for="cell in lineageCells"
            :key="cell.label"
            class="lineage-cell"
            :class="cell.tone"
          >
            <strong>{{ cell.value }}</strong>
            <em>{{ cell.label }}</em>
          </span>
        </div>

        <div class="risk-rail">
          <div v-for="item in riskRails" :key="item.label">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
            <i :style="{ width: item.width }" />
          </div>
        </div>

        <div class="auth-copy">
          <h2>把数据治理、漏洞情报和 Agent 响应收束到同一个控制面。</h2>
          <p>
            登录后进入面向 SOC 的中台工作区：资产画像、CVE 情报、RAG 知识、Trace 观测和 MCP 工具统一编排。
          </p>
        </div>
      </aside>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Moon, Platform, Sunny } from '@element-plus/icons-vue'
import {
  clearStoredAuthToken,
  fetchCurrentUser,
  fetchOAuthProviders,
  loginWithPassword,
  registerWithPassword,
  requestOAuthAuthorization,
  storeAuthToken,
} from '../lib/authClient'
import type { AuthUser, OAuthProvider } from '../types'

defineProps<{
  isDark: boolean
}>()

const emit = defineEmits<{
  authenticated: [user: AuthUser]
  'toggle-theme': []
}>()

type AuthMode = 'login' | 'register'

const mode = ref<AuthMode>('login')
const email = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const oauthProviders = ref<OAuthProvider[]>([])
const oauthLoading = ref<OAuthProvider | ''>('')

const lineageCells = [
  { label: '资产面', value: 'ASM', tone: 'blue' },
  { label: '漏洞情报', value: 'CVE', tone: 'red' },
  { label: '知识切片', value: 'RAG', tone: 'green' },
  { label: '运行链路', value: 'Trace', tone: 'blue' },
  { label: '剧本工具', value: 'MCP', tone: 'yellow' },
  { label: '响应闭环', value: 'SOAR', tone: 'green' },
]

const riskRails = [
  { label: '数据接入', value: 'Online', width: '84%' },
  { label: '治理覆盖', value: 'Mapped', width: '72%' },
  { label: '威胁调查', value: 'Ready', width: '91%' },
]

const validate = () => {
  const normalizedEmail = email.value.trim()
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) {
    errorMessage.value = '请输入有效邮箱'
    return null
  }
  if (password.value.length < 8) {
    errorMessage.value = '密码至少需要 8 位'
    return null
  }
  return { email: normalizedEmail, password: password.value }
}

const submitAuth = async () => {
  const credentials = validate()
  if (!credentials) return

  submitting.value = true
  errorMessage.value = ''
  try {
    if (mode.value === 'register') {
      await registerWithPassword(credentials)
    }
    const token = await loginWithPassword(credentials)
    storeAuthToken(token.access_token)
    const user = await fetchCurrentUser(token.access_token)
    emit('authenticated', user)
  } catch (err: unknown) {
    clearStoredAuthToken()
    errorMessage.value = err instanceof Error && err.message ? err.message : '认证失败'
  } finally {
    submitting.value = false
  }
}

const providerLabel = (provider: OAuthProvider) => {
  const labels: Record<string, string> = {
    github: 'GitHub',
    google: 'Google',
    microsoft: 'Microsoft',
  }
  return labels[provider] || provider
}

const startOAuth = async (provider: OAuthProvider) => {
  oauthLoading.value = provider
  errorMessage.value = ''
  try {
    const authorizationUrl = await requestOAuthAuthorization(provider)
    window.location.assign(authorizationUrl)
  } catch (err: unknown) {
    errorMessage.value = err instanceof Error && err.message ? err.message : 'OAuth 授权失败'
  } finally {
    oauthLoading.value = ''
  }
}

onMounted(async () => {
  try {
    oauthProviders.value = await fetchOAuthProviders()
  } catch {
    oauthProviders.value = []
  }
})
</script>

<style scoped>
.auth-screen {
  min-height: 100dvh;
  display: grid;
  place-items: center;
  padding: 24px;
  background:
    linear-gradient(rgba(47, 143, 237, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(47, 143, 237, 0.08) 1px, transparent 1px),
    #eef3f7;
  background-size: 44px 44px;
  color: #111827;
}

html.dark .auth-screen {
  background:
    linear-gradient(rgba(106, 215, 255, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(106, 215, 255, 0.08) 1px, transparent 1px),
    #071014;
  color: #e6edf3;
}

.auth-card {
  width: min(1120px, 100%);
  min-height: min(720px, calc(100dvh - 48px));
  display: grid;
  grid-template-columns: minmax(340px, 0.82fr) minmax(420px, 1.18fr);
  overflow: hidden;
  border: 1px solid #b8c8d8;
  border-radius: 8px;
  background: #f8fafc;
  box-shadow: 0 18px 60px rgba(15, 23, 42, 0.16);
}

html.dark .auth-card {
  border-color: #20313d;
  background: #0b141b;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.42);
}

.auth-panel,
.lineage-panel {
  min-width: 0;
  padding: 32px;
}

.auth-panel {
  display: flex;
  flex-direction: column;
  justify-content: center;
  border-right: 1px solid #cbd6e2;
  background: #ffffff;
}

html.dark .auth-panel {
  border-color: #20313d;
  background: #0e171f;
}

.auth-brand {
  display: flex;
  align-items: center;
  gap: 14px;
}

.auth-logo {
  display: grid;
  width: 46px;
  height: 46px;
  place-items: center;
  border: 1px solid rgba(47, 143, 237, 0.42);
  border-radius: 8px;
  background: #eaf5ff;
  color: #0969da;
}

html.dark .auth-logo {
  background: #102638;
  color: #6ad7ff;
}

.auth-brand h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 800;
  letter-spacing: 0;
}

.auth-brand p,
.auth-footer,
.auth-oauth > span,
.auth-field > span {
  color: #5f7080;
}

html.dark .auth-brand p,
html.dark .auth-footer,
html.dark .auth-oauth > span,
html.dark .auth-field > span {
  color: #8ea0ae;
}

.auth-brand p {
  margin: 4px 0 0;
  font-size: 13px;
}

.auth-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  margin-top: 34px;
  padding: 4px;
  border: 1px solid #cbd6e2;
  border-radius: 8px;
  background: #eef3f7;
}

html.dark .auth-tabs {
  border-color: #20313d;
  background: #071014;
}

.auth-tabs button {
  min-height: 40px;
  cursor: pointer;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 700;
  color: #5f7080;
}

.auth-tabs button.active {
  background: #ffffff;
  color: #0f4f8f;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
}

html.dark .auth-tabs button.active {
  background: #102638;
  color: #ddf4ff;
}

.auth-form {
  margin-top: 26px;
  display: grid;
  gap: 16px;
}

.auth-field {
  display: grid;
  gap: 8px;
  font-size: 13px;
  font-weight: 700;
}

.auth-alert {
  margin: 0;
}

.auth-submit {
  width: 100%;
  margin-top: 2px;
}

.auth-oauth {
  margin-top: 22px;
  display: grid;
  gap: 10px;
}

.auth-oauth > div {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.oauth-button {
  min-width: 104px;
}

.auth-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 28px;
  font-size: 11px;
}

.auth-footer span {
  border: 1px solid #d8e0e7;
  border-radius: 6px;
  padding: 4px 7px;
  background: #f8fafc;
}

html.dark .auth-footer span {
  border-color: #20313d;
  background: #0b141b;
}

.lineage-panel {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 28px;
  background: #e8eef4;
}

html.dark .lineage-panel {
  background: #071014;
}

.lineage-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  color: #475569;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  text-transform: uppercase;
}

html.dark .lineage-header {
  color: #8ea0ae;
}

.theme-chip {
  display: grid;
  width: 34px;
  height: 34px;
  cursor: pointer;
  place-items: center;
  border: 1px solid #cbd6e2;
  border-radius: 8px;
  background: #ffffff;
}

html.dark .theme-chip {
  border-color: #20313d;
  background: #0e171f;
}

.lineage-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.lineage-cell {
  min-height: 118px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  border: 1px solid #c6d3df;
  border-radius: 8px;
  padding: 14px;
  background: #ffffff;
}

html.dark .lineage-cell {
  border-color: #20313d;
  background: #0e171f;
}

.lineage-cell strong {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 22px;
  color: #0f172a;
}

html.dark .lineage-cell strong {
  color: #e6edf3;
}

.lineage-cell em {
  font-style: normal;
  font-size: 12px;
  color: #64748b;
}

.lineage-cell.blue {
  box-shadow: inset 0 3px 0 #2f8fed;
}

.lineage-cell.green {
  box-shadow: inset 0 3px 0 #54d38a;
}

.lineage-cell.yellow {
  box-shadow: inset 0 3px 0 #f6c343;
}

.lineage-cell.red {
  box-shadow: inset 0 3px 0 #f06a6a;
}

.risk-rail {
  display: grid;
  gap: 12px;
}

.risk-rail div {
  display: grid;
  grid-template-columns: 92px 74px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  color: #475569;
  font-size: 12px;
}

html.dark .risk-rail div {
  color: #8ea0ae;
}

.risk-rail strong {
  color: #0f172a;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

html.dark .risk-rail strong {
  color: #e6edf3;
}

.risk-rail i {
  height: 8px;
  border-radius: 4px;
  background: #2f8fed;
  box-shadow: 0 0 0 1px rgba(47, 143, 237, 0.22);
}

.auth-copy h2 {
  max-width: 620px;
  margin: 0;
  font-size: clamp(28px, 4vw, 46px);
  line-height: 1.08;
  letter-spacing: 0;
  color: #0f172a;
}

html.dark .auth-copy h2 {
  color: #ffffff;
}

.auth-copy p {
  max-width: 560px;
  margin: 16px 0 0;
  color: #526170;
  font-size: 14px;
  line-height: 1.8;
}

html.dark .auth-copy p {
  color: #9aacb9;
}

@media (max-width: 860px) {
  .auth-screen {
    padding: 12px;
    place-items: stretch;
  }

  .auth-card {
    min-height: calc(100dvh - 24px);
    grid-template-columns: 1fr;
  }

  .auth-panel {
    border-right: 0;
    border-bottom: 1px solid #cbd6e2;
  }

  .lineage-panel {
    padding-top: 24px;
  }

  .lineage-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 520px) {
  .auth-panel,
  .lineage-panel {
    padding: 20px;
  }

  .lineage-cell {
    min-height: 92px;
  }

  .risk-rail div {
    grid-template-columns: 1fr;
    gap: 5px;
  }
}
</style>
