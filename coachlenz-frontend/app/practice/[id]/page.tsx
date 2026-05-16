'use client'

import { useState, useEffect, FormEvent } from 'react'
import { useParams } from 'next/navigation'
import { practiceApi, PracticePlan, Drill } from '@/lib/api'
import {
  ArrowLeft, Save, Loader2, CheckSquare, Square, Clock, Zap,
} from 'lucide-react'
import Link from 'next/link'

export default function PracticeDetailPage() {
  const params = useParams()
  const planId = params.id as string

  const [plan, setPlan] = useState<PracticePlan | null>(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [checkedDrills, setCheckedDrills] = useState<Set<number>>(new Set())

  const [form, setForm] = useState({
    title: '',
    date: '',
    duration_minutes: 90,
    notes: '',
  })

  useEffect(() => {
    practiceApi
      .get(planId)
      .then((p) => {
        setPlan(p)
        setForm({
          title: p.title,
          date: p.date,
          duration_minutes: p.duration_minutes || 90,
          notes: p.notes || '',
        })
      })
      .finally(() => setLoading(false))
  }, [planId])

  const handleSave = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const updated = await practiceApi.update(planId, form)
      setPlan(updated)
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  const toggleDrill = (index: number) => {
    setCheckedDrills((prev) => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }

  const intensityColor = (intensity?: string) => {
    if (intensity === 'high') return 'text-red-400'
    if (intensity === 'medium') return 'text-yellow-400'
    return 'text-green-400'
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-[#2563eb]" />
      </div>
    )
  }

  if (!plan) {
    return (
      <div className="text-center py-20">
        <p className="text-[#6b7280]">Practice plan not found.</p>
        <Link href="/practice" className="text-[#2563eb] text-sm mt-2 inline-block">
          Back to Practice Plans
        </Link>
      </div>
    )
  }

  const drills: Drill[] = Array.isArray(plan.drills) ? plan.drills : []
  const completedCount = checkedDrills.size
  const totalDrills = drills.length

  return (
    <div>
      <div className="page-header">
        <Link
          href="/practice"
          className="flex items-center gap-2 text-[#6b7280] hover:text-white text-sm mb-4 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Practice Plans
        </Link>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="page-title">{plan.title}</h1>
            <p className="text-[#6b7280] text-sm mt-1">
              {new Date(plan.date + 'T12:00:00').toLocaleDateString('en-US', {
                weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
              })}
              {plan.duration_minutes && ` · ${plan.duration_minutes} minutes`}
            </p>
          </div>
          <button
            onClick={() => setEditing(!editing)}
            className="btn-secondary flex items-center gap-2"
          >
            {editing ? 'Cancel Edit' : 'Edit Plan'}
          </button>
        </div>
      </div>

      {editing && (
        <form onSubmit={handleSave} className="card p-6 mb-6">
          <h2 className="text-white font-semibold mb-4">Edit Practice Plan</h2>
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="label">Title</label>
              <input
                type="text"
                value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                className="input"
              />
            </div>
            <div>
              <label className="label">Date</label>
              <input
                type="date"
                value={form.date}
                onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))}
                className="input"
              />
            </div>
            <div>
              <label className="label">Duration (min)</label>
              <input
                type="number"
                value={form.duration_minutes}
                onChange={(e) => setForm((f) => ({ ...f, duration_minutes: parseInt(e.target.value) }))}
                className="input"
              />
            </div>
            <div className="col-span-2">
              <label className="label">Notes</label>
              <textarea
                value={form.notes}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                className="input resize-none h-24"
              />
            </div>
          </div>
          <div className="flex gap-3 mt-4">
            <button type="submit" disabled={saving} className="btn-primary flex items-center gap-2">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      )}

      {/* Progress bar */}
      {totalDrills > 0 && (
        <div className="card p-4 mb-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[#9ca3af] text-xs font-medium">Practice Progress</span>
            <span className="text-white text-xs font-semibold">
              {completedCount}/{totalDrills} drills
            </span>
          </div>
          <div className="w-full h-2 bg-[#1e1e1e] rounded-full overflow-hidden">
            <div
              className="h-full bg-[#2563eb] rounded-full transition-all duration-300"
              style={{ width: `${totalDrills > 0 ? (completedCount / totalDrills) * 100 : 0}%` }}
            />
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-6">
        {/* Drills list */}
        <div className="col-span-2 space-y-3">
          <h2 className="text-white font-semibold">
            Drills ({totalDrills})
          </h2>
          {totalDrills === 0 ? (
            <div className="card p-6 text-center text-[#6b7280] text-sm">
              No drills in this plan. Use AI generation to populate drills.
            </div>
          ) : (
            drills.map((drill, i) => (
              <div
                key={i}
                onClick={() => toggleDrill(i)}
                className={`card p-5 cursor-pointer transition-all ${
                  checkedDrills.has(i) ? 'opacity-60 border-[#2563eb]/30' : 'hover:border-[#2563eb]/30'
                }`}
              >
                <div className="flex items-start gap-4">
                  <div className="mt-0.5 flex-shrink-0">
                    {checkedDrills.has(i) ? (
                      <CheckSquare className="w-5 h-5 text-[#2563eb]" />
                    ) : (
                      <Square className="w-5 h-5 text-[#4b5563]" />
                    )}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center justify-between mb-1">
                      <h3 className={`font-semibold text-sm ${checkedDrills.has(i) ? 'line-through text-[#6b7280]' : 'text-white'}`}>
                        {drill.name}
                      </h3>
                      <div className="flex items-center gap-3">
                        {drill.intensity && (
                          <div className="flex items-center gap-1">
                            <Zap className={`w-3 h-3 ${intensityColor(drill.intensity)}`} />
                            <span className={`text-xs capitalize ${intensityColor(drill.intensity)}`}>
                              {drill.intensity}
                            </span>
                          </div>
                        )}
                        {drill.duration_minutes && (
                          <div className="flex items-center gap-1 text-[#6b7280]">
                            <Clock className="w-3 h-3" />
                            <span className="text-xs">{drill.duration_minutes} min</span>
                          </div>
                        )}
                      </div>
                    </div>
                    <p className="text-[#9ca3af] text-sm">{drill.description}</p>
                    {drill.focus && (
                      <p className="text-[#6b7280] text-xs mt-2">
                        Focus: <span className="text-[#9ca3af]">{drill.focus}</span>
                      </p>
                    )}
                    {drill.equipment && drill.equipment.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {drill.equipment.map((eq, j) => (
                          <span
                            key={j}
                            className="text-xs px-2 py-0.5 bg-[#1e1e1e] text-[#9ca3af] rounded"
                          >
                            {eq}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Notes panel */}
        <div className="space-y-4">
          <div className="card p-5">
            <h3 className="text-white font-semibold text-sm mb-3">Coaching Notes</h3>
            {plan.notes ? (
              <p className="text-[#9ca3af] text-sm leading-relaxed">{plan.notes}</p>
            ) : (
              <p className="text-[#4b5563] text-sm italic">No notes for this session.</p>
            )}
          </div>

          <div className="card p-5">
            <h3 className="text-white font-semibold text-sm mb-3">Session Info</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-[#6b7280]">Date</span>
                <span className="text-white">
                  {new Date(plan.date + 'T12:00:00').toLocaleDateString()}
                </span>
              </div>
              {plan.duration_minutes && (
                <div className="flex justify-between">
                  <span className="text-[#6b7280]">Duration</span>
                  <span className="text-white">{plan.duration_minutes} min</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-[#6b7280]">Drills</span>
                <span className="text-white">{totalDrills}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#6b7280]">Completed</span>
                <span className="text-[#2563eb] font-medium">
                  {completedCount}/{totalDrills}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
