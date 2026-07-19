const AUTH_TOKEN_STORAGE_KEY = 'agno-aios-auth-token'

export const getToken = () => globalThis.localStorage?.getItem(AUTH_TOKEN_STORAGE_KEY) ?? null

export const setToken = (token: string) => globalThis.localStorage?.setItem(AUTH_TOKEN_STORAGE_KEY, token)

export const clearToken = () => globalThis.localStorage?.removeItem(AUTH_TOKEN_STORAGE_KEY)
