<template>
  <main class="auth-screen">
    <section class="auth-card auth-brief-shell" :aria-label="t('auth.entryAria')">
      <aside class="auth-brief" :aria-label="t('auth.briefAria')">
        <header class="auth-brief-header">
          <div class="auth-brand">
            <span class="auth-logo">
              <el-icon><Platform /></el-icon>
            </span>
            <div>
              <h1>{{ PRODUCT_SHORT_NAME }}</h1>
              <p>{{ PRODUCT_FULL_NAME }}</p>
            </div>
          </div>

          <button
            type="button"
            class="theme-chip"
            :aria-label="isDark ? t('auth.theme.toLight') : t('auth.theme.toDark')"
            @click="$emit('toggle-theme')"
          >
            <el-icon>
              <Sunny v-if="isDark" />
              <Moon v-else />
            </el-icon>
          </button>
        </header>

        <div class="auth-brief-title">
          <span>{{ t('auth.brief.eyebrow') }}</span>
          <h2>{{ t('auth.brief.title') }}</h2>
          <p>{{ t('auth.brief.description') }}</p>
        </div>

        <div class="auth-brief-grid">
          <span v-for="item in briefItems" :key="item.label" :class="item.tone">
            <el-icon><component :is="item.icon" /></el-icon>
            {{ item.label }}
          </span>
        </div>
      </aside>

      <div class="auth-panel">
        <div class="auth-panel-heading">
          <span>{{ mode === 'login' ? t('auth.modes.loginEyebrow') : t('auth.modes.registerEyebrow') }}</span>
          <h2>{{ mode === 'login' ? t('auth.modes.loginTitle') : t('auth.modes.registerTitle') }}</h2>
        </div>

        <div class="auth-tabs" role="tablist" :aria-label="t('auth.modes.tabsAria')">
          <button
            type="button"
            :class="{ active: mode === 'login' }"
            role="tab"
            :aria-selected="mode === 'login'"
            @click="mode = 'login'"
          >
            {{ t('auth.modes.login') }}
          </button>
          <button
            type="button"
            :class="{ active: mode === 'register' }"
            role="tab"
            :aria-selected="mode === 'register'"
            @click="mode = 'register'"
          >
            {{ t('auth.modes.register') }}
          </button>
        </div>

        <form class="auth-form" @submit.prevent="submitAuth">
          <label class="auth-field">
            <span>{{ t('auth.fields.email') }}</span>
            <el-input
              v-model="email"
              autocomplete="email"
              clearable
              placeholder="operator@example.com"
              size="large"
            />
          </label>

          <label class="auth-field">
            <span>{{ t('auth.fields.password') }}</span>
            <el-input
              v-model="password"
              autocomplete="current-password"
              :placeholder="t('auth.fields.passwordPlaceholder')"
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
            {{ mode === 'login' ? t('auth.modes.submitLogin') : t('auth.modes.submitRegister') }}
          </el-button>
        </form>

        <div v-if="oauthProviders.length" class="auth-oauth">
          <span>{{ t('auth.oauth.label') }}</span>
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
          <span v-for="item in footerItems" :key="item">{{ item }}</span>
        </div>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChatDotRound, Connection, DataAnalysis, Moon, Platform, Sunny } from '@element-plus/icons-vue'
import {
  clearStoredAuthToken,
  fetchCurrentUser,
  fetchOAuthProviders,
  loginWithPassword,
  registerWithPassword,
  requestOAuthAuthorization,
  storeAuthToken,
  type AuthClientFallbackKey,
} from '../lib/authClient'
import { PRODUCT_FULL_NAME, PRODUCT_SHORT_NAME } from '../modules/shellBrand'
import type { AuthUser, OAuthProvider } from '../types'

defineProps<{
  isDark: boolean
}>()

const emit = defineEmits<{
  authenticated: [user: AuthUser]
  'toggle-theme': []
}>()
const { t } = useI18n()

type AuthMode = 'login' | 'register'
type BriefItem = {
  label: string
  tone: string
  icon: Component
}

