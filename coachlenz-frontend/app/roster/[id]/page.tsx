'use client'

import { useState, useEffect, FormEvent } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { playersApi, statsApi, Player } from '@/lib/api'
import PlayerBadge from '@/components/PlayerBadge'
import {
  ArrowLeft, Save, Loader2, Brain, ChevronDown,
} from 'lucide-react'
import Link from 'next/link'

interface StatRecord {
  id: string
  sport: string
  game_id?: string
  stats: Record<string, number>
  recorded_at: string
}

export default function PlayerDetailPage() {
  const params = useParams()
  const router = useRouter()
  const playerId = params.id as string

  const [player, setPlayer] = useState<Player | null>(null)
  const [stats, setStats] = useState<StatRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [aiAnalysis, setAiAnalysis] = useState<string>('')
  const [analyzing, setAnalyzing] = useState(false)

  const [form, setForm] = useState({
    name: '', jersey_number: '', position: '',
    grade_year: '', email: '', phone: '', status: 'active',
  })

  useEffect(() => {
    Promise.all([
      playersApi.get(playerId),
      playersApi.stats(playerId),
    ]).then(([p, s]) => {
      setPlayer(p)
      setForm({
        name: p.name || '',
        jersey_number: p.jersey_number || '',
        position: p.position || '',
        grade_year: p.grade_year || '',
        email: p.email || '',
        phone: p.phone || '',
        status: p.status,
      })
      const statsData = s as { stats: StatRecord[] }
      setStats(statsData.stats || [])
    }).finally(() => setLoading(false))
  }, [playerId])

  const handleSave = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const updated = await playersApi.update(playerId, form)
      setPlayer(updated)
    } finally {
      setSaving(false)
    }
  }

  const handleAiAnalysis = async () => {
    setAnalyzing(true)
    setAiAnalysis('')
    try {
      const res = await statsApi.aiAnalysis(playerId)
      setAiAnalysis(res.analysis)
    } finally {
      setAnalyzing(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-[#2563eb]" />
      </div>
    )
  }

  if (!player) {
    return (
      <div className="text-center py-20">
        <p className="text-[#6b7280]">Player not found.</p>
        <Link href="/roster" className="text-[#2563eb] text-sm mt-2 inline-block">
          Back to Roster
        </Link>
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <Link
          href="/roster"
          className="flex items-center gap-2 text-[#6b7280] hover:text-white text-sm mb-4 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Roster
        </Link>
        <div className="flex items-center gap-4">
          <div>
            <h1 className="page-title">{player.name}</h1>
            <div className="flex items-center gap-3 mt-1">
              <p className="text-[#6b7280] text-sm">
                #{player.jersey_number} · {player.position}
              </p>
              <PlayerBadge status={player.status} />
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Edit form */}
        <div className="col-span-2 card p-6">
          <h2 className="text-white font-semibold mb-5">Player Info</h2>
          <form onSubmit={handleSave} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label className="label">Full Name</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  className="input"
                />
              </div>
              <div>
                <label className="label">Jersey #</label>
                <input
                  type="text"
                  value={form.jersey_number}
                  onChange={(e) => setForm((f) => ({ ...f, jersey_number: e.target.value }))}
                  className="input"
                />
              </div>
              <div>
                <label className="label">Position</label>
                <input
                  type="text"
                  value={form.position}
                  onChange={(e) => setForm((f) => ({ ...f, position: e.target.value }))}
                  className="input"
                />
              </div>
              <div>
                <label className="label">Grade/Year</label>
                <input
                  type="text"
                  value={form.grade_year}
                  onChange={(e) => setForm((f) => ({ ...f, grade_year: e.target.value }))}
                  className="input"
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
                />
              </div>
              <div>
                <label className="label">Phone</label>
                <input
                  type="tel"
                  value={form.phone}
                  onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                  className="input"
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={saving}
              className="btn-primary flex items-center gap-2"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </form>
        </div>

        {/* AI analysis */}
        <div className="card p-6">
          <div className="flex items-center gap-2 mb-4">
            <Brain className="w-4 h-4 text-[#2563eb]" />
            <h2 className="text-white font-semibold">AI Performance Analysis</h2>
          </div>
          <p className="text-[#6b7280] text-xs mb-4">
            Claude analyzes stat history and provides coaching insights.
          </p>
          <button
            onClick={handleAiAnalysis}
            disabled={analyzing}
            className="btn-primary w-full flex items-center justify-center gap-2 mb-4"
          >
            {analyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Brain className="w-4 h-4" />}
            {analyzing ? 'Analyzing...' : 'Generate Analysis'}
          </button>
          {aiAnalysis && (
            <div className="bg-[#0d0d0d] rounded-lg p-4 border border-[#1e1e1e]">
              <p className="text-[#e5e7eb] text-xs leading-relaxed whitespace-pre-wrap">
                {aiAnalysis}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Stat history */}
      <div className="mt-6 card p-6">
        <h2 className="text-white font-semibold mb-4">
          Stat History ({stats.length} records)
        </h2>
        {stats.length === 0 ? (
          <p className="text-[#6b7280] text-sm">No stats recorded for this player yet.</p>
        ) : (
          <div className="space-y-3">
            {stats.map((record) => (
              <div
                key={record.id}
                className="bg-[#0d0d0d] rounded-lg p-4 border border-[#1e1e1e]"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[#9ca3af] text-xs font-medium uppercase">
                    {record.sport}
                    {record.game_id ? ' — Game' : ' — Practice'}
                  </span>
                  <span className="text-[#4b5563] text-xs">
                    {new Date(record.recorded_at).toLocaleDateString()}
                  </span>
                </div>
                <div className="flex flex-wrap gap-3">
                  {Object.entries(record.stats).map(([key, val]) => (
                    <div key={key} className="text-center">
                      <p className="text-white font-semibold text-sm">{val}</p>
                      <p className="text-[#6b7280] text-xs">{key.replace(/_/g, ' ')}</p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
