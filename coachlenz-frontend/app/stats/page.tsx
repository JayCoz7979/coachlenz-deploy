'use client'

import { useState, useEffect, FormEvent } from 'react'
import { statsApi, teamsApi, playersApi, Team, Player } from '@/lib/api'
import StatForm from '@/components/StatForm'
import {
  BarChart2, ChevronDown, ChevronUp, Brain, Loader2, Plus, X,
} from 'lucide-react'

interface SeasonStatEntry {
  player: Player
  games_played: number
  stat_entries: number
  aggregated_stats: Record<string, number>
}

const SPORT_PRIMARY_STATS: Record<string, string[]> = {
  football: ['passing_yards', 'rushing_yards', 'touchdowns', 'tackles'],
  basketball: ['points', 'rebounds', 'assists'],
  baseball: ['hits', 'rbi', 'home_runs'],
  softball: ['hits', 'rbi', 'home_runs'],
  soccer: ['goals', 'assists', 'shots'],
  volleyball: ['kills', 'assists', 'aces'],
}

export default function StatsPage() {
  const [teams, setTeams] = useState<Team[]>([])
  const [selectedTeam, setSelectedTeam] = useState<Team | null>(null)
  const [selectedTeamId, setSelectedTeamId] = useState('')
  const [seasonStats, setSeasonStats] = useState<SeasonStatEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [sortKey, setSortKey] = useState('')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const [showRecordModal, setShowRecordModal] = useState(false)
  const [rosterPlayers, setRosterPlayers] = useState<Player[]>([])
  const [selectedPlayerId, setSelectedPlayerId] = useState('')
  const [statFields, setStatFields] = useState<Record<string, number>>({})
  const [saving, setSaving] = useState(false)

  const [aiPlayerId, setAiPlayerId] = useState<string | null>(null)
  const [aiAnalysis, setAiAnalysis] = useState<string>('')
  const [analyzing, setAnalyzing] = useState(false)

  useEffect(() => {
    teamsApi.list().then((data) => {
      setTeams(data)
      if (data.length > 0) {
        setSelectedTeam(data[0])
        setSelectedTeamId(data[0].id)
      }
    })
  }, [])

  useEffect(() => {
    if (!selectedTeamId) return
    const team = teams.find((t) => t.id === selectedTeamId) || null
    setSelectedTeam(team)
    setLoading(true)
    Promise.all([
      statsApi.teamSeason(selectedTeamId),
      playersApi.list(selectedTeamId),
    ]).then(([stats, players]) => {
      const s = stats as { season_stats: SeasonStatEntry[] }
      setSeasonStats(s.season_stats || [])
      setRosterPlayers(players)
    }).finally(() => setLoading(false))
  }, [selectedTeamId, teams])

  const primaryStats = selectedTeam
    ? SPORT_PRIMARY_STATS[selectedTeam.sport] || []
    : []

  const sorted = [...seasonStats].sort((a, b) => {
    if (!sortKey) return 0
    const av = a.aggregated_stats[sortKey] ?? 0
    const bv = b.aggregated_stats[sortKey] ?? 0
    return sortDir === 'desc' ? bv - av : av - bv
  })

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const handleRecordStat = async (e: FormEvent) => {
    e.preventDefault()
    if (!selectedPlayerId || !selectedTeam) return
    setSaving(true)
    try {
      await statsApi.record({
        player_id: selectedPlayerId,
        sport: selectedTeam.sport,
        stats: statFields,
      })
      // Refresh
      const stats = await statsApi.teamSeason(selectedTeamId)
      const s = stats as { season_stats: SeasonStatEntry[] }
      setSeasonStats(s.season_stats || [])
      setShowRecordModal(false)
      setSelectedPlayerId('')
      setStatFields({})
    } finally {
      setSaving(false)
    }
  }

  const handleAiAnalysis = async (playerId: string) => {
    setAiPlayerId(playerId)
    setAiAnalysis('')
    setAnalyzing(true)
    try {
      const res = await statsApi.aiAnalysis(playerId)
      setAiAnalysis(res.analysis)
    } finally {
      setAnalyzing(false)
    }
  }

  const SortIcon = ({ col }: { col: string }) => (
    sortKey === col
      ? (sortDir === 'desc' ? <ChevronDown className="w-3 h-3 inline ml-1" /> : <ChevronUp className="w-3 h-3 inline ml-1" />)
      : null
  )

  return (
    <div>
      <div className="page-header flex items-center justify-between">
        <div>
          <h1 className="page-title">Statistics</h1>
          <p className="page-subtitle">Season totals and performance tracking</p>
        </div>
        <button
          onClick={() => setShowRecordModal(true)}
          className="btn-primary flex items-center gap-2"
          disabled={!selectedTeamId}
        >
          <Plus className="w-4 h-4" />
          Record Stats
        </button>
      </div>

      {/* Team selector */}
      <div className="mb-6">
        <div className="relative inline-block">
          <select
            value={selectedTeamId}
            onChange={(e) => setSelectedTeamId(e.target.value)}
            className="appearance-none bg-[#161616] border border-[#1e1e1e] rounded-lg px-4 py-2.5 pr-10 text-white text-sm focus:outline-none focus:border-[#2563eb]"
          >
            {teams.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name} — {t.sport}
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#6b7280] pointer-events-none" />
        </div>
      </div>

      {/* Stats table */}
      <div className="card overflow-hidden mb-6">
        <div className="flex items-center gap-2 p-5 border-b border-[#1e1e1e]">
          <BarChart2 className="w-4 h-4 text-[#2563eb]" />
          <h2 className="text-white font-semibold">Season Stats</h2>
          {selectedTeam && (
            <span className="text-[#6b7280] text-xs capitalize ml-1">· {selectedTeam.sport}</span>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#1e1e1e]">
                <th className="px-6 py-3 text-left text-xs font-medium text-[#6b7280] uppercase tracking-wider">Player</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-[#6b7280] uppercase tracking-wider">GP</th>
                {primaryStats.map((stat) => (
                  <th
                    key={stat}
                    onClick={() => handleSort(stat)}
                    className="px-4 py-3 text-center text-xs font-medium text-[#6b7280] uppercase tracking-wider cursor-pointer hover:text-white transition-colors"
                  >
                    {stat.replace(/_/g, ' ')} <SortIcon col={stat} />
                  </th>
                ))}
                <th className="px-4 py-3 text-center text-xs font-medium text-[#6b7280] uppercase tracking-wider">AI</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={primaryStats.length + 3} className="px-6 py-10 text-center text-[#6b7280] text-sm">
                    Loading stats...
                  </td>
                </tr>
              ) : sorted.length === 0 ? (
                <tr>
                  <td colSpan={primaryStats.length + 3} className="px-6 py-10 text-center text-[#6b7280] text-sm">
                    No stats recorded yet. Record game or practice stats to see them here.
                  </td>
                </tr>
              ) : (
                sorted.map((entry) => (
                  <tr key={entry.player.id} className="border-b border-[#1e1e1e] hover:bg-[#1e1e1e]/40">
                    <td className="px-6 py-4">
                      <p className="text-white font-medium text-sm">{entry.player.name}</p>
                      <p className="text-[#6b7280] text-xs">
                        #{entry.player.jersey_number} · {entry.player.position}
                      </p>
                    </td>
                    <td className="px-4 py-4 text-center text-[#9ca3af] text-sm">
                      {entry.games_played}
                    </td>
                    {primaryStats.map((stat) => (
                      <td key={stat} className="px-4 py-4 text-center text-white text-sm font-medium">
                        {entry.aggregated_stats[stat] ?? '—'}
                      </td>
                    ))}
                    <td className="px-4 py-4 text-center">
                      <button
                        onClick={() => handleAiAnalysis(entry.player.id)}
                        className="p-1.5 text-[#2563eb] hover:text-[#3b82f6] transition-colors"
                        title="AI Analysis"
                      >
                        <Brain className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* AI analysis panel */}
      {(aiPlayerId || analyzing) && (
        <div className="card p-6">
          <div className="flex items-center gap-2 mb-4">
            <Brain className="w-4 h-4 text-[#2563eb]" />
            <h3 className="text-white font-semibold">AI Performance Analysis</h3>
          </div>
          {analyzing ? (
            <div className="flex items-center gap-3 text-[#6b7280] text-sm">
              <Loader2 className="w-4 h-4 animate-spin" />
              Analyzing player data with Claude...
            </div>
          ) : (
            <div className="bg-[#0d0d0d] rounded-lg p-4 border border-[#1e1e1e]">
              <p className="text-[#e5e7eb] text-sm leading-relaxed whitespace-pre-wrap">{aiAnalysis}</p>
            </div>
          )}
        </div>
      )}

      {/* Record stat modal */}
      {showRecordModal && selectedTeam && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-[#161616] border border-[#1e1e1e] rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-6 border-b border-[#1e1e1e] sticky top-0 bg-[#161616]">
              <h2 className="text-white font-semibold">Record Player Stats</h2>
              <button onClick={() => setShowRecordModal(false)} className="text-[#6b7280] hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleRecordStat} className="p-6 space-y-4">
              <div>
                <label className="label">Player *</label>
                <select
                  required
                  value={selectedPlayerId}
                  onChange={(e) => setSelectedPlayerId(e.target.value)}
                  className="input"
                >
                  <option value="">Select player</option>
                  {rosterPlayers.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} {p.jersey_number && `#${p.jersey_number}`}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="label">Stats — {selectedTeam.sport}</label>
                <StatForm
                  sport={selectedTeam.sport}
                  onChange={setStatFields}
                />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="submit" disabled={saving || !selectedPlayerId} className="btn-primary flex-1 flex items-center justify-center gap-2">
                  {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                  {saving ? 'Saving...' : 'Record Stats'}
                </button>
                <button type="button" onClick={() => setShowRecordModal(false)} className="btn-secondary flex-1">
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
