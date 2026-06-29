import {
  createContext,
  startTransition,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import type { ReactNode } from 'react'

import {
  clearStoredAuthToken,
  fetchCurrentUser,
  getStoredAuthToken,
  loginWithPassword,
  registerWithPassword,
  setStoredAuthToken,
} from '#/lib/auth.ts'
import type { AuthUser } from '#/lib/auth.ts'

type AuthContextValue = {
  bootstrapping: boolean
  token: string | null
  user: AuthUser | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [bootstrapping, setBootstrapping] = useState(true)
  const [token, setToken] = useState<string | null>(() => getStoredAuthToken())
  const [user, setUser] = useState<AuthUser | null>(null)

  useEffect(() => {
    let cancelled = false

    async function restoreSession() {
      if (!token) {
        setBootstrapping(false)
        return
      }

      try {
        const currentUser = await fetchCurrentUser(token)
        if (!cancelled) setUser(currentUser)
      } catch {
        clearStoredAuthToken()
        if (!cancelled) {
          setToken(null)
          setUser(null)
        }
      } finally {
        if (!cancelled) setBootstrapping(false)
      }
    }

    void restoreSession()
    return () => {
      cancelled = true
    }
  }, [token])

  const value = useMemo<AuthContextValue>(
    () => ({
      bootstrapping,
      token,
      user,
      async login(email, password) {
        const response = await loginWithPassword({ email, password })
        setStoredAuthToken(response.access_token)
        const currentUser = await fetchCurrentUser(response.access_token)
        startTransition(() => {
          setToken(response.access_token)
          setUser(currentUser)
        })
      },
      async register(email, password) {
        await registerWithPassword({ email, password })
        const response = await loginWithPassword({ email, password })
        setStoredAuthToken(response.access_token)
        const currentUser = await fetchCurrentUser(response.access_token)
        startTransition(() => {
          setToken(response.access_token)
          setUser(currentUser)
        })
      },
      logout() {
        clearStoredAuthToken()
        startTransition(() => {
          setToken(null)
          setUser(null)
        })
      },
      async refreshUser() {
        if (!token) return
        const currentUser = await fetchCurrentUser(token)
        setUser(currentUser)
      },
    }),
    [bootstrapping, token, user],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
