import { create } from 'zustand'
import api from './api'

interface OrgInfo {
  id: string
  name: string
  subscription_tier: string
  is_trial: boolean
  trial_active: boolean
  trial_days_remaining: number
  has_coach_tenure_access: boolean
  admin_level: string | null
}

interface User {
  id: string
  name: string
  email: string
  role: string
  // Capability strings for this user's role (from GET /me). UI gates off these.
  permissions: string[]
  organization: OrgInfo
}

interface AuthState {
  user: User | null
  isLoading: boolean
  fetchMe: () => Promise<void>
  logout: () => Promise<void>
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  isLoading: true,
  fetchMe: async () => {
    try {
      const res = await api.get('/me')
      set({ user: res.data, isLoading: false })
    } catch {
      set({ user: null, isLoading: false })
    }
  },
  logout: async () => {
    // Revoke server-side (bumps token_version -> kills all refresh tokens) before
    // discarding the local tokens. Best-effort: still sign out locally if it fails.
    try {
      await api.post('/auth/logout')
    } catch {
      // ignore — we sign out locally regardless
    }
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
    }
    set({ user: null })
    window.location.href = '/login'
  },
}))

// UI gate: true if the signed-in user's role has the given capability. Usage:
//   const canManageRoster = usePermission('can_manage_roster')
export const usePermission = (permission: string) =>
  useAuth((s) => s.user?.permissions?.includes(permission) ?? false)
