'use client'

import { useState, useEffect, FormEvent } from 'react'
import { gamesApi, teamsApi, Game, Team } from '@/lib/api'
import {
  Plus, X, ChevronDown, Calendar, MapPin, Loader2, Trash2,
} from 'lucide-react'
import Link from 'next/link'

function ResultBadge({ result }: { result?: string | null }) {
  if (!result) return <span className="text-[#6b7280] text-xs">Upcoming</span>
  const cfg = {
    win: 'bg-green-900/40 text-green-400 border-green-800',
    loss: 'bg-red-900/40 text-red-400 border-red-800',
    tie: 'bg-yellow-900/40 text-yellow-400 border-yellow-800',
  }[result] || 'bg-gray-800 text-gray-400 border-gray-700'
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold border uppercase ${cfg}`}>
      {result}
    </span>
  )
}

export default function SchedulePage() {
  const [teams, setTeams] = useState<Team[]>([])
  const [selectedTeamId, setSelectedTeamId] = useState('')
  const [games, setGames] = useState<Game[]>([])
  const [loading, setLoading] = useState(false)
  const [showAddModal, setShowAddModal] = useState(false)
  const [saving, setSaving] = useState(false)

  const [form, setForm] = useState({
    opponent: '', date: '', location: '', home_away: 'home', notes: '',
  })

  useEffect(() => {
    teamsApi.list().then((data) => {
      setTeams(data)
      if (data.length > 0) setSelectedTeamId(data[0].id)
    })
  }, [])

  useEffect(() => {
    if (!selectedTeamId) return
    setLoading(true)
    teamsApi.schedule(selectedTeamId).then(setGames).finally(() => setLoading(false))
  }, [selectedTeamId])

  const handleAdd = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const newGame = await gamesApi.create({ ...form, team_id: selectedTeamId })
      setGames((prev) => [...prev, newGame].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()))
      setShowAddModal(false)
      setForm({ opponent: '', date: '', location: '', home_away: 'home', notes: '' })
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (gameId: string) => {
    if (!confirm('Delete this game?')) return
    await gamesApi.delete(gameId)
    setGames((prev) => prev.filter((g) => g.id !== gameId))
  }

  const now = new Date()
  const upcoming = games.filter((g) => new Date(g.date) >= now)
  const past = games.filter((g) => new Date(g.date) < now)

  return (
    <div>
      <div className="page-header flex items-center justify-between">
        <div>
          <h1 className="page-title">Schedule</h1>
          <p className="page-subtitle">Games and match results</p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="btn-primary flex items-center gap-2"
          disabled={!selectedTeamId}
        >
          <Plus className="w-4 h-4" />
          Add Game
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
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#6b7280] pointer-events-none" />
        </div>
      </div>

      {loading ? (
        <div className="text-[#6b7280] text-sm">Loading schedule...</div>
      ) : (
        <div className="space-y-8">
          {/* Upcoming */}
          <section>
            <h2 className="text-[#9ca3af] text-xs font-medium uppercase tracking-wider mb-4">
              Upcoming ({upcoming.length})
            </h2>
            {upcoming.length === 0 ? (
              <div className="card p-6 text-center text-[#6b7280] text-sm">
                No upcoming games scheduled.
              </div>
            ) : (
              <div className="space-y-3">
                {upcoming.map((game) => (
                  <GameCard key={game.id} game={game} onDelete={handleDelete} />
                ))}
              </div>
            )}
          </section>

          {/* Past */}
          {past.length > 0 && (
            <section>
              <h2 className="text-[#9ca3af] text-xs font-medium uppercase tracking-wider mb-4">
                Results ({past.length})
              </h2>
              <div className="space-y-3">
                {[...past].reverse().map((game) => (
                  <GameCard key={game.id} game={game} onDelete={handleDelete} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {/* Add game modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-[#161616] border border-[#1e1e1e] rounded-2xl w-full max-w-lg">
            <div className="flex items-center justify-between p-6 border-b border-[#1e1e1e]">
              <h2 className="text-white font-semibold text-lg">Add Game</h2>
              <button onClick={() => setShowAddModal(false)} className="text-[#6b7280] hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleAdd} className="p-6 space-y-4">
              <div>
                <label className="label">Opponent *</label>
                <input
                  type="text"
                  required
                  value={form.opponent}
                  onChange={(e) => setForm((f) => ({ ...f, opponent: e.target.value }))}
                  className="input"
                  placeholder="Opponent team name"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="label">Date & Time *</label>
                  <input
                    type="datetime-local"
                    required
                    value={form.date}
                    onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))}
                    className="input"
                  />
                </div>
                <div>
                  <label className="label">Home / Away</label>
                  <div className="relative">
                    <select
                      value={form.home_away}
                      onChange={(e) => setForm((f) => ({ ...f, home_away: e.target.value }))}
                      className="input appearance-none pr-8"
                    >
                      <option value="home">Home</option>
                      <option value="away">Away</option>
                      <option value="neutral">Neutral</option>
                    </select>
                    <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#6b7280] pointer-events-none" />
                  </div>
                </div>
              </div>
              <div>
                <label className="label">Location</label>
                <input
                  type="text"
                  value={form.location}
                  onChange={(e) => setForm((f) => ({ ...f, location: e.target.value }))}
                  className="input"
                  placeholder="Stadium / arena name"
                />
              </div>
              <div>
                <label className="label">Notes</label>
                <textarea
                  value={form.notes}
                  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                  className="input resize-none h-20"
                  placeholder="Game notes..."
                />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="submit" disabled={saving} className="btn-primary flex-1 flex items-center justify-center gap-2">
                  {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                  {saving ? 'Saving...' : 'Add Game'}
                </button>
                <button type="button" onClick={() => setShowAddModal(false)} className="btn-secondary flex-1">
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

function GameCard({ game, onDelete }: { game: Game; onDelete: (id: string) => void }) {
  return (
    <div className="card p-5 flex items-center justify-between">
      <div className="flex items-center gap-5">
        <div className="text-center w-14">
          <p className="text-[#9ca3af] text-xs">
            {new Date(game.date).toLocaleDateString('en-US', { month: 'short' })}
          </p>
          <p className="text-white text-2xl font-bold leading-none">
            {new Date(game.date).getDate()}
          </p>
        </div>
        <div>
          <div className="flex items-center gap-3">
            <p className="text-white font-semibold">vs {game.opponent}</p>
            <ResultBadge result={game.result} />
            <span className="text-[#4b5563] text-xs capitalize px-2 py-0.5 bg-[#1e1e1e] rounded">
              {game.home_away}
            </span>
          </div>
          <div className="flex items-center gap-4 mt-1">
            {game.location && (
              <div className="flex items-center gap-1 text-[#6b7280] text-xs">
                <MapPin className="w-3 h-3" />
                {game.location}
              </div>
            )}
            <div className="flex items-center gap-1 text-[#6b7280] text-xs">
              <Calendar className="w-3 h-3" />
              {new Date(game.date).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}
            </div>
          </div>
        </div>
      </div>
      <div className="flex items-center gap-4">
        {game.our_score != null && (
          <div className="text-center">
            <p className="text-white text-xl font-bold">
              {game.our_score} – {game.opponent_score}
            </p>
            <p className="text-[#6b7280] text-xs">Final</p>
          </div>
        )}
        <Link
          href={`/schedule/${game.id}`}
          className="btn-secondary text-xs px-3 py-1.5"
        >
          Details
        </Link>
        <button
          onClick={() => onDelete(game.id)}
          className="p-2 text-[#6b7280] hover:text-red-400 transition-colors"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
