import type {
  AuthCredentials,
  AuthTokenResponse,
  AuthUser,
  OAuthAuthorizationResponse,
  OAuthProvider,
  OAuthProvidersResponse,
} from '../types'

export const AUTH_TOKEN_STORAGE_KEY = 'agno-aios-auth-token'

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
export type AuthClientFallbackKey =
  | 'fetchUnsupported'
  | 'loginFailed'
  | 'registerFailed'
  | 'currentUserFailed'
  | 'oauthProvidersFailed'
  | 'oauthAuthorizeFailed'
  | 'oauthMissingAuthorizationUrl'

export type AuthClientOptions = {
  baseUrl?: string
  fetch?: FetchLike
  storage?: StorageLike
  fallbacks?: Partial<Record<AuthClientFallbackKey, string>>
}

const DEFAULT_API_BASE = '/api'
const DEFAULT_FALLBACKS: Record<AuthClientFallbackKey, string> = {
  fetchUnsupported: 'Fetch API is not available in this environment',
  loginFailed: 'Sign in failed',
  registerFailed: 'Registration failed',
  currentUserFailed: 'Failed to load current user',
  oauthProvidersFailed: 'Failed to load OAuth providers',
  oauthAuthorizeFailed: 'Failed to request OAuth authorization URL',
  oauthMissingAuthorizationUrl: 'OAuth provider did not return an authorization URL',
}

const authUrl = (path: string, baseUrl = DEFAULT_API_BASE) => {
  const base = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl
  return `${base}${path}`
}

const fallbackMessage = (options: AuthClientOptions, key: AuthClientFallbackKey) => {
  return options.fallbacks?.[key] || DEFAULT_FALLBACKS[key]
}

const getFetch = (options: AuthClientOptions = {}): FetchLike => {
  if (options.fetch) return options.fetch
  if (!globalThis.fetch) {
    throw new Error(fallbackMessage(options, 'fetchUnsupported'))
  }
  return globalThis.fetch.bind(globalThis)
}

const getStorage = (storage?: StorageLike): StorageLike | null => {
  if (storage) return storage
  if (typeof globalThis.localStorage === 'undefined') return null
  return globalThis.localStorage
}

const messageFromResponse = async (response: Response, fallback: string) => {
  const data = await response.json().catch(() => null) as unknown
  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>
    const detail = record.detail
    const message = record.message
    if (typeof detail === 'string' && detail) return detail
    if (typeof message === 'string' && message) return message
    if (detail && typeof detail === 'object') {
      const detailRecord = detail as Record<string, unknown>
      const detailError = detailRecord.error
      const detailMessage = detailRecord.message
      if (typeof detailError === 'string' && detailError) return detailError
      if (typeof detailMessage === 'string' && detailMessage) return detailMessage
    }
  }
  return fallback
}

const readJson = async <T>(response: Response, fallback: string): Promise<T> => {
  if (!response.ok) {
    throw new Error(await messageFromResponse(response, fallback))
  }
  return await response.json() as T
}

export const getStoredAuthToken = (options: AuthClientOptions = {}) => {
  return getStorage(options.storage)?.getItem(AUTH_TOKEN_STORAGE_KEY) ?? null
}

export const storeAuthToken = (token: string, options: AuthClientOptions = {}) => {
  getStorage(options.storage)?.setItem(AUTH_TOKEN_STORAGE_KEY, token)
}

export const clearStoredAuthToken = (options: AuthClientOptions = {}) => {
  getStorage(options.storage)?.removeItem(AUTH_TOKEN_STORAGE_KEY)
}

export const loginWithPassword = async (
  credentials: AuthCredentials,
  options: AuthClientOptions = {},
): Promise<AuthTokenResponse> => {
  const body = new URLSearchParams()
  body.set('username', credentials.email)
  body.set('password', credentials.password)

  const response = await getFetch(options)(authUrl('/auth/jwt/login', options.baseUrl), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body,
  })
  return await readJson<AuthTokenResponse>(response, fallbackMessage(options, 'loginFailed'))
}

export const registerWithPassword = async (
  credentials: AuthCredentials,
  options: AuthClientOptions = {},
): Promise<AuthUser> => {
  const response = await getFetch(options)(authUrl('/auth/register', options.baseUrl), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(credentials),
  })
  return await readJson<AuthUser>(response, fallbackMessage(options, 'registerFailed'))
}

export const fetchCurrentUser = async (
  token: string,
  options: AuthClientOptions = {},
): Promise<AuthUser> => {
  const response = await getFetch(options)(authUrl('/auth/users/me', options.baseUrl), {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })
  return await readJson<AuthUser>(response, fallbackMessage(options, 'currentUserFailed'))
}

export const fetchOAuthProviders = async (
  options: AuthClientOptions = {},
): Promise<OAuthProvider[]> => {
  const response = await getFetch(options)(authUrl('/auth/oauth/providers', options.baseUrl))
  const data = await readJson<OAuthProvidersResponse>(response, fallbackMessage(options, 'oauthProvidersFailed'))
  return data.providers || []
}

export const requestOAuthAuthorization = async (
  provider: OAuthProvider,
  options: AuthClientOptions = {},
): Promise<string> => {
  const safeProvider = encodeURIComponent(provider)
  const response = await getFetch(options)(authUrl(`/auth/${safeProvider}/authorize`, options.baseUrl))
  const data = await readJson<OAuthAuthorizationResponse>(response, fallbackMessage(options, 'oauthAuthorizeFailed'))
  if (!data.authorization_url) {
    throw new Error(fallbackMessage(options, 'oauthMissingAuthorizationUrl'))
  }
  return data.authorization_url
}

export const logout = async (
  token: string | null,
  options: AuthClientOptions = {},
): Promise<void> => {
  try {
    if (token) {
      await getFetch(options)(authUrl('/auth/logout', options.baseUrl), {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })
    }
  } finally {
    clearStoredAuthToken(options)
  }
}
