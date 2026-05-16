'use client'

import { useState, useEffect, FormEvent } from 'react'
import { practiceApi, teamsApi, PracticePlan, Team } from '@/lib/api'
import {
  Plus, X, ChevronDown, Loader2, Brain, Trash2,
} from 'lucide-react'
import Link from 'next/link'

export default function PracticePage() {
  const [teams, setTeams] = useState<Team[]>([])
  const [selectedTeam, setSelectedTeam] = useState<Team | null>(null)
  const [selectedTeamId, setSelectedTeamId] = useState('')
  const [plans, setPlans] = useState<PracticePlan[]>([])
  const [loading, setLoading] = useState(false)

  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showAiModal, setShowAiModal] = useState(false)

  const [form, setForm] = useState({
    date: '', title: '', duration_minutes: 90, notes: '',
  })
  const [saving, setSaving] = useState(false)

  const [aiForm, setAiForm] = useState({
    focus_areas: '', duration_minutes: 90, player_count: '', notes: '',
  })
  const [generating, setGenerating] = useState(false)
  const [aiResult, setAiResult] = useState<string>('')

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
    practiceApi.list(selectedTeamId).then(setPlans).finally(() => setLoading(false))
  }, [selectedTeamId, teams])

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const newPlan = await practiceApi.create({
        ...form,
        team_id: selectedTeamId,
        drills: [],
      })
      setPlans((prev) => [newPlan, ...prev])
      setShowCreateModal(false)
      setForm({ date: '', title: '', duration_minutes: 90, notes: '' })
    } finally {
      setSaving(false)
    }
  }

  const handleGenerateAi = async (e: FormEvent) => {
    e.preventDefault()
    if (!selectedTeam) return
    setGenerating(true)
    setAiResult('')
    try {
      const focusAreas = aiForm.focus_areas
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)

      const res = await practiceApi.generate({
        team_id: selectedTeamId,
        sport: selectedTeam.sport,
        focus_areas: focusAreas,
        duration_minutes: aiForm.duration_minutes,
        player_count: aiForm.player_count ? parseInt(aiForm.player_count) : undefined,
        notes: aiForm.notes,
      })

      setPlans((prev) => [res.plan, ...prev])
      setAiResult(res.ai_notes || 'Practice plan generated and saved!')
    } finally {
      setGenerating(false)
    }
  }

  const handleDelete = async (planId: string) => {
    if (!confirm('Delete this practice plan?')) return
    await practiceApi.delete(planId)
    setPlans((prev) => prev.filter((p) => p.id !== planId))
  }

  const upcoming = plans.filter((p) => p.date >= new Date().toISOString().split('T')[0])
  const past = plans.filter((p) => p.date < new Date().toISOString().split('T')[0])

  return (
    <div>
      <div className="page-header flex items-center justify-between">
        <div>
          <h1 className="page-title">Practice Plans</h1>
          <p className="page-subtitle">Manage drills and training sessions</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setShowAiModal(true)}
            className="btn-secondary flex items-center gap-2"
            disabled={!selectedTeamId}
          >
            <Brain className="w-4 h-4" />
            Generate with AI
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn-primary flex items-center gap-2"
            disabled={!selectedTeamId}
          >
            <Plus className="w-4 h-4" />
            New Plan
          </button>
        </div>
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
        <div className="text-[#6b7280] text-sm">Loading practice plans...</div>
      ) : (
        <div className="space-y-8">
          <section>
            <h2 className="text-[#9ca3af] text-xs font-medium uppercase tracking-wider mb-4">
              Upcoming ({upcoming.length})
            </h2>
            {upcoming.length === 0 ? (
              <div className="card p-6 text-center text-[#6b7280] text-sm">
                No upcoming practice plans.
              </div>
            ) : (
              <div className="space-y-3">
                {upcoming.map((plan) => (
                  <PlanCard key={plan.id} plan={plan} onDelete={handleDelete} />
                ))}
              </div>
            )}
          </section>

          {past.length > 0 && (
            <section>
              <h2 className="text-[#9ca3af] text-xs font-medium uppercase tracking-wider mb-4">
                Past Plans ({past.length})
              </h2>
              <div className="space-y-3">
                {[...past].reverse().map((plan) => (
                  <PlanCard key={plan.id} plan={plan} onDelete={handleDelete} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {/* Create modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-[#161616] border border-[#1e1e1e] rounded-2xl w-full max-w-md">
            <div className="flex items-center justify-between p-6 border-b border-[#1e1e1e]">
              <h2 className="text-white font-semibold text-lg">New Practice Plan</h2>
              <button onClick={() => setShowCreateModal(false)} className="text-[#6b7280] hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleCreate} className="p-6 space-y-4">
              <div>
                <label className="label">Title *</label>
                <input
                  type="text"
                  required
                  value={form.title}
                  onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                  className="input"
                  placeholder="Monday Offense Practice"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="label">Date *</label>
                  <input
                    type="date"
                    required
                    value={form.date}
                    onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))}
                    className="input"
                  />
                </div>
                <div>
                  <label className="label">Duration (min)</label>
                  <input
                    type="number"
                    min="15"
                    value={form.duration_minutes}
                    onChange={(e) => setForm((f) => ({ ...f, duration_minutes: parseInt(e.target.value) }))}
                    className="input"
                  />
                </div>
              </div>
              <div>
                <label className="label">Notes</label>
                <textarea
                  value={form.notes}
                  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                  className="input resize-none h-20"
                  placeholder="Practice objectives..."
                />
              </div>
              <div className="flex gap-3">
                <button type="submit" disabled={saving} className="btn-primary flex-1 flex items-center justify-center gap-2">
                  {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                  {saving ? 'Creating...' : 'Create Plan'}
                </button>
                <button type="button" onClick={() => setShowCreateModal(false)} className="btn-secondary flex-1">
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* AI Generate modal */}
      {showAiModal && selectedTeam && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-[#161616] border border-[#1e1e1e] rounded-2xl w-full max-w-md">
            <div className="flex items-center justify-between p-6 border-b border-[#1e1e1e]">
              <div className="flex items-center gap-2">
                <Brain className="w-5 h-5 text-[#2563eb]" />
                <h2 className="text-white font-semibold text-lg">Generate Practice Plan</h2>
              </div>
              <button onClick={() => setShowAiModal(false)} className="text-[#6b7280] hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleGenerateAi} className="p-6 space-y-4">
              <div className="bg-[#0d0d0d] rounded-lg p-3 border border-[#1e1e1e]">
                <p className="text-[#9ca3af] text-xs">
                  Sport: <span className="text-white capitalize">{selectedTeam.sport}</span>
                </p>
              </div>
              <div>
                <label className="label">Focus Areas *</label>
                <input
                  type="text"
                  required
                  value={aiForm.focus_areas}
                  onChange={(e) => setAiForm((f) => ({ ...f, focus_areas: e.target.value }))}
                  className="input"
                  placeholder="offense, passing, footwork (comma separated)"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="label">Duration (min)</label>
                  <input
                    type="number"
                    min="30"
                    max="240"
                    value={aiForm.duration_minutes}
                    onChange={(e) => setAiForm((f) => ({ ...f, duration_minutes: parseInt(e.target.value) }))}
                    className="input"
                  />
                </div>
                <div>
                  <label className="label">Player Count</label>
                  <input
                    type="number"
                    min="1"
                    value={aiForm.player_count}
                    onChange={(e) => setAiForm((f) => ({ ...f, player_count: e.target.value }))}
                    className="input"
                    placeholder="Optional"
                  />
                </div>
              </div>
              <div>
                <label className="label">Additional Notes</label>
                <textarea
                  value={aiForm.notes}
                  onChange={(e) => setAiForm((f) => ({ ...f, notes: e.target.value }))}
                  className="input resize-none h-16"
                  placeholder="Any special focus areas or constraints..."
                />
              </div>
              {aiResult && (
                <div className="bg-[#0d0d0d] rounded-lg p-3 border border-green-800/50">
                  <p className="text-green-400 text-xs">{aiResult}</p>
                  <p className="text-[#6b7280] text-xs mt-1">Plan saved to your schedule!</p>
                </div>
              )}
              <div className="flex gap-3">
                <button type="submit" disabled={generating} className="btn-primary flex-1 flex items-center justify-center gap-2">
                  {generating && <Loader2 className="w-4 h-4 animate-spin" />}
                  {generating ? 'Generating...' : 'Generate Plan'}
                </button>
                <button type="button" onClick={() => setShowAiModal(false)} className="btn-secondary flex-1">
                  {aiResult ? 'Close' : 'Cancel'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

function PlanCard({ plan, onDelete }: { plan: PracticePlan; onDelete: (id: string) => void }) {
  const drillCount = Array.isArray(plan.drills) ? plan.drills.length : 0
  return (
    <div className="card p-5 flex items-center justify-between">
      <div className="flex items-center gap-5">
        <div className="text-center w-14">
          <p className="text-[#9ca3af] text-xs">
            {new Date(plan.date + 'T12:00:00').toLocaleDateString('en-US', { month: 'short' })}
          </p>
          <p className="text-white text-2xl font-bold leading-none">
            {new Date(plan.date + 'T12:00:00').getDate()}
          </p>
        </div>
        <div>
          <p className="text-white font-semibold">{plan.title}</p>
          <p className="text-[#6b7280] text-xs mt-0.5">
            {plan.duration_minutes && `${plan.duration_minutes} min`}
            {plan.duration_minutes && drillCount > 0 && ' · '}
            {drillCount > 0 && `${drillCount} drills`}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Link
          href={`/practice/${plan.id}`}
          className="btn-secondary text-xs px-3 py-1.5"
        >
          View Plan
        </Link>
        <button
          onClick={() => onDelete(plan.id)}
          className="p-2 text-[#6b7280] hover:text-red-400 transition-colors"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