const mode = ref<AuthMode>('login')
const email = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const oauthProviders = ref<OAuthProvider[]>([])
const oauthLoading = ref<OAuthProvider | ''>('')
const authClientFallbacks = computed<Record<AuthClientFallbackKey, string>>(() => ({
  fetchUnsupported: t('auth.errors.fetchUnsupported'),
  loginFailed: t('auth.errors.loginFailed'),
  registerFailed: t('auth.errors.registerFailed'),
  currentUserFailed: t('auth.errors.currentUserFailed'),
  oauthProvidersFailed: t('auth.errors.oauthProvidersFailed'),
  oauthAuthorizeFailed: t('auth.errors.oauthAuthorizeFailed'),
  oauthMissingAuthorizationUrl: t('auth.errors.oauthMissingAuthorizationUrl'),
}))

const briefItems = computed<BriefItem[]>(() => [
  { label: t('auth.brief.items.chat'), tone: 'blue', icon: ChatDotRound },
  { label: t('auth.brief.items.mcp'), tone: 'yellow', icon: Connection },
  { label: t('auth.brief.items.trace'), tone: 'green', icon: DataAnalysis },
  { label: t('auth.brief.items.model'), tone: 'red', icon: Platform },
])
const footerItems = computed(() => [
  t('auth.footer.jwt'),
  t('auth.footer.pgvector'),
  t('auth.footer.mcp'),
])

const validate = () => {
  const normalizedEmail = email.value.trim()
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) {
    errorMessage.value = t('auth.errors.invalidEmail')
    return null
  }
  if (password.value.length < 8) {
    errorMessage.value = t('auth.errors.shortPassword')
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
      await registerWithPassword(credentials, { fallbacks: authClientFallbacks.value })
    }
    const token = await loginWithPassword(credentials, { fallbacks: authClientFallbacks.value })
    storeAuthToken(token.access_token)
    const user = await fetchCurrentUser(token.access_token, { fallbacks: authClientFallbacks.value })
    emit('authenticated', user)
  } catch (err: unknown) {
    clearStoredAuthToken()
    errorMessage.value = err instanceof Error && err.message ? err.message : t('auth.errors.authFailed')
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
    const authorizationUrl = await requestOAuthAuthorization(provider, { fallbacks: authClientFallbacks.value })
    window.location.assign(authorizationUrl)
  } catch (err: unknown) {
    errorMessage.value = err instanceof Error && err.message ? err.message : t('auth.errors.oauthFailed')
  } finally {
    oauthLoading.value = ''
  }
}

onMounted(async () => {
  try {
    oauthProviders.value = await fetchOAuthProviders({ fallbacks: authClientFallbacks.value })
  } catch {
    oauthProviders.value = []
  }
})
</script>

<style scoped>
.auth-screen {
  display: grid;
  min-height: 100dvh;
  place-items: center;
  padding: 20px;
  background:
    linear-gradient(90deg, rgba(92, 105, 124, 0.08) 1px, transparent 1px),
    linear-gradient(180deg, rgba(92, 105, 124, 0.06) 1px, transparent 1px),
    var(--ag-page);
  background-size: 34px 34px;
  color: var(--ag-text);
}

.auth-card {
  display: grid;
  width: min(980px, 100%);
  min-height: min(620px, calc(100dvh - 40px));
  grid-template-columns: minmax(300px, 0.72fr) minmax(340px, 1fr);
  overflow: hidden;
  border: 1px solid var(--ag-border);
  border-radius: 8px;
  background: var(--ag-frame);
  box-shadow: var(--ag-shadow);
}

.auth-brief,
.auth-panel {
  min-width: 0;
  padding: clamp(22px, 4vw, 38px);
}

.auth-brief {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 32px;
  border-right: 1px solid var(--ag-border);
  background: var(--ag-sidebar);
  color: var(--ag-sidebar-text);
}

.auth-brief-header,
.auth-brand {
  display: flex;
  align-items: center;
}

.auth-brief-header {
  justify-content: space-between;
  gap: 16px;
}

