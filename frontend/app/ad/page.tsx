'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { Download, AlertTriangle, CheckCircle2 } from 'lucide-react'

interface Coach {
  user_id: string; name: string; email: string; role: string
  runs_in_range: number; runs_this_month: number
  monthly_limit: number | null; remaining: number | null
}
interface Usage {
  range: { from: string; to: string }
  total_runs: number
  by_sport: Record<string, number>
  by_type: Record<string, number>
  coaches: Coach[]
}
interface InactiveCoach {
  user_id: string; name: string; email: string; role: string
  last_active_at: string | null; days_inactive: number | null; never_active: boolean
}
interface Inactive {
  days: number; as_of: string; total_coaches: number; inactive_count: number
  inactive: InactiveCoach[]
}

const AD_TIERS = ['athletic_dept', 'district']

export default function AdDashboardPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [usage, setUsage] = useState<Usage | null>(null)
  const [loading, setLoading] = useState(false)
  const [limitEdits, setLimitEdits] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState('')
  const [inactive, setInactive] = useState<Inactive | null>(null)
  const [days, setDays] = useState(14)

  const isAd = AD_TIERS.includes(user?.organization?.subscription_tier || '')

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => { if (isAd) { load(); loadInactive() } }, [isAd])

  function flash(t: string) { setMsg(t); setTimeout(() => setMsg(''), 3000) }
  async function load() {
    setLoading(true)
    try { const r = await api.get('/ad/usage'); setUsage(r.data) } catch {} finally { setLoading(false) }
  }
  async function loadInactive(d = days) {
    try { const r = await api.get(`/ad/inactive-coaches?days=${d}`); setInactive(r.data) } catch {}
  }
  async function saveLimit(userId: string) {
    const raw = limitEdits[userId]
    const val = raw === '' || raw == null ? 0 : parseInt(raw, 10)
    if (isNaN(val)) return
    try {
      await api.post('/ad/limits', { user_id: userId, monthly_run_limit: val })
      setLimitEdits(e => { const n = { ...e }; delete n[userId]; return n })
      await load(); flash('Limit saved.')
    } catch {}
  }
  async function exportCsv() {
    try {
      const res = await api.get('/ad/usage/export', { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }))
      const a = document.createElement('a'); a.href = url; a.download = 'coachlenz-usage.csv'; a.click()
      URL.revokeObjectURL(url)
    } catch {}
  }

  if (!isLoading && user && !isAd) {
    return (
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto p-8">
          <div className="max-w-lg mx-auto card text-center mt-16">
            <h2 className="text-xl font-bold mb-2">Usage Dashboard</h2>
            <p className="text-gray-400 text-sm mb-4">The usage dashboard, per-coach limits, and usage exports are part of the Athletic Dept and District plans.</p>
            <Link href="/settings/billing" className="btn-primary inline-block">See plans</Link>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-5xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-2xl font-bold">Usage Dashboard</h2>
              <p className="text-gray-400 text-sm">Analysis usage by coach this month, with per-coach limits.</p>
            </div>
            <button onClick={exportCsv} className="btn-secondary flex items-center gap-2"><Download size={16} /> Export CSV</button>
          </div>

          {msg && <div className="mb-4 text-sm bg-brand-500/10 border border-brand-500/30 text-brand-400 rounded p-2">{msg}</div>}

          {inactive && (
            <div className="card mb-6">
              <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
                <div className="flex items-center gap-2">
                  {inactive.inactive.length === 0
                    ? <CheckCircle2 size={18} className="text-brand-400" />
                    : <AlertTriangle size={18} className="text-gold" />}
                  <h3 className="font-semibold">Coach activity</h3>
                  <span className="text-xs text-gray-500">no login or analysis in {inactive.days} days</span>
                </div>
                <select value={days} onChange={e => { const d = Number(e.target.value); setDays(d); loadInactive(d) }}
                  className="input py-1 text-xs" style={{ width: 'auto' }}>
                  {[7, 14, 30, 60].map(d => <option key={d} value={d}>{d} days</option>)}
                </select>
              </div>
              {inactive.inactive.length === 0 ? (
                <p className="text-sm text-brand-400">
                  {inactive.total_coaches === 0 ? 'No other coaches on this account yet.' : `All ${inactive.total_coaches} coaches have been active in the last ${inactive.days} days.`}
                </p>
              ) : (
                <>
                  <div className="space-y-2">
                    {inactive.inactive.map(c => (
                      <div key={c.user_id} className="flex items-center justify-between border-b border-gray-800/60 pb-2">
                        <div>
                          <div className="text-sm">{c.name}</div>
                          <div className="text-xs text-gray-500">{c.email} · {c.role}</div>
                        </div>
                        <span className={`text-xs px-2 py-1 rounded ${c.never_active ? 'bg-red-400/10 text-red-400' : 'bg-gold/10 text-gold'}`}>
                          {c.never_active ? 'Never used' : `${c.days_inactive}d inactive`}
                        </span>
                      </div>
                    ))}
                  </div>
                  <p className="text-xs text-gray-600 mt-3">
                    {inactive.inactive_count} of {inactive.total_coaches} coaches flagged. Activity counts a login or an analysis run.
                  </p>
                </>
              )}
            </div>
          )}

          {loading || !usage ? (
            <p className="text-gray-400">Loading…</p>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-4 mb-6">
                <div className="card">
                  <div className="text-sm text-gray-400">Total runs (this month)</div>
                  <div className="text-3xl font-bold">{usage.total_runs}</div>
                </div>
                <div className="card">
                  <div className="text-sm text-gray-400 mb-1">By sport</div>
                  {Object.entries(usage.by_sport).map(([s, n]) => <div key={s} className="text-sm flex justify-between"><span className="text-gray-300 capitalize">{s}</span><span className="font-mono">{n}</span></div>)}
                  {Object.keys(usage.by_sport).length === 0 && <div className="text-sm text-gray-600">—</div>}
                </div>
                <div className="card">
                  <div className="text-sm text-gray-400 mb-1">By type</div>
                  {Object.entries(usage.by_type).map(([t, n]) => <div key={t} className="text-sm flex justify-between"><span className="text-gray-300">{t}</span><span className="font-mono">{n}</span></div>)}
                  {Object.keys(usage.by_type).length === 0 && <div className="text-sm text-gray-600">—</div>}
                </div>
              </div>

              <div className="card">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-gray-400 border-b border-gray-800">
                    <th className="py-2">Coach</th><th className="py-2">Role</th><th className="py-2 text-center">This month</th><th className="py-2 text-center">Monthly limit</th><th className="py-2 text-center">Remaining</th><th></th>
                  </tr></thead>
                  <tbody>
                    {usage.coaches.map(c => {
                      const editing = c.user_id in limitEdits
                      return (
                        <tr key={c.user_id} className="border-b border-gray-800/60">
                          <td className="py-2"><div>{c.name}</div><div className="text-xs text-gray-500">{c.email}</div></td>
                          <td className="py-2 text-gray-400">{c.role}</td>
                          <td className="py-2 text-center font-mono">{c.runs_this_month}</td>
                          <td className="py-2 text-center">
                            <input type="number" min={0} className="input py-1 w-24 text-center text-xs mx-auto"
                              value={editing ? limitEdits[c.user_id] : (c.monthly_limit ?? '')}
                              placeholder="∞"
                              onChange={e => setLimitEdits(m => ({ ...m, [c.user_id]: e.target.value }))} />
                          </td>
                          <td className="py-2 text-center font-mono">{c.remaining == null ? '∞' : c.remaining}</td>
                          <td className="py-2 text-right">{editing && <button onClick={() => saveLimit(c.user_id)} className="btn-primary text-xs py-1">Save</button>}</td>
                        </tr>
                      )
                    })}
                    {usage.coaches.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-gray-500">No coaches yet.</td></tr>}
                  </tbody>
                </table>
                <p className="text-xs text-gray-600 mt-3">Set a monthly limit to cap a coach&apos;s analyses. 0 or blank = unlimited.</p>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  )
}
