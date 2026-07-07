import { clearStoredAuthToken, getStoredAuthToken } from './authClient'

export const API_BASE = '/api'

const apiUrl = (path: string) => {
  if (path.startsWith('/api')) return path
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

const withAuthHeaders = (init: RequestInit = {}) => {
  const headers = new Headers(init.headers)
  const token = getStoredAuthToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return headers
}

export const apiFetch = async (path: string, init: RequestInit = {}): Promise<Response> => {
  const headers = withAuthHeaders(init)

  const response = await fetch(apiUrl(path), {
    ...init,
    headers,
  })

  if (response.status === 401) {
    clearStoredAuthToken()
  }

  return response
}

export const agentOsFetch = async (path: string, init: RequestInit = {}): Promise<Response> => {
  const headers = withAuthHeaders(init)
  const response = await fetch(path.startsWith('/') ? path : `/${path}`, {
    ...init,
    headers,
  })

  if (response.status === 401) {
    clearStoredAuthToken()
  }

  return response
}