.auth-brand {
  gap: 12px;
}

.auth-logo {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  border: 1px solid var(--ag-sidebar-border);
  border-radius: 8px;
  background: var(--ag-sidebar-icon);
  color: var(--ag-accent);
}

.auth-brand h1,
.auth-brand p,
.auth-panel-heading h2,
.auth-brief-title h2,
.auth-brief-title p {
  margin: 0;
}

.auth-brand h1 {
  color: var(--ag-sidebar-strong);
  font-size: 17px;
  font-weight: 780;
}

.auth-brand p {
  margin-top: 2px;
  color: var(--ag-sidebar-muted);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
  font-weight: 800;
}

.theme-chip {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border: 1px solid var(--ag-sidebar-border);
  border-radius: 8px;
  background: var(--ag-sidebar-icon);
  color: var(--ag-sidebar-text);
}

.auth-brief-title span,
.auth-panel-heading span {
  display: block;
  color: var(--ag-accent);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  font-weight: 800;
}

.auth-brief-title h2 {
  margin-top: 10px;
  color: var(--ag-sidebar-strong);
  font-size: clamp(34px, 5vw, 54px);
  font-weight: 840;
  line-height: 0.98;
}

.auth-brief-title p {
  max-width: 360px;
  margin-top: 14px;
  color: var(--ag-sidebar-muted);
  font-size: 13px;
  line-height: 1.7;
}

.auth-brief-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.auth-brief-grid span {
  display: inline-flex;
  min-height: 42px;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--ag-sidebar-border);
  border-radius: 8px;
  background: var(--ag-sidebar-item);
  padding: 0 12px;
  color: var(--ag-sidebar-strong);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 12px;
  font-weight: 800;
}

.auth-brief-grid .blue {
  color: var(--ag-blue);
}

.auth-brief-grid .green {
  color: var(--ag-green);
}

.auth-brief-grid .yellow {
  color: var(--ag-yellow);
}

.auth-brief-grid .red {
  color: var(--ag-accent);
}

.auth-panel {
  display: flex;
  flex-direction: column;
  justify-content: center;
  background: var(--ag-panel);
}

.auth-panel-heading h2 {
  margin-top: 8px;
  color: var(--ag-heading);
  font-size: 28px;
  font-weight: 820;
}

.auth-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  margin-top: 28px;
  border: 1px solid var(--ag-border);
  border-radius: 8px;
  background: var(--ag-panel-soft);
  padding: 4px;
}

.auth-tabs button {
  min-height: 38px;
  border-radius: 6px;
  color: var(--ag-muted);
  font-size: 13px;
  font-weight: 750;
}

.auth-tabs button.active {
  background: var(--ag-panel-raised);
  color: var(--ag-heading);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
}

.auth-form {
  display: grid;
  gap: 16px;
  margin-top: 22px;
}

.auth-field {
  display: grid;
  gap: 8px;
}

.auth-field > span,
.auth-oauth > span {
  color: var(--ag-muted-strong);
  font-size: 12px;
  font-weight: 750;
}

.auth-alert {
  margin: 0;
}

.auth-submit {
  width: 100%;
}

.auth-oauth {
  display: grid;
  gap: 10px;
  margin-top: 20px;
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
  margin-top: 22px;
}

.auth-footer span {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--ag-border);
  border-radius: 6px;
  background: var(--ag-panel-soft);
  padding: 3px 7px;
  color: var(--ag-muted);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
  font-weight: 800;
}

@media (max-width: 820px) {
  .auth-screen {
    place-items: stretch;
    padding: 12px;
  }

  .auth-card {
    min-height: calc(100dvh - 24px);
    grid-template-columns: 1fr;
  }

  .auth-brief {
    border-right: 0;
    border-bottom: 1px solid var(--ag-border);
  }
}

@media (max-width: 520px) {
  .auth-brief,
  .auth-panel {
    padding: 20px;
  }

  .auth-brief-grid {
    grid-template-columns: 1fr;
  }
}
</style>
