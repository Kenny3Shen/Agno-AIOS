export type UserRole = 'admin' | 'user' | 'guest'

export interface AuthUser {
  id: string
  email: string
  role?: UserRole
  scopes?: string[]
  is_active: boolean
  is_superuser?: boolean
  is_verified?: boolean
}

export interface AuthTokenResponse {
  access_token: string
  token_type: string
}

export type OAuthProvider = 'github' | 'google' | 'microsoft' | string
