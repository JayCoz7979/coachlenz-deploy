'use client'

import { useState, useEffect } from 'react'
import { teamsApi, dashboardApi, Team, DashboardData } from '@/lib/api'
import PlayerBadge from '@/components/PlayerBadge'
import {
  Trophy,
  Users,
  Calendar,
  Activity,
  TrendingUp,
  AlertTriangle,
  ChevronDown,
} from 'lucide-react'

export default function DashboardPage() {
  const [teams, setTeams] = useState<Team[]>([])
  const [selectedTeamId, setSelectedTeamId] = useState<string>('')
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(false)
  const [teamsLoading, setTeamsLoading] = useState(true)

  useEffect(() => {
    teamsApi
      .list()
      .then((data) => {
        setTeams(data)
        if (data.length > 0) setSelectedTeamId(data[0].id)
      })
      .finally(() => setTeamsLoading(false))
  }, [])

  useEffect(() => {
    if (!selectedTeamId) return
    setLoading(true)
    dashboardApi
      .team(selectedTeamId)
      .then(setDashboard)
      .finally(() => setLoading(false))
  }, [selectedTeamId])

  const record = dashboard?.season_record
  const totalGames = record
    ? record.wins + record.losses + record.ties
    : 0
  const winPct = totalGames > 0 ? ((record!.wins / totalGames) * 100).toFixed(0) : '—'

  return (
    <div>
      <div className="page-header flex items-center justify-between">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-subtitle">Team season overview and analytics</p>
        </div>

        {/* Team selector */}
        {!teamsLoading && teams.length > 0 && (
          <div className="relative">
            <select
              value={selectedTeamId}
              onChange={(e) => setSelectedTeamId(e.target.value)}
              className="appearance-none bg-[#161616] border border-[#1e1e1e] rounded-lg px-4 py-2.5 pr-10 text-white text-sm focus:outline-none focus:border-[#2563eb] cursor-pointer"
            >
              {teams.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} — {t.sport}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#6b7280] pointer-events-none" />
          </div>
        )}
      </div>

      {teamsLoading && (
        <div className="text-[#6b7280] text-sm">Loading teams...</div>
      )}

      {!teamsLoading && teams.length === 0 && (
        <div className="card p-8 text-center">
          <Trophy className="w-12 h-12 text-[#2563eb] mx-auto mb-4" />
          <h3 className="text-white font-semibold text-lg mb-2">No teams yet</h3>
          <p className="text-[#6b7280] text-sm">
            Create your first team to get started with CoachLenz.
          </p>
        </div>
      )}

      {loading && selectedTeamId && (
        <div className="text-[#6b7280] text-sm">Loading dashboard...</div>
      )}

      {dashboard && !loading && (
        <div className="space-y-6">
          {/* Stats row */}
          <div className="grid grid-cols-4 gap-4">
            {/* Record */}
            <div className="stat-card">
              <div className="flex items-center gap-2 mb-3">
                <Trophy className="w-4 h-4 text-[#2563eb]" />
                <p className="text-[#9ca3af] text-xs font-medium uppercase tracking-wider">Season Record</p>
              </div>
              <p className="text-3xl font-bold text-white">
                {record?.wins}-{record?.losses}-{record?.ties}
              </p>
              <p className="text-[#6b7280] text-xs mt-1">W-L-T | Win% {winPct}%</p>
            </div>

            {/* Roster size */}
            <div className="stat-card">
              <div className="flex items-center gap-2 mb-3">
                <Users className="w-4 h-4 text-[#2563eb]" />
                <p className="text-[#9ca3af] text-xs font-medium uppercase tracking-wider">Roster</p>
              </div>
              <p className="text-3xl font-bold text-white">{dashboard.roster_size}</p>
              <p className="text-[#6b7280] text-xs mt-1">Total players</p>
            </div>

            {/* Active players */}
            <div className="stat-card">
              <div className="flex items-center gap-2 mb-3">
                <Activity className="w-4 h-4 text-green-400" />
                <p className="text-[#9ca3af] text-xs font-medium uppercase tracking-wider">Active</p>
              </div>
              <p className="text-3xl font-bold text-white">{dashboard.team_health.active}</p>
              <p className="text-[#6b7280] text-xs mt-1">
                {dashboard.team_health.injured} injured
              </p>
            </div>

            {/* Upcoming games */}
            <div className="stat-card">
              <div className="flex items-center gap-2 mb-3">
                <Calendar className="w-4 h-4 text-[#2563eb]" />
                <p className="text-[#9ca3af] text-xs font-medium uppercase tracking-wider">Upcoming</p>
              </div>
              <p className="text-3xl font-bold text-white">{dashboard.upcoming_games.length}</p>
              <p className="text-[#6b7280] text-xs mt-1">Games scheduled</p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-6">
            {/* Top performers */}
            <div className="col-span-2 card p-6">
              <div className="flex items-center gap-2 mb-5">
                <TrendingUp className="w-4 h-4 text-[#2563eb]" />
                <h3 className="text-white font-semibold">Top Performers</h3>
              </div>

              {dashboard.top_performers.length === 0 ? (
                <p className="text-[#6b7280] text-sm">
                  No stats recorded yet. Record game stats to see top performers.
                </p>
              ) : (
                <div className="space-y-3">
                  {dashboard.top_performers.map((tp, i) => (
                    <div
                      key={tp.player.id}
                      className="flex items-center justify-between py-3 border-b border-[#1e1e1e] last:border-0"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-[#2563eb]/20 flex items-center justify-center text-[#2563eb] font-bold text-sm">
                          {i + 1}
                        </div>
                        <div>
                          <p className="text-white font-medium text-sm">
                            {tp.player.name}
                          </p>
                          <p className="text-[#6b7280] text-xs">
                            #{tp.player.jersey_number} · {tp.player.position}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-white text-sm font-medium">
                          {tp.games_with_stats} games
                        </p>
                        <p className="text-[#6b7280] text-xs">
                          {Object.entries(tp.season_totals)
                            .slice(0, 2)
                            .map(([k, v]) => `${v} ${k.replace(/_/g, ' ')}`)
                            .join(' · ')}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Team health + upcoming */}
            <div className="space-y-4">
              {/* Team health */}
              <div className="card p-5">
                <div className="flex items-center gap-2 mb-4">
                  <AlertTriangle className="w-4 h-4 text-yellow-400" />
                  <h3 className="text-white font-semibold text-sm">Team Health</h3>
                </div>
                <div className="space-y-2">
                  {(['active', 'injured', 'inactive'] as const).map((s) => (
                    <div key={s} className="flex items-center justify-between">
                      <PlayerBadge status={s} />
                      <span className="text-white font-semibold text-sm">
                        {dashboard.team_health[s]}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Next games */}
              <div className="card p-5">
                <div className="flex items-center gap-2 mb-4">
                  <Calendar className="w-4 h-4 text-[#2563eb]" />
                  <h3 className="text-white font-semibold text-sm">Upcoming Games</h3>
                </div>
                {dashboard.upcoming_games.length === 0 ? (
                  <p className="text-[#6b7280] text-xs">No upcoming games scheduled.</p>
                ) : (
                  <div className="space-y-3">
                    {dashboard.upcoming_games.map((g) => (
                      <div key={g.id} className="border-b border-[#1e1e1e] pb-3 last:border-0 last:pb-0">
                        <p className="text-white text-sm font-medium">vs {g.opponent}</p>
                        <p className="text-[#6b7280] text-xs">
                          {new Date(g.date).toLocaleDateString()} ·{' '}
                          <span className="capitalize">{g.home_away}</span>
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Recent practices */}
          {dashboard.recent_practices.length > 0 && (
            <div className="card p-6">
              <h3 className="text-white font-semibold mb-4">Recent Practices</h3>
              <div className="grid grid-cols-3 gap-4">
                {dashboard.recent_practices.map((p) => (
                  <div key={p.id} className="bg-[#0d0d0d] rounded-lg p-4 border border-[#1e1e1e]">
                    <p className="text-white text-sm font-medium">{p.title}</p>
                    <p className="text-[#6b7280] text-xs mt-1">
                      {new Date(p.date).toLocaleDateString()}
                      {p.duration_minutes && ` · ${p.duration_minutes} min`}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
