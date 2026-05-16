'use client'

import { useState, useEffect, FormEvent } from 'react'
import { playersApi, teamsApi, Player, Team } from '@/lib/api'
import PlayerBadge from '@/components/PlayerBadge'
import {
  UserPlus,
  X,
  Edit2,
  Trash2,
  ChevronDown,
  Search,
  Loader2,
} from 'lucide-react'
import Link from 'next/link'

const POSITIONS = {
  football: ['QB', 'RB', 'WR', 'TE', 'OL', 'DL', 'LB', 'CB', 'S', 'K', 'P'],
  basketball: ['PG', 'SG', 'SF', 'PF', 'C'],
  baseball: ['P', 'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'DH'],
  softball: ['P', 'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'DP'],
  soccer: ['GK', 'CB', 'LB', 'RB', 'CDM', 'CM', 'CAM', 'LW', 'RW', 'ST'],
  volleyball: ['S', 'OH', 'OPP', 'MB', 'L', 'RS'],
}

export default function RosterPage() {
  const [teams, setTeams] = useState<Team[]>([])
  const [selectedTeamId, setSelectedTeamId] = useState<string>('')
  const [selectedTeam, setSelectedTeam] = useState<Team | null>(null)
  const [players, setPlayers] = useState<Player[]>([])
  const [loading, setLoading] = useState(false)
  const [showAddModal, setShowAddModal] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [filterStatus, setFilterStatus] = useState<string>('all')

  // Form state
  const [form, setForm] = useState({
    name: '', jersey_number: '', position: '', grade_year: '',
    email: '', phone: '', status: 'active',
  })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    teamsApi.list().then((data) => {
      setTeams(data)
      if (data.length > 0) setSelectedTeamId(data[0].id)
    })
  }, [])

  useEffect(() => {
    if (!selectedTeamId) return
    const team = teams.find((t) => t.id === selectedTeamId) || null
    setSelectedTeam(team)
    setLoading(true)
    teamsApi.roster(selectedTeamId)
      .then(setPlayers)
      .finally(() => setLoading(false))
  }, [selectedTeamId, teams])

  const filtered = players.filter((p) => {
    const matchSearch =
      !searchQuery ||
      p.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.jersey_number?.includes(searchQuery) ||
      p.position?.toLowerCase().includes(searchQuery.toLowerCase())
    const matchStatus = filterStatus === 'all' || p.status === filterStatus
    return matchSearch && matchStatus
  })

  const handleAddPlayer = async (e: FormEvent) => {
    e.preventDefault()
    if (!selectedTeamId) return
    setSaving(true)
    try {
      const newPlayer = await playersApi.create({ ...form, team_id: selectedTeamId })
      setPlayers((prev) => [...prev, newPlayer])
      setShowAddModal(false)
      setForm({ name: '', jersey_number: '', position: '', grade_year: '', email: '', phone: '', status: 'active' })
    } finally {
      setSaving(false)
    }
  }

  const handleStatusChange = async (playerId: string, status: string) => {
    await playersApi.setStatus(playerId, status)
    setPlayers((prev) =>
      prev.map((p) => (p.id === playerId ? { ...p, status: status as Player['status'] } : p))
    )
  }

  const handleDelete = async (playerId: string) => {
    if (!confirm('Remove this player from the roster?')) return
    await playersApi.delete(playerId)
    setPlayers((prev) => prev.filter((p) => p.id !== playerId))
  }

  const positions = selectedTeam
    ? POSITIONS[selectedTeam.sport as keyof typeof POSITIONS] || []
    : []

  return (
    <div>
      <div className="page-header flex items-center justify-between">
        <div>
          <h1 className="page-title">Roster</h1>
          <p className="page-subtitle">Manage players and their status</p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="btn-primary flex items-center gap-2"
          disabled={!selectedTeamId}
        >
          <UserPlus className="w-4 h-4" />
          Add Player
        </button>
      </div>

      {/* Team + filters */}
      <div className="flex items-center gap-4 mb-6">
        <div className="relative">
          <select
            value={selectedTeamId}
            onChange={(e) => setSelectedTeamId(e.target.value)}
            className="appearance-none bg-[#161616] border border-[#1e1e1e] rounded-lg px-4 py-2.5 pr-10 text-white text-sm focus:outline-none focus:border-[#2563eb]"
          >
            {teams.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#6b7280] pointer-events-none" />
        </div>

        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#6b7280]" />
          <input
            type="text"
            placeholder="Search players..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="input pl-9"
          />
        </div>

        <div className="relative">
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="appearance-none bg-[#161616] border border-[#1e1e1e] rounded-lg px-4 py-2.5 pr-10 text-white text-sm focus:outline-none focus:border-[#2563eb]"
          >
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="injured">Injured</option>
            <option value="inactive">Inactive</option>
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#6b7280] pointer-events-none" />
        </div>
      </div>

      {/* Players table */}
      <div className="card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[#1e1e1e]">
              {['#', 'Name', 'Position', 'Grade/Year', 'Status', 'Actions'].map((h) => (
                <th
                  key={h}
                  className="px-6 py-4 text-left text-xs font-medium text-[#6b7280] uppercase tracking-wider"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-[#6b7280] text-sm">
                  Loading roster...
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-[#6b7280] text-sm">
                  {players.length === 0
                    ? 'No players on this roster yet.'
                    : 'No players match your search.'}
                </td>
              </tr>
            ) : (
              filtered.map((player) => (
                <tr
                  key={player.id}
                  className="border-b border-[#1e1e1e] hover:bg-[#1e1e1e]/40 transition-colors"
                >
                  <td className="px-6 py-4">
                    <span className="text-[#9ca3af] font-mono text-sm">
                      {player.jersey_number || '—'}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <Link
                      href={`/roster/${player.id}`}
                      className="text-white font-medium hover:text-[#2563eb] transition-colors"
                    >
                      {player.name}
                    </Link>
                  </td>
                  <td className="px-6 py-4 text-[#9ca3af] text-sm">
                    {player.position || '—'}
                  </td>
                  <td className="px-6 py-4 text-[#9ca3af] text-sm">
                    {player.grade_year || '—'}
                  </td>
                  <td className="px-6 py-4">
                    <select
                      value={player.status}
                      onChange={(e) => handleStatusChange(player.id, e.target.value)}
                      className="bg-transparent border-0 text-xs cursor-pointer focus:outline-none"
                    >
                      <option value="active">Active</option>
                      <option value="injured">Injured</option>
                      <option value="inactive">Inactive</option>
                    </select>
                    <PlayerBadge status={player.status} />
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      <Link
                        href={`/roster/${player.id}`}
                        className="p-1.5 text-[#6b7280] hover:text-white transition-colors"
                        title="View/Edit"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </Link>
                      <button
                        onClick={() => handleDelete(player.id)}
                        className="p-1.5 text-[#6b7280] hover:text-red-400 transition-colors"
                        title="Remove"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        {filtered.length > 0 && (
          <div className="px-6 py-3 border-t border-[#1e1e1e]">
            <p className="text-[#6b7280] text-xs">
              {filtered.length} of {players.length} players
            </p>
          </div>
        )}
      </div>

      {/* Add player modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-[#161616] border border-[#1e1e1e] rounded-2xl w-full max-w-lg">
            <div className="flex items-center justify-between p-6 border-b border-[#1e1e1e]">
              <h2 className="text-white font-semibold text-lg">Add Player</h2>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-[#6b7280] hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleAddPlayer} className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="label">Full Name *</label>
                  <input
                    type="text"
                    required
                    value={form.name}
                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                    className="input"
                    placeholder="Player name"
                  />
                </div>
                <div>
                  <label className="label">Jersey #</label>
                  <input
                    type="text"
                    value={form.jersey_number}
                    onChange={(e) => setForm((f) => ({ ...f, jersey_number: e.target.value }))}
                    className="input"
                    placeholder="12"
                  />
                </div>
                <div>
                  <label className="label">Position</label>
                  {positions.length > 0 ? (
                    <div className="relative">
                      <select
                        value={form.position}
                        onChange={(e) => setForm((f) => ({ ...f, position: e.target.value }))}
                        className="input appearance-none pr-8"
                      >
                        <option value="">Select position</option>
                        {positions.map((p) => (
                          <option key={p} value={p}>{p}</option>
                        ))}
                      </select>
                      <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#6b7280] pointer-events-none" />
                    </div>
                  ) : (
                    <input
                      type="text"
                      value={form.position}
                      onChange={(e) => setForm((f) => ({ ...f, position: e.target.value }))}
                      className="input"
                      placeholder="Position"
                    />
                  )}
                </div>
                <div>
                  <label className="label">Grade/Year</label>
                  <input
                    type="text"
                    value={form.grade_year}
                    onChange={(e) => setForm((f) => ({ ...f, grade_year: e.target.value }))}
                    className="input"
                    placeholder="Jr / Senior / 2024"
                  />
                </div>
                <div>
                  <label className="label">Status</label>
                  <div className="relative">
                    <select
                      value={form.status}
                      onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}
                      className="input appearance-none pr-8"
                    >
                      <option value="active">Active</option>
                      <option value="injured">Injured</option>
                      <option value="inactive">Inactive</option>
                    </select>
                    <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#6b7280] pointer-events-none" />
                  </div>
                </div>
                <div>
                  <label className="label">Email</label>
                  <input
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                    className="input"
                    placeholder="player@school.edu"
                  />
                </div>
                <div>
                  <label className="label">Phone</label>
                  <input
                    type="tel"
                    value={form.phone}
                    onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                    className="input"
                    placeholder="(555) 555-5555"
                  />
                </div>
              </div>
              <div className="flex gap-3 pt-2">
                <button type="submit" disabled={saving} className="btn-primary flex-1 flex items-center justify-center gap-2">
                  {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                  {saving ? 'Adding...' : 'Add Player'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="btn-secondary flex-1"
                >
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
