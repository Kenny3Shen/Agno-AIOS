import { clearStoredAuthToken, getStoredAuthToken } from './authClient'

export const API_BASE = '/api'

const apiUrl = (path: string) => {
  if (path.startsWith('/api')) return path
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

export const apiFetch = async (path: string, init: RequestInit = {}): Promise<Response> => {
  const headers = new Headers(init.headers)
  const token = getStoredAuthToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(apiUrl(path), {
    ...init,
    headers,
  })

  if (response.status === 401) {
    clearStoredAuthToken()
  }

  return response
}
