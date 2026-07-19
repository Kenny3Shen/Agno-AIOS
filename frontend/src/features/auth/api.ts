import { apiFetch, requestJson } from '@/shared/api/client'
import { clearToken } from '@/shared/auth/storage'
import type { AuthTokenResponse, AuthUser, OAuthProvider } from '@/shared/types/auth'

export const login = async (email: string, password: string) => {
  const body = new URLSearchParams({ username: email, password })
  return requestJson<AuthTokenResponse>('/auth/jwt/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
}

export const getCurrentUser = () => requestJson<AuthUser>('/auth/users/me')

export const getOAuthProviders = async () =>
  (await requestJson<{ providers: OAuthProvider[] }>('/auth/oauth/providers')).providers

export const getOAuthAuthorization = async (provider: OAuthProvider) => {
  const data = await requestJson<{ authorization_url: string }>(`/auth/${encodeURIComponent(provider)}/authorize`)
  return data.authorization_url
}

export const logout = async () => {
  try {
    await apiFetch('/auth/logout', { method: 'POST' })
  } finally {
    clearToken()
  }
}
