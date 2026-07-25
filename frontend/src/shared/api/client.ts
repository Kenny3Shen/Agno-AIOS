import { clearToken, getToken } from '@/shared/auth/storage'

export class ApiError extends Error {
  readonly status: number
  readonly payload?: unknown

  constructor(message: string, status: number, payload?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

const readError = async (response: Response) => {
  const payload: unknown = await response.json().catch(() => null)
  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>
    if (typeof record.detail === 'string') return { message: record.detail, payload }
    if (record.detail && typeof record.detail === 'object') {
      const detail = record.detail as Record<string, unknown>
      if (typeof detail.message === 'string') return { message: detail.message, payload }
    }
    if (typeof record.message === 'string') return { message: record.message, payload }
  }
  return { message: `Request failed (${response.status})`, payload }
}

export const apiFetch = async (path: string, init: RequestInit = {}) => {
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const url = path.startsWith('/api') ? path : `/api${path.startsWith('/') ? path : `/${path}`}`
  const response = await fetch(url, { ...init, headers })
  if (response.status === 401) clearToken()
  return response
}

export const requestJson = async <T>(path: string, init: RequestInit = {}): Promise<T> => {
  const response = await apiFetch(path, init)
  if (!response.ok) {
    const error = await readError(response)
    throw new ApiError(error.message, response.status, error.payload)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const jsonInit = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})
