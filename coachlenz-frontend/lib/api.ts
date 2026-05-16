import { getToken } from './auth'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const url = `${API_BASE}/api/v1${path}`
  const res = await fetch(url, { ...options, headers })

  if (res.status === 401) {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('coachlenz_token')
      window.location.href = '/login'
    }
    throw new ApiError('Unauthorized', 401)
  }

  const data = await res.json().catch(() => ({}))

  if (!res.ok) {
    throw new ApiError(
      data?.detail || `Request failed with status ${res.status}`,
      res.status
    )
  }

  return data as T
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: 'GET' }),

  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),

  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    }),

  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

// Typed API helpers
export const authApi = {
  login: (email: string, password: string) =>
    api.post<{ access_token: string; coach_id: string; name: string; email: string; role: string }>(
      '/auth/login',
      { email, password }
    ),
  register: (data: {
    name: string
    email: string
    password: string
    role: string
    admin_key: string
  }) => api.post('/auth/register', data),
}

export const teamsApi = {
  list: () => api.get<Team[]>('/teams'),
  get: (id: string) => api.get<Team>(`/teams/${id}`),
  create: (data: Partial<Team>) => api.post<Team>('/teams', data),
  update: (id: string, data: Partial<Team>) => api.patch<Team>(`/teams/${id}`, data),
  delete: (id: string) => api.delete(`/teams/${id}`),
  roster: (id: string) => api.get<Player[]>(`/teams/${id}/roster`),
  schedule: (id: string) => api.get<Game[]>(`/teams/${id}/schedule`),
  stats: (id: string) => api.get<unknown>(`/teams/${id}/stats`),
}

export const playersApi = {
  list: (teamId?: string) =>
    api.get<Player[]>(teamId ? `/players?team_id=${teamId}` : '/players'),
  get: (id: string) => api.get<Player>(`/players/${id}`),
  create: (data: Partial<Player>) => api.post<Player>('/players', data),
  update: (id: string, data: Partial<Player>) => api.patch<Player>(`/players/${id}`, data),
  delete: (id: string) => api.delete(`/players/${id}`),
  stats: (id: string) => api.get<unknown>(`/players/${id}/stats`),
  setStatus: (id: string, status: string) =>
    api.patch<Player>(`/players/${id}/status`, { status }),
}

export const gamesApi = {
  list: (teamId?: string) =>
    api.get<Game[]>(teamId ? `/games?team_id=${teamId}` : '/games'),
  get: (id: string) => api.get<Game>(`/games/${id}`),
  create: (data: Partial<Game>) => api.post<Game>('/games', data),
  update: (id: string, data: Partial<Game>) => api.patch<Game>(`/games/${id}`, data),
  delete: (id: string) => api.delete(`/games/${id}`),
  updateScore: (id: string, ourScore: number, opponentScore: number) =>
    api.patch<Game>(`/games/${id}/score`, { our_score: ourScore, opponent_score: opponentScore }),
  stats: (id: string) => api.get<unknown>(`/games/${id}/stats`),
}

export const statsApi = {
  record: (data: {
    player_id: string
    game_id?: string
    sport: string
    stats: Record<string, number>
  }) => api.post('/stats', data),
  playerHistory: (playerId: string) => api.get<unknown>(`/stats/player/${playerId}`),
  teamSeason: (teamId: string) => api.get<unknown>(`/stats/team/${teamId}/season`),
  aiAnalysis: (playerId: string, context?: string) =>
    api.post<{ player: Player; analysis: string; stat_records_analyzed: number }>(
      '/stats/ai-analysis',
      { player_id: playerId, additional_context: context }
    ),
}

export const practiceApi = {
  list: (teamId?: string) =>
    api.get<PracticePlan[]>(teamId ? `/practice?team_id=${teamId}` : '/practice'),
  teamPlans: (teamId: string) => api.get<PracticePlan[]>(`/practice/team/${teamId}`),
  get: (id: string) => api.get<PracticePlan>(`/practice/${id}`),
  create: (data: Partial<PracticePlan>) => api.post<PracticePlan>('/practice', data),
  update: (id: string, data: Partial<PracticePlan>) =>
    api.patch<PracticePlan>(`/practice/${id}`, data),
  delete: (id: string) => api.delete(`/practice/${id}`),
  generate: (data: {
    team_id: string
    sport: string
    focus_areas: string[]
    duration_minutes: number
    player_count?: number
    notes?: string
  }) => api.post<{ generated: boolean; plan: PracticePlan; ai_notes: string }>('/practice/generate', data),
}

export const dashboardApi = {
  team: (teamId: string) => api.get<DashboardData>(`/dashboard/team/${teamId}`),
}

// Shared types
export interface Team {
  id: string
  name: string
  sport: string
  season?: string
  head_coach?: string
  school?: string
  created_at: string
}

export interface Player {
  id: string
  team_id: string
  name: string
  jersey_number?: string
  position?: string
  grade_year?: string
  email?: string
  phone?: string
  status: 'active' | 'injured' | 'inactive'
  created_at: string
}

export interface Game {
  id: string
  team_id: string
  opponent: string
  date: string
  location?: string
  home_away: 'home' | 'away' | 'neutral'
  our_score?: number
  opponent_score?: number
  result?: 'win' | 'loss' | 'tie' | null
  notes?: string
  created_at: string
}

export interface StatRecord {
  id: string
  player_id: string
  game_id?: string
  sport: string
  stats: Record<string, number>
  recorded_at: string
}

export interface PracticePlan {
  id: string
  team_id: string
  date: string
  title: string
  duration_minutes?: number
  drills: Drill[]
  notes?: string
  created_at: string
}

export interface Drill {
  name: string
  duration_minutes: number
  description: string
  equipment?: string[]
  focus: string
  players_needed?: string | number
  intensity?: 'low' | 'medium' | 'high'
}

export interface DashboardData {
  team: Team
  season_record: { wins: number; losses: number; ties: number; unplayed: number }
  upcoming_games: Game[]
  recent_practices: PracticePlan[]
  team_health: { active: number; injured: number; inactive: number; total: number }
  top_performers: Array<{
    player: Player
    games_with_stats: number
    season_totals: Record<string, number>
  }>
  roster_size: number
}
