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
  organization: OrgInfo
}

interface AuthState {
  user: User | null
  isLoading: boolean
  fetchMe: () => Promise<void>
  logout: () => void
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
  logout: () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
    }
    set({ user: null })
    window.location.href = '/login'
  },
}))
