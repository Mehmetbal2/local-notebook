const ACCESS_TOKEN_KEY = 'access_token'
const REFRESH_TOKEN_KEY = 'refresh_token'
const USER_KEY = 'user'
// Short-lived token for <img>/<audio> preview URLs, which cannot send an Authorization
// header. The backend accepts it only on preview routes, so a URL that ends up in
// browser history or a log does not expose the full session.
const MEDIA_TOKEN_KEY = 'media_token'
const MEDIA_TOKEN_EXPIRES_KEY = 'media_token_expires_at'

export interface User {
  user_id: string
  username: string
  role: 'user' | 'admin'
  phone?: string
  created_at: string
}

export function getToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function setTokens(accessToken: string, refreshToken: string) {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
}

export function setMediaToken(token: string, expiresInSeconds: number) {
  localStorage.setItem(MEDIA_TOKEN_KEY, token)
  localStorage.setItem(MEDIA_TOKEN_EXPIRES_KEY, String(Date.now() + Math.max(0, expiresInSeconds) * 1000))
}

export function getMediaToken(): string | null {
  const token = localStorage.getItem(MEDIA_TOKEN_KEY)
  const expiresAt = Number(localStorage.getItem(MEDIA_TOKEN_EXPIRES_KEY) || 0)
  return token && expiresAt > Date.now() ? token : null
}

/** True when there is no media token or it expires within `marginMs`. */
export function mediaTokenNeedsRefresh(marginMs: number): boolean {
  const expiresAt = Number(localStorage.getItem(MEDIA_TOKEN_EXPIRES_KEY) || 0)
  return !localStorage.getItem(MEDIA_TOKEN_KEY) || expiresAt - Date.now() < marginMs
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem(MEDIA_TOKEN_KEY)
  localStorage.removeItem(MEDIA_TOKEN_EXPIRES_KEY)
}

export function getUser(): User | null {
  const userStr = localStorage.getItem(USER_KEY)
  if (userStr) {
    try {
      return JSON.parse(userStr)
    } catch {
      return null
    }
  }
  return null
}

export function setUser(user: User) {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function isLoggedIn(): boolean {
  return !!getToken()
}

export function isAdmin(): boolean {
  return getUser()?.role === 'admin'
}

export function getDisplayUsername(): string {
  return getUser()?.username || ''
}
