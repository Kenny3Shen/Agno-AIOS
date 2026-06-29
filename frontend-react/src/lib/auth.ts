export type AuthUser = {
  id: string
  email: string
  is_active: boolean
  is_superuser: boolean
  is_verified: boolean
}

export type AuthTokenResponse = {
  access_token: string
  token_type: string
}

export type OAuthProvider = 'github' | 'google' | 'microsoft' | string

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const TOKEN_STORAGE_KEY = 'agno-aios-auth-token'

function authUrl(path: string) {
  return `${API_BASE}${path}`
}

async function readError(response: Response, fallback: string) {
  const payload = (await response.json().catch(() => null)) as unknown
  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>
    const detail = record.detail
    if (typeof detail === 'string' && detail) return detail
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0] as Record<string, unknown>
      if (typeof first.msg === 'string') return first.msg
    }
  }
  return fallback
}

export function getStoredAuthToken() {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(TOKEN_STORAGE_KEY)
}

export function setStoredAuthToken(token: string) {
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token)
}

export function clearStoredAuthToken() {
  window.localStorage.removeItem(TOKEN_STORAGE_KEY)
}

export async function loginWithPassword(options: {
  email: string
  password: string
}) {
  const form = new URLSearchParams()
  form.set('username', options.email)
  form.set('password', options.password)

  const response = await fetch(authUrl('/api/auth/jwt/login'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Accept: 'application/json',
    },
    body: form,
  })

  if (!response.ok) {
    throw new Error(await readError(response, '登录失败，请检查邮箱和密码。'))
  }

  return (await response.json()) as AuthTokenResponse
}

export async function registerWithPassword(options: {
  email: string
  password: string
}) {
  const response = await fetch(authUrl('/api/auth/register'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({
      email: options.email,
      password: options.password,
    }),
  })

  if (!response.ok) {
    throw new Error(await readError(response, '注册失败，请检查输入信息。'))
  }

  return (await response.json()) as AuthUser
}

export async function fetchCurrentUser(token: string) {
  const response = await fetch(authUrl('/api/auth/users/me'), {
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(await readError(response, '获取当前用户失败。'))
  }

  return (await response.json()) as AuthUser
}

export async function fetchOAuthProviders() {
  const response = await fetch(authUrl('/api/auth/oauth/providers'), {
    headers: { Accept: 'application/json' },
  })

  if (!response.ok) {
    return [] as OAuthProvider[]
  }

  const payload = (await response.json()) as { providers?: OAuthProvider[] }
  return payload.providers ?? []
}

export async function requestOAuthAuthorization(provider: OAuthProvider) {
  const response = await fetch(authUrl(`/api/auth/${provider}/authorize`), {
    headers: { Accept: 'application/json' },
  })

  if (!response.ok) {
    throw new Error(await readError(response, '获取 OAuth 授权地址失败。'))
  }

  const payload = (await response.json()) as { authorization_url?: string }
  if (!payload.authorization_url) {
    throw new Error('OAuth 授权地址为空。')
  }
  return payload.authorization_url
}
