const TOKEN_KEY = 'coachlenz_token'
const COACH_KEY = 'coachlenz_coach'

export interface Coach {
  id: string
  name: string
  email: string
  role: string
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  if (typeof window === 'undefined') return
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  if (typeof window === 'undefined') return
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(COACH_KEY)
}

export function isAuthenticated(): boolean {
  return !!getToken()
}

export function getCoach(): Coach | null {
  if (typeof window === 'undefined') return null
  const raw = localStorage.getItem(COACH_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as Coach
  } catch {
    return null
  }
}

export function setCoach(coach: Coach): void {
  if (typeof window === 'undefined') return
  localStorage.setItem(COACH_KEY, JSON.stringify(coach))
}

export function logout(): void {
  clearToken()
  window.location.href = '/login'
}
