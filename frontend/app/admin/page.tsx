'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'
import { ShieldCheck, Users, AlertTriangle, Trash2, ToggleLeft, ToggleRight, TrendingUp } from 'lucide-react'
import ConfirmModal from '@/components/ConfirmModal'

export default function AdminPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [orgs, setOrgs] = useState<any[]>([])
  const [stats, setStats] = useState<any>(null)
  const [flags, setFlags] = useState<any[]>([])
  const [features, setFeatures] = useState<any[]>([])
  const [retention, setRetention] = useState<any>(null)
  const [funnel, setFunnel] = useState<any>(null)
  const [costs, setCosts] = useState<any>(null)
  const [detection, setDetection] = useState<any>(null)
  const [tab, setTab] = useState<'orgs'|'retention'|'funnel'|'detection'|'costs'|'features'|'flags'|'stats'>('orgs')
  const [orgToDelete, setOrgToDelete] = useState<{id: string, name: string} | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => { fetchMe() }, [])
  useEffect(() => {
    if (!isLoading && !user) { router.push('/login'); return }
    if (!isLoading && user && !user.organization.admin_level) router.push('/dashboard')
  }, [isLoading, user])
  useEffect(() => {
    if (!user?.organization.admin_level) return
    api.get('/admin/orgs').then(r => setOrgs(r.data))
    api.get('/admin/stats').then(r => setStats(r.data))
    api.get('/admin/risk-flags').then(r => setFlags(r.data))
    api.get('/admin/feature-flags').then(r => setFeatures(r.data.flags || [])).catch(() => {})
    api.get('/admin/retention').then(r => setRetention(r.data)).catch(() => {})
    api.get('/admin/funnel').then(r => setFunnel(r.data)).catch(() => {})
    api.get('/admin/analysis-costs').then(r => setCosts(r.data)).catch(() => {})
    api.get('/admin/detection-quality').then(r => setDetection(r.data)).catch(() => {})
  }, [user])

  const gateStyle: Record<string, string> = {
    pass: 'bg-brand-500/15 text-brand-400',
    watch: 'bg-yellow-500/15 text-yellow-400',
    stop: 'bg-red-500/15 text-red-400',
    maturing: 'bg-gray-700 text-gray-400',
    no_data: 'bg-gray-700 text-gray-400',
  }
  const pct = (r: number | null) => r === null || r === undefined ? '-' : `${Math.round(r * 100)}%`

  async function toggleFeature(key: string, enabled: boolean) {
    try {
      await api.put(`/admin/feature-flags/${key}`, { enabled: !enabled })
      setFeatures(fs => fs.map(f => f.key === key ? { ...f, enabled: !enabled, source: 'override' } : f))
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Could not toggle feature.')
    }
  }

  async function toggleTenure(orgId: string, current: boolean) {
    await api.patch(`/admin/orgs/${orgId}`, { has_coach_tenure_access: !current })
    setOrgs(o => o.map(x => x.id === orgId ? { ...x, has_coach_tenure_access: !current } : x))
  }

  async function deleteOrg() {
    if (!orgToDelete) return
    setErr(''); setDeleting(true)
    try {
      await api.delete(`/admin/orgs/${orgToDelete.id}`)
      setOrgs(o => o.filter(x => x.id !== orgToDelete.id))
      setOrgToDelete(null)
    } catch (e: any) {
      setErr(e.response?.data?.detail || `Could not delete "${orgToDelete.name}".`)
      setOrgToDelete(null)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-2xl font-bold mb-6 flex items-center gap-3"><ShieldCheck className="text-brand-400" /> Admin Panel</h2>
          {err && <div className="mb-4 text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-2">{err}</div>}
          <div className="flex gap-2 mb-6">
            {(['orgs','retention','funnel','detection','costs','features','flags','stats'] as const).map(t => (
              <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === t ? 'bg-brand-500 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-100'}`}>{t === 'orgs' ? 'Organizations' : t === 'retention' ? 'Retention' : t === 'funnel' ? 'Funnel' : t === 'detection' ? 'Film Quality' : t === 'costs' ? 'Costs' : t === 'features' ? 'Feature Toggles' : t === 'flags' ? 'Risk Flags' : 'Stats'}</button>
            ))}
          </div>
          {tab === 'stats' && stats && (
            <div className="grid grid-cols-4 gap-4">
              {Object.entries(stats).map(([k, v]) => (
                <div key={k} className="card text-center"><div className="text-2xl font-bold">{v as number}</div><div className="text-sm text-gray-400 capitalize">{k.replace(/_/g,' ')}</div></div>
              ))}
            </div>
          )}
          {tab === 'retention' && (
            <div className="space-y-6">
              <p className="text-sm text-gray-400 flex items-center gap-2"><TrendingUp size={16} className="text-brand-400" /> The retention gate. A cohort is a signup week. <span className="text-gray-300">Return</span> = share that ran a 2nd film analysis within 30 days (the gated number). <span className="text-gray-300">Activation</span> = share that ran their 1st within 7 days. Cohorts still inside the 30-day window show as maturing and do not count toward the verdict.</p>
              {retention && (
                <>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="card">
                      <div className="text-sm text-gray-400">Return (matured)</div>
                      <div className="text-3xl font-bold">{pct(retention.summary.return_rate)}</div>
                      <div className="mt-1"><span className={`text-[11px] px-2 py-0.5 rounded uppercase font-medium ${gateStyle[retention.summary.gate]}`}>{retention.summary.gate}</span></div>
                    </div>
                    <div className="card">
                      <div className="text-sm text-gray-400">Activation (matured)</div>
                      <div className="text-3xl font-bold">{pct(retention.summary.activation_rate)}</div>
                      <div className="text-xs text-gray-500 mt-1">1st analysis in {retention.summary.activation_window_days}d</div>
                    </div>
                    <div className="card">
                      <div className="text-sm text-gray-400">Pass bar / stop line</div>
                      <div className="text-3xl font-bold">{pct(retention.summary.return_bar)} <span className="text-gray-500 text-lg">/ {pct(retention.summary.stop_line)}</span></div>
                      <div className="text-xs text-gray-500 mt-1">build breadth above the bar</div>
                    </div>
                    <div className="card">
                      <div className="text-sm text-gray-400">Matured cohorts</div>
                      <div className="text-3xl font-bold">{retention.summary.matured_cohorts}</div>
                      <div className="text-xs text-gray-500 mt-1">{retention.summary.matured_orgs} orgs judged</div>
                    </div>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead><tr className="text-gray-400 border-b border-gray-800"><th className="text-left pb-3">Cohort (signup week)</th><th className="text-right pb-3">Coaches</th><th className="text-right pb-3">Activation</th><th className="text-right pb-3">Return</th><th className="text-right pb-3">Gate</th></tr></thead>
                      <tbody className="divide-y divide-gray-800">
                        {retention.cohorts.map((c: any) => (
                          <tr key={c.cohort}>
                            <td className="py-3">{c.cohort}</td>
                            <td className="py-3 text-right">{c.size}</td>
                            <td className="py-3 text-right">{pct(c.activation_rate)} <span className="text-gray-500">({c.activated})</span></td>
                            <td className="py-3 text-right">{c.matured ? pct(c.return_rate) : <span className="text-gray-500">maturing</span>} <span className="text-gray-500">({c.returned})</span></td>
                            <td className="py-3 text-right"><span className={`text-[11px] px-2 py-0.5 rounded uppercase font-medium ${gateStyle[c.gate]}`}>{c.gate}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {retention.cohorts.length === 0 && <div className="text-center text-gray-500 py-12">No cohorts yet. The gate populates as coaches sign up and analyze film.</div>}
                  </div>
                </>
              )}
              {!retention && <div className="text-center text-gray-500 py-12">Loading retention…</div>}
            </div>
          )}
          {tab === 'funnel' && (
            <div className="space-y-6">
              <p className="text-sm text-gray-400 flex items-center gap-2"><TrendingUp size={16} className="text-brand-400" /> The conversion gate. Visitor to completed signup over the last {funnel?.window_days || 30} days. Top steps count unique visitors; the two signup steps are recorded server-side. Conversion stops where retention starts, so activation and paid live on the Retention tab and in billing.</p>
              {funnel && (
                <>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                    <div className="card">
                      <div className="text-sm text-gray-400">Visitor to signup</div>
                      <div className="text-3xl font-bold">{pct(funnel.visitor_to_signup)}</div>
                      <div className="mt-1"><span className={`text-[11px] px-2 py-0.5 rounded uppercase font-medium ${gateStyle[funnel.gate]}`}>{funnel.gate === 'no_data' ? 'no data' : funnel.gate}</span></div>
                    </div>
                    <div className="card">
                      <div className="text-sm text-gray-400">Pass bar / stop line</div>
                      <div className="text-3xl font-bold">{pct(funnel.conversion_bar)} <span className="text-gray-500 text-lg">/ {pct(funnel.stop_line)}</span></div>
                      <div className="text-xs text-gray-500 mt-1">scale paid traffic only above the bar</div>
                    </div>
                    <div className="card">
                      <div className="text-sm text-gray-400">Biggest drop-off</div>
                      {funnel.biggest_drop ? (
                        <>
                          <div className="text-lg font-bold">{funnel.biggest_drop.from_label} to {funnel.biggest_drop.to_label}</div>
                          <div className="text-xs text-gray-500 mt-1">lost {funnel.biggest_drop.lost} ({pct(funnel.biggest_drop.drop_rate)} of the step)</div>
                        </>
                      ) : <div className="text-lg text-gray-500">No traffic yet</div>}
                    </div>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead><tr className="text-gray-400 border-b border-gray-800"><th className="text-left pb-3">Step</th><th className="text-right pb-3">Count</th><th className="text-right pb-3">From previous</th></tr></thead>
                      <tbody className="divide-y divide-gray-800">
                        {funnel.steps.map((s: any, i: number) => {
                          const conv = i === 0 ? null : funnel.step_conversion[i - 1]
                          return (
                            <tr key={s.step}>
                              <td className="py-3">{s.label}</td>
                              <td className="py-3 text-right">{s.count}</td>
                              <td className="py-3 text-right">{conv ? pct(conv.rate) : <span className="text-gray-500">-</span>}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                    {funnel.steps.every((s: any) => s.count === 0) && <div className="text-center text-gray-500 py-12">No funnel events yet. This populates as visitors hit the landing page and move through signup.</div>}
                  </div>
                  {funnel.by_source && funnel.by_source.length > 0 && (
                    <div>
                      <h3 className="text-xs uppercase tracking-wide text-gray-500 mb-2">By channel</h3>
                      <p className="text-xs text-gray-500 mb-3">Prove one channel clears the gate on qualified traffic before scaling it. Do not split across channels at once.</p>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead><tr className="text-gray-400 border-b border-gray-800"><th className="text-left pb-3">Channel</th><th className="text-right pb-3">Visitors</th><th className="text-right pb-3">Signups</th><th className="text-right pb-3">Visitor to signup</th><th className="text-right pb-3">Gate</th></tr></thead>
                          <tbody className="divide-y divide-gray-800">
                            {funnel.by_source.map((s: any) => (
                              <tr key={s.source}>
                                <td className="py-3">{s.source}</td>
                                <td className="py-3 text-right">{s.visitors}</td>
                                <td className="py-3 text-right">{s.signups}</td>
                                <td className="py-3 text-right">{pct(s.visitor_to_signup)}</td>
                                <td className="py-3 text-right"><span className={`text-[11px] px-2 py-0.5 rounded uppercase font-medium ${gateStyle[s.gate]}`}>{s.gate === 'no_data' ? 'no data' : s.gate}</span></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </>
              )}
              {!funnel && <div className="text-center text-gray-500 py-12">Loading funnel…</div>}
            </div>
          )}
          {tab === 'detection' && (
            <div className="space-y-6">
              <p className="text-sm text-gray-400 flex items-center gap-2"><TrendingUp size={16} className="text-brand-400" /> The detection-quality gate. Does the agent actually chop the plays. <span className="text-gray-300">Recall</span> = plays auto-detected out of every play on the game (a play the coach added by hand is a snap we missed), so this is a floor unless a true count is set. <span className="text-gray-300">Label edits</span> = share of found plays the coach had to relabel. The cut by film resolution is the whole point: it shows whether misses come from the model or from bad film.</p>
              {detection && (
                <>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="card">
                      <div className="text-sm text-gray-400">Recall ({detection.overall.measurement})</div>
                      <div className="text-3xl font-bold">{pct(detection.overall.recall)}</div>
                      <div className="mt-1"><span className={`text-[11px] px-2 py-0.5 rounded uppercase font-medium ${gateStyle[detection.overall.recall_verdict]}`}>{detection.overall.recall_verdict === 'no_data' ? 'no data' : detection.overall.recall_verdict}</span></div>
                    </div>
                    <div className="card">
                      <div className="text-sm text-gray-400">Pass bar / watch line</div>
                      <div className="text-3xl font-bold">{pct(detection.recall_pass_bar)} <span className="text-gray-500 text-lg">/ {pct(detection.recall_watch_line)}</span></div>
                      <div className="text-xs text-gray-500 mt-1">a true 90% is top notch</div>
                    </div>
                    <div className="card">
                      <div className="text-sm text-gray-400">Label edit rate</div>
                      <div className="text-3xl font-bold">{pct(detection.overall.label_edit_rate)}</div>
                      <div className="mt-1"><span className={`text-[11px] px-2 py-0.5 rounded uppercase font-medium ${gateStyle[detection.overall.label_verdict]}`}>{detection.overall.label_verdict === 'no_data' ? 'no data' : detection.overall.label_verdict}</span></div>
                    </div>
                    <div className="card">
                      <div className="text-sm text-gray-400">Speed (median)</div>
                      <div className="text-3xl font-bold">{detection.overall.median_realtime_ratio === null ? '-' : `${detection.overall.median_realtime_ratio}x`}</div>
                      <div className="text-xs text-gray-500 mt-1">run time / film length</div>
                    </div>
                  </div>

                  {detection.by_film_quality.length > 0 && (
                    <div>
                      <h3 className="text-xs uppercase tracking-wide text-gray-500 mb-2">By film quality</h3>
                      <p className="text-xs text-gray-500 mb-3">If HD passes and SD stops, the leak is the film, not the model. Curate the first coach onto HD, end-zone or sideline all-22.</p>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead><tr className="text-gray-400 border-b border-gray-800"><th className="text-left pb-3">Film</th><th className="text-right pb-3">Games</th><th className="text-right pb-3">Plays</th><th className="text-right pb-3">Recall</th><th className="text-right pb-3">Label edits</th><th className="text-right pb-3">Verdict</th></tr></thead>
                          <tbody className="divide-y divide-gray-800">
                            {detection.by_film_quality.map((b: any) => (
                              <tr key={b.label}>
                                <td className="py-3">{b.label}</td>
                                <td className="py-3 text-right">{b.games}</td>
                                <td className="py-3 text-right">{b.total_plays}</td>
                                <td className="py-3 text-right">{pct(b.recall)}</td>
                                <td className="py-3 text-right">{pct(b.label_edit_rate)}</td>
                                <td className="py-3 text-right"><span className={`text-[11px] px-2 py-0.5 rounded uppercase font-medium ${gateStyle[b.recall_verdict]}`}>{b.recall_verdict === 'no_data' ? 'no data' : b.recall_verdict}</span></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  <div className="overflow-x-auto">
                    <h3 className="text-xs uppercase tracking-wide text-gray-500 mb-2">Per game</h3>
                    <table className="w-full text-sm">
                      <thead><tr className="text-gray-400 border-b border-gray-800"><th className="text-left pb-3">Game</th><th className="text-left pb-3">Film</th><th className="text-right pb-3">Found</th><th className="text-right pb-3">Missed</th><th className="text-right pb-3">Recall</th><th className="text-right pb-3">Label edits</th><th className="text-right pb-3">Speed</th><th className="text-right pb-3">Verdict</th></tr></thead>
                      <tbody className="divide-y divide-gray-800">
                        {detection.games.map((g: any) => (
                          <tr key={g.game_id}>
                            <td className="py-3">{g.title || g.game_id.slice(0, 8)}<span className="text-gray-500"> {g.game_date || ''}</span></td>
                            <td className="py-3 uppercase text-gray-400">{g.film_quality === 'hd' ? 'HD' : g.film_quality === 'sd' ? 'SD' : '?'}</td>
                            <td className="py-3 text-right">{g.auto_plays}</td>
                            <td className="py-3 text-right">{g.coach_added_plays}</td>
                            <td className="py-3 text-right">{pct(g.recall)}{g.measurement === 'labeled' && <span className="text-brand-400"> *</span>}</td>
                            <td className="py-3 text-right">{pct(g.label_edit_rate)}</td>
                            <td className="py-3 text-right">{g.realtime_ratio === null ? '-' : `${g.realtime_ratio}x`}</td>
                            <td className="py-3 text-right"><span className={`text-[11px] px-2 py-0.5 rounded uppercase font-medium ${gateStyle[g.recall_verdict]}`}>{g.recall_verdict === 'no_data' ? 'no data' : g.recall_verdict}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {detection.games.length === 0 && <div className="text-center text-gray-500 py-12">No analyzed film yet. This fills in as coaches run film breakdowns. Recall reads as a floor until you set a true play count on a labeled game.</div>}
                    <p className="text-xs text-gray-500 mt-3">* recall measured against a confirmed true play count. Unmarked recall is a floor from coach-added plays.</p>
                  </div>
                </>
              )}
              {!detection && <div className="text-center text-gray-500 py-12">Loading film quality…</div>}
            </div>
          )}
          {tab === 'costs' && (
            <div className="space-y-4">
              <p className="text-sm text-gray-400">Real measured cost per analysis run (from our own token accounting), grouped by sport and type, checked against the {costs ? Math.round(costs.margin_floor * 100) : 65}% margin floor at the cheapest credit price (${costs?.floor_credit_price ?? 0.70}/credit). <span className="text-gray-300">pass</span> holds the floor, <span className="text-gray-300">watch</span> is 50-65%, <span className="text-gray-300">fail</span> is below 50%.</p>
              {costs && costs.groups?.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="text-gray-400 border-b border-gray-800"><th className="text-left pb-3">Sport</th><th className="text-left pb-3">Type</th><th className="text-right pb-3">Runs</th><th className="text-right pb-3">Avg cost</th><th className="text-right pb-3">Max</th><th className="text-right pb-3">Credits</th><th className="text-right pb-3">Rev @ floor</th><th className="text-right pb-3">Margin</th><th className="text-right pb-3">Verdict</th></tr></thead>
                    <tbody className="divide-y divide-gray-800">
                      {costs.groups.map((g: any) => {
                        const vstyle: Record<string,string> = { pass: 'bg-brand-500/15 text-brand-400', watch: 'bg-yellow-500/15 text-yellow-400', fail: 'bg-red-500/15 text-red-400', no_data: 'bg-gray-700 text-gray-400' }
                        return (
                          <tr key={g.sport + g.type}>
                            <td className="py-3 capitalize">{g.sport}</td>
                            <td className="py-3">{g.type === 'deep_grade' ? 'Deep + grade' : 'Standard'}</td>
                            <td className="py-3 text-right">{g.runs}</td>
                            <td className="py-3 text-right">${g.avg_usd}</td>
                            <td className="py-3 text-right text-gray-500">${g.max_usd}</td>
                            <td className="py-3 text-right">{g.credits}</td>
                            <td className="py-3 text-right text-gray-500">${g.revenue_at_floor}</td>
                            <td className="py-3 text-right">{g.margin_at_floor === null ? '-' : `${Math.round(g.margin_at_floor * 100)}%`}</td>
                            <td className="py-3 text-right"><span className={`text-[11px] px-2 py-0.5 rounded uppercase font-medium ${vstyle[g.verdict]}`}>{g.verdict === 'no_data' ? 'no data' : g.verdict}</span></td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              ) : <div className="text-center text-gray-500 py-12">No analysis cost data yet. This fills in as coaches run film analyses (measured from real token usage).</div>}
            </div>
          )}
          {tab === 'orgs' && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-gray-400 border-b border-gray-800"><th className="text-left pb-3">Name</th><th className="text-left pb-3">Tier</th><th className="text-left pb-3">Trial</th><th className="text-left pb-3">Tenure</th><th className="pb-3">Actions</th></tr></thead>
                <tbody className="divide-y divide-gray-800">
                  {orgs.map(o => (
                    <tr key={o.id}>
                      <td className="py-3">{o.name}</td>
                      <td className="py-3 capitalize">{o.subscription_tier}</td>
                      <td className="py-3">{o.is_trial ? 'Yes' : 'No'}</td>
                      <td className="py-3">{o.has_coach_tenure_access ? <span className="text-brand-400">On</span> : <span className="text-gray-500">Off</span>}</td>
                      <td className="py-3 text-center">
                        <button onClick={() => toggleTenure(o.id, o.has_coach_tenure_access)} className="text-xs btn-secondary py-1">{o.has_coach_tenure_access ? 'Disable Tenure' : 'Enable Tenure'}</button>
                        {o.id !== user?.organization?.id && (
                          <button onClick={() => { setErr(''); setOrgToDelete({ id: o.id, name: o.name }) }} title="Delete organization and all its data" className="text-xs text-red-400 hover:text-red-300 ml-3 inline-flex items-center gap-1"><Trash2 size={13} /> Delete</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {tab === 'features' && (
            <div className="space-y-6">
              <p className="text-sm text-gray-400">Toggle features on or off live. Changes take effect within ~20 seconds, no redeploy. A toggle overrides the shipped default; features you never touch stay on their default.</p>
              {Array.from(new Set(features.map(f => f.category))).map(cat => (
                <div key={cat}>
                  <h3 className="text-xs uppercase tracking-wide text-gray-500 mb-2">{cat}</h3>
                  <div className="space-y-2">
                    {features.filter(f => f.category === cat).map(f => (
                      <div key={f.key} className="card flex items-start gap-4">
                        <button onClick={() => toggleFeature(f.key, f.enabled)} title={f.enabled ? 'Turn off' : 'Turn on'} className="mt-0.5 shrink-0">
                          {f.enabled ? <ToggleRight size={34} className="text-brand-400" /> : <ToggleLeft size={34} className="text-gray-600" />}
                        </button>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{f.label}</span>
                            <span className={`text-[10px] px-1.5 py-0.5 rounded ${f.enabled ? 'bg-brand-500/15 text-brand-400' : 'bg-gray-700 text-gray-400'}`}>{f.enabled ? 'ON' : 'OFF'}</span>
                            {f.source === 'override' && <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-700 text-gray-400" title="Manually overriding the shipped default">override</span>}
                          </div>
                          <div className="text-sm text-gray-400 mt-0.5">{f.description}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              {features.length === 0 && <div className="text-center text-gray-500 py-12">No feature toggles available.</div>}
            </div>
          )}
          {tab === 'flags' && (
            <div className="space-y-3">
              {flags.map(f => (
                <div key={f.id} className="card flex items-center gap-4">
                  <AlertTriangle size={20} className={f.severity === 'critical' ? 'text-red-400' : f.severity === 'high' ? 'text-orange-400' : 'text-yellow-400'} />
                  <div>
                    <div className="font-medium">{f.flag_type}</div>
                    <div className="text-sm text-gray-400">{f.severity} · {new Date(f.created_at).toLocaleDateString()}</div>
                    <div className="text-xs text-gray-500 mt-1">{JSON.stringify(f.details)}</div>
                  </div>
                </div>
              ))}
              {flags.length === 0 && <div className="text-center text-gray-500 py-12">No unresolved risk flags.</div>}
            </div>
          )}
        </div>
        <ConfirmModal
          open={!!orgToDelete}
          title="Delete organization?"
          message={orgToDelete ? `Permanently delete "${orgToDelete.name}" and ALL of its data (users, film, reports, roster). This cannot be undone.` : ''}
          confirmLabel="Delete organization"
          busy={deleting}
          onConfirm={deleteOrg}
          onCancel={() => setOrgToDelete(null)}
        />
      </main>
    </div>
  )
}
