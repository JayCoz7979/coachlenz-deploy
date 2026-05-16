'use client'

import { useState, useEffect, FormEvent } from 'react'
import { useParams } from 'next/navigation'
import { gamesApi, statsApi, teamsApi, Game } from '@/lib/api'
import StatForm from '@/components/StatForm'
import {
  ArrowLeft, Save, Loader2, Plus, X,
} from 'lucide-react'
import Link from 'next/link'

interface PlayerBasic {
  id: string
  name: string
  jersey_number?: string
  position?: string
}

interface PlayerStatRecord {
  id: string
  player_id: string
  stats: Record<string, number>
  sport: string
  recorded_at: string
  players?: PlayerBasic
}

export default function GameDetailPage() {
  const params = useParams()
  const gameId = params.id as string

  const [game, setGame] = useState<Game | null>(null)
  const [playerStats, setPlayerStats] = useState<PlayerStatRecord[]>([])
  const [rosterPlayers, setRosterPlayers] = useState<PlayerBasic[]>([])
  const [teamSport, setTeamSport] = useState('football')
  const [loading, setLoading] = useState(true)
  const [showScoreModal, setShowScoreModal] = useState(false)
  const [showStatModal, setShowStatModal] = useState(false)

  const [ourScore, setOurScore] = useState('')
  const [oppScore, setOppScore] = useState('')
  const [savingScore, setSavingScore] = useState(false)

  const [selectedPlayerId, setSelectedPlayerId] = useState('')
  const [statFields, setStatFields] = useState<Record<string, number>>({})
  const [savingStat, setSavingStat] = useState(false)

  useEffect(() => {
    gamesApi.get(gameId).then(async (g) => {
      setGame(g)
      // Get team sport and roster
      const team = await teamsApi.get(g.team_id)
      setTeamSport(team.sport)
      const roster = await teamsApi.roster(g.team_id)
      setRosterPlayers(roster)
    })

    gamesApi.stats(gameId).then((data) => {
      const d = data as { game: Game; player_stats: PlayerStatRecord[] }
      setPlayerStats(d.player_stats || [])
    }).finally(() => setLoading(false))
  }, [gameId])

  const handleScoreSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSavingScore(true)
    try {
      const updated = await gamesApi.updateScore(gameId, parseInt(ourScore), parseInt(oppScore))
      setGame(updated)
      setShowScoreModal(false)
    } finally {
      setSavingScore(false)
    }
  }

  const handleRecordStat = async (e: FormEvent) => {
    e.preventDefault()
    if (!selectedPlayerId) return
    setSavingStat(true)
    try {
      const newStat = await statsApi.record({
        player_id: selectedPlayerId,
        game_id: gameId,
        sport: teamSport,
        stats: statFields,
      })
      const player = rosterPlayers.find((p) => p.id === selectedPlayerId)
      setPlayerStats((prev) => [...prev, { ...newStat, players: player }])
      setShowStatModal(false)
      setSelectedPlayerId('')
      setStatFields({})
    } finally {
      setSavingStat(false)
    }
  }

  if (loading || !game) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-[#2563eb]" />
      </div>
    )
  }

  const isPlayed = game.our_score != null
  const resultColor = game.result === 'win' ? 'text-green-400' : game.result === 'loss' ? 'text-red-400' : 'text-yellow-400'

  return (
    <div>
      <div className="page-header">
        <Link
          href="/schedule"
          className="flex items-center gap-2 text-[#6b7280] hover:text-white text-sm mb-4 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Schedule
        </Link>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="page-title">vs {game.opponent}</h1>
            <p className="text-[#6b7280] text-sm mt-1">
              {new Date(game.date).toLocaleDateString('en-US', {
                weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
              })}
              {game.location && ` · ${game.location}`}
              {' · '}
              <span className="capitalize">{game.home_away}</span>
            </p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => setShowScoreModal(true)}
              className="btn-secondary flex items-center gap-2"
            >
              <Save className="w-4 h-4" />
              Record Score
            </button>
            <button
              onClick={() => setShowStatModal(true)}
              className="btn-primary flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              Add Player Stats
            </button>
          </div>
        </div>
      </div>

      {/* Score card */}
      {isPlayed ? (
        <div className="card p-6 mb-6 flex items-center justify-center gap-12">
          <div className="text-center">
            <p className="text-[#6b7280] text-sm mb-1">Your Team</p>
            <p className="text-6xl font-bold text-white">{game.our_score}</p>
          </div>
          <div className="text-center">
            {game.result && (
              <p className={`text-2xl font-bold uppercase ${resultColor}`}>{game.result}</p>
            )}
            <p className="text-[#4b5563] text-xs">FINAL</p>
          </div>
          <div className="text-center">
            <p className="text-[#6b7280] text-sm mb-1">{game.opponent}</p>
            <p className="text-6xl font-bold text-white">{game.opponent_score}</p>
          </div>
        </div>
      ) : (
        <div className="card p-6 mb-6 text-center">
          <p className="text-[#6b7280] text-sm">Score not yet recorded.</p>
          <button
            onClick={() => setShowScoreModal(true)}
            className="btn-primary mt-3"
          >
            Record Final Score
          </button>
        </div>
      )}

      {/* Box score */}
      <div className="card p-6">
        <h2 className="text-white font-semibold mb-4">
          Player Stats ({playerStats.length})
        </h2>
        {playerStats.length === 0 ? (
          <p className="text-[#6b7280] text-sm">
            No player stats recorded for this game yet.
          </p>
        ) : (
          <div className="space-y-3">
            {playerStats.map((ps) => (
              <div key={ps.id} className="bg-[#0d0d0d] rounded-lg p-4 border border-[#1e1e1e]">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-white font-medium text-sm">
                    {ps.players?.name || 'Unknown Player'}
                    {ps.players?.jersey_number && (
                      <span className="text-[#6b7280] ml-2 text-xs">#{ps.players.jersey_number}</span>
                    )}
                    {ps.players?.position && (
                      <span className="text-[#6b7280] ml-1 text-xs">· {ps.players.position}</span>
                    )}
                  </p>
                  <span className="text-[#4b5563] text-xs">
                    {new Date(ps.recorded_at).toLocaleTimeString()}
                  </span>
                </div>
                <div className="flex flex-wrap gap-4">
                  {Object.entries(ps.stats).map(([k, v]) => (
                    <div key={k} className="text-center min-w-[48px]">
                      <p className="text-white font-bold">{v}</p>
                      <p className="text-[#6b7280] text-xs">{k.replace(/_/g, ' ')}</p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Score modal */}
      {showScoreModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-[#161616] border border-[#1e1e1e] rounded-2xl w-full max-w-sm">
            <div className="flex items-center justify-between p-6 border-b border-[#1e1e1e]">
              <h2 className="text-white font-semibold">Record Final Score</h2>
              <button onClick={() => setShowScoreModal(false)} className="text-[#6b7280] hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleScoreSubmit} className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="label">Our Score</label>
                  <input
                    type="number"
                    min="0"
                    required
                    value={ourScore}
                    onChange={(e) => setOurScore(e.target.value)}
                    className="input text-center text-2xl font-bold"
                    placeholder="0"
                  />
                </div>
                <div>
                  <label className="label">Their Score</label>
                  <input
                    type="number"
                    min="0"
                    required
                    value={oppScore}
                    onChange={(e) => setOppScore(e.target.value)}
                    className="input text-center text-2xl font-bold"
                    placeholder="0"
                  />
                </div>
              </div>
              <div className="flex gap-3">
                <button type="submit" disabled={savingScore} className="btn-primary flex-1 flex items-center justify-center gap-2">
                  {savingScore && <Loader2 className="w-4 h-4 animate-spin" />}
                  Save Score
                </button>
                <button type="button" onClick={() => setShowScoreModal(false)} className="btn-secondary flex-1">
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Stat entry modal */}
      {showStatModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-[#161616] border border-[#1e1e1e] rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-6 border-b border-[#1e1e1e] sticky top-0 bg-[#161616]">
              <h2 className="text-white font-semibold">Record Player Stats</h2>
              <button onClick={() => setShowStatModal(false)} className="text-[#6b7280] hover:text-white">
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
                <label className="label">Stats</label>
                <StatForm
                  sport={teamSport}
                  onChange={setStatFields}
                />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="submit" disabled={savingStat || !selectedPlayerId} className="btn-primary flex-1 flex items-center justify-center gap-2">
                  {savingStat && <Loader2 className="w-4 h-4 animate-spin" />}
                  Record Stats
                </button>
                <button type="button" onClick={() => setShowStatModal(false)} className="btn-secondary flex-1">
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
