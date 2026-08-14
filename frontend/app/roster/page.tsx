'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth, usePermission } from '@/lib/auth'
import api from '@/lib/api'
import { Plus, Trash2, Upload, Copy, Users, BarChart3 } from 'lucide-react'
import ConfirmModal from '@/components/ConfirmModal'

interface Team { id: string; name: string; sport: string; season: string | null }
interface Player {
  id: string; jersey_number: string; first_name: string; last_name: string | null
  position: string | null; grade_year: string | null; height: string | null; weight: number | null
}
interface StatLine { plays: number; primary_plays: number; total_yards: number; games: number; by_play_type: Record<string, number> }
interface StatRow extends Player { stats: StatLine; top_play_types: { play_type: string; count: number }[] }

const BLANK = { jersey_number: '', first_name: '', last_name: '', position: '', grade_year: '', height: '', weight: '' }

export default function RosterPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const canManage = usePermission('can_manage_roster')

  const [teams, setTeams] = useState<Team[]>([])
  const [teamId, setTeamId] = useState('')
  const [players, setPlayers] = useState<Player[]>([])
  const [form, setForm] = useState({ ...BLANK })
  const [showForm, setShowForm] = useState(false)
  const [csv, setCsv] = useState('')
  const [showCsv, setShowCsv] = useState(false)
  const [cloneTo, setCloneTo] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [view, setView] = useState<'roster' | 'stats'>('roster')
  const [stats, setStats] = useState<StatRow[]>([])
  const [gamesAnalyzed, setGamesAnalyzed] = useState(0)
  // Set when the backend requires the one-time student-data (COPPA) attestation
  // before roster data can be entered. `retry` re-runs the blocked action.
  const [consent, setConsent] = useState<{ attestation: string; retry: () => Promise<void> } | null>(null)
  const [playerToRemove, setPlayerToRemove] = useState<{ id: string; name: string } | null>(null)
  const [removing, setRemoving] = useState(false)

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => {
    if (user) api.get('/teams').then(r => { setTeams(r.data); if (r.data[0]) setTeamId(r.data[0].id) }).catch(() => {})
  }, [user])

  async function loadRoster(id: string) {
    if (!id) return
    try { const r = await api.get(`/rosters/${id}`); setPlayers(r.data.players || []) } catch { setPlayers([]) }
  }
  async function loadStats(id: string) {
    if (!id) return
    try {
      const r = await api.get(`/rosters/${id}/stats`)
      setStats(r.data.players || []); setGamesAnalyzed(r.data.games_analyzed || 0)
    } catch { setStats([]); setGamesAnalyzed(0) }
  }
  useEffect(() => { loadRoster(teamId) }, [teamId])
  useEffect(() => { if (view === 'stats') loadStats(teamId) }, [teamId, view])

  function flash(setter: (s: string) => void, text: string) { setter(text); setTimeout(() => setter(''), 3500) }

  // Route an action error: a student-consent 403 opens the attestation panel (with a
  // retry of the blocked action); anything else flashes the message.
  function onActionError(e: any, fallback: string, retry: () => Promise<void>) {
    const d = e?.response?.data?.detail
    if (e?.response?.status === 403 && d && typeof d === 'object' && d.code === 'student_consent_required') {
      setConsent({ attestation: d.attestation, retry })
      return
    }
    flash(setErr, typeof d === 'string' ? d : fallback)
  }

  async function attestConsent() {
    setErr('')
    try {
      await api.post('/legal/student-consent')
      const retry = consent?.retry
      setConsent(null)
      if (retry) await retry()
    } catch (e: any) { flash(setErr, e?.response?.data?.detail || 'Could not record your confirmation.') }
  }

  async function doAddPlayer() {
    // Omit empty height/weight; send weight as a number (backend expects int).
    const payload = {
      ...form,
      height: form.height.trim() || undefined,
      weight: form.weight.trim() && !isNaN(Number(form.weight)) ? Number(form.weight) : undefined,
    }
    await api.post(`/rosters/${teamId}/players`, payload)
    setForm({ ...BLANK }); setShowForm(false); await loadRoster(teamId)
  }
  async function addPlayer(e: React.FormEvent) {
    e.preventDefault(); setErr('')
    try { await doAddPlayer() } catch (e: any) { onActionError(e, 'Could not add player.', doAddPlayer) }
  }

  async function doUploadCsv() {
    const r = await api.post(`/rosters/${teamId}/upload`, { csv })
    setCsv(''); setShowCsv(false); await loadRoster(teamId)
    flash(setMsg, `Imported: ${r.data.created} added, ${r.data.updated} updated.`)
  }
  async function uploadCsv() {
    setErr('')
    try { await doUploadCsv() } catch (e: any) { onActionError(e, 'CSV import failed.', doUploadCsv) }
  }

  async function removePlayer() {
    if (!playerToRemove) return
    setRemoving(true)
    try {
      await api.delete(`/rosters/${teamId}/players/${playerToRemove.id}`)
      await loadRoster(teamId)
    } catch {}
    finally {
      setRemoving(false)
      setPlayerToRemove(null)
    }
  }

  async function doClone() {
    const r = await api.post(`/rosters/${teamId}/clone-to/${cloneTo}`)
    flash(setMsg, `Cloned ${r.data.cloned} players.`); setCloneTo('')
  }
  async function clone() {
    if (!cloneTo) return
    setErr('')
    try { await doClone() } catch (e: any) { onActionError(e, 'Clone failed.', doClone) }
  }

  const currentTeam = teams.find(t => t.id === teamId)
  const isBball = currentTeam?.sport === 'basketball'  // "Yards" is a football stat

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold">Rosters</h2>
            {canManage && teamId && view === 'roster' && (
              <div className="flex gap-2">
                <button onClick={() => { setShowCsv(s => !s); setShowForm(false) }} className="btn-secondary flex items-center gap-2"><Upload size={16} /> Import CSV</button>
                <button onClick={() => { setShowForm(s => !s); setShowCsv(false) }} className="btn-primary flex items-center gap-2"><Plus size={16} /> Add Player</button>
              </div>
            )}
          </div>

          {teams.length > 0 && (
            <div className="inline-flex rounded-lg border border-gray-800 p-1 mb-6">
              <button onClick={() => setView('roster')} className={`px-3 py-1.5 rounded-md text-sm font-medium flex items-center gap-2 transition-colors ${view === 'roster' ? 'bg-brand-500 text-white' : 'text-gray-400 hover:text-gray-100'}`}><Users size={15} /> Roster</button>
              <button onClick={() => setView('stats')} className={`px-3 py-1.5 rounded-md text-sm font-medium flex items-center gap-2 transition-colors ${view === 'stats' ? 'bg-brand-500 text-white' : 'text-gray-400 hover:text-gray-100'}`}><BarChart3 size={15} /> Season Stats</button>
            </div>
          )}

          {msg && <div className="mb-4 text-sm bg-brand-500/10 border border-brand-500/30 text-brand-300 rounded p-2">{msg}</div>}
          {err && <div className="mb-4 text-sm bg-red-400/10 border border-red-400/30 text-red-400 rounded p-2">{err}</div>}

          {consent && (
            <div className="card mb-6 border border-brand-500/40">
              <h3 className="font-semibold mb-2">Confirm student-data consent</h3>
              <p className="text-sm text-gray-300 mb-4">{consent.attestation}</p>
              <div className="flex gap-2">
                <button onClick={attestConsent} className="btn-primary">I confirm &amp; continue</button>
                <button onClick={() => setConsent(null)} className="btn-secondary">Cancel</button>
              </div>
            </div>
          )}

          {teams.length === 0 ? (
            <div className="card text-center text-gray-400">
              You don&apos;t have any teams yet. <Link href="/teams" className="text-brand-400 hover:underline">Create a team</Link> to build its roster.
            </div>
          ) : (
            <>
              <div className="mb-6">
                <label className="label">Team</label>
                <select className="input" value={teamId} onChange={e => setTeamId(e.target.value)}>
                  {teams.map(t => <option key={t.id} value={t.id}>{t.name}{t.season ? ` · ${t.season}` : ''} ({t.sport})</option>)}
                </select>
              </div>

              {view === 'roster' && (<>
              {showForm && canManage && (
                <form onSubmit={addPlayer} className="card mb-6 space-y-4">
                  <div className="grid grid-cols-5 gap-3">
                    <div><label className="label">#</label><input className="input" value={form.jersey_number} onChange={e => setForm(f => ({ ...f, jersey_number: e.target.value }))} required /></div>
                    <div><label className="label">First</label><input className="input" value={form.first_name} onChange={e => setForm(f => ({ ...f, first_name: e.target.value }))} required /></div>
                    <div><label className="label">Last</label><input className="input" value={form.last_name} onChange={e => setForm(f => ({ ...f, last_name: e.target.value }))} /></div>
                    <div><label className="label">Pos</label><input className="input" value={form.position} onChange={e => setForm(f => ({ ...f, position: e.target.value }))} /></div>
                    <div><label className="label">Grade/Yr</label><input className="input" value={form.grade_year} onChange={e => setForm(f => ({ ...f, grade_year: e.target.value }))} /></div>
                    <div><label className="label">Height</label><input className="input" value={form.height} onChange={e => setForm(f => ({ ...f, height: e.target.value }))} placeholder={`6'2"`} /></div>
                    <div><label className="label">Weight</label><input className="input" type="number" min="0" value={form.weight} onChange={e => setForm(f => ({ ...f, weight: e.target.value }))} placeholder="lbs" /></div>
                  </div>
                  <div className="flex gap-2"><button type="submit" className="btn-primary">Add</button><button type="button" onClick={() => setShowForm(false)} className="btn-secondary">Cancel</button></div>
                </form>
              )}

              {showCsv && canManage && (
                <div className="card mb-6 space-y-3">
                  <label className="label">Paste CSV (columns: jersey_number, first_name, last_name, position, grade_year)</label>
                  <textarea className="input font-mono text-xs" rows={5} value={csv} onChange={e => setCsv(e.target.value)} placeholder={'jersey_number,first_name,last_name,position,grade_year\n23,Jordan,Smith,G,2026'} />
                  <div className="flex gap-2"><button onClick={uploadCsv} className="btn-primary" disabled={!csv.trim()}>Import</button><button onClick={() => setShowCsv(false)} className="btn-secondary">Cancel</button></div>
                </div>
              )}

              <div className="card">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-gray-400 border-b border-gray-800">
                    <th className="py-2 w-12">#</th><th className="py-2">Name</th><th className="py-2">Pos</th><th className="py-2">Grade/Yr</th><th className="py-2">Ht / Wt</th><th></th>
                  </tr></thead>
                  <tbody>
                    {players.map(p => (
                      <tr key={p.id} className="border-b border-gray-800/60">
                        <td className="py-2 font-mono text-gray-300">{p.jersey_number}</td>
                        <td className="py-2">{p.first_name} {p.last_name || ''}</td>
                        <td className="py-2 text-gray-400">{p.position || '—'}</td>
                        <td className="py-2 text-gray-400">{p.grade_year || '—'}</td>
                        <td className="py-2 text-gray-400">{[p.height, p.weight ? `${p.weight} lb` : null].filter(Boolean).join(' / ') || '—'}</td>
                        <td className="py-2 text-right">{canManage && <button onClick={() => setPlayerToRemove({ id: p.id, name: `#${p.jersey_number} ${p.first_name} ${p.last_name || ''}`.trim() })} className="text-gray-500 hover:text-red-400"><Trash2 size={15} /></button>}</td>
                      </tr>
                    ))}
                    {players.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-gray-500">No players yet{canManage ? '. Add one or import a CSV.' : '.'}</td></tr>}
                  </tbody>
                </table>
              </div>

              {canManage && currentTeam && teams.length > 1 && players.length > 0 && (
                <div className="card mt-6 flex items-end gap-3">
                  <div className="flex-1">
                    <label className="label">Clone this roster to another team (new season)</label>
                    <select className="input" value={cloneTo} onChange={e => setCloneTo(e.target.value)}>
                      <option value="">Select a team…</option>
                      {teams.filter(t => t.id !== teamId).map(t => <option key={t.id} value={t.id}>{t.name}{t.season ? ` · ${t.season}` : ''}</option>)}
                    </select>
                  </div>
                  <button onClick={clone} className="btn-secondary flex items-center gap-2" disabled={!cloneTo}><Copy size={16} /> Clone</button>
                </div>
              )}
              </>)}

              {view === 'stats' && (
                <div className="card">
                  <p className="text-xs text-gray-500 mb-3">Season totals across {gamesAnalyzed} analyzed {gamesAnalyzed === 1 ? 'game' : 'games'} for this team. Numbers come from tagged plays; players with no plays yet show zeros.</p>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead><tr className="text-left text-gray-400 border-b border-gray-800">
                        <th className="py-2 w-12">#</th><th className="py-2">Name</th><th className="py-2">Pos</th>
                        <th className="py-2 text-right">Plays</th><th className="py-2 text-right">Primary</th>
                        {!isBball && <th className="py-2 text-right">Yards</th>}<th className="py-2 text-right">Games</th>
                        <th className="py-2">Top plays</th>
                      </tr></thead>
                      <tbody>
                        {stats.map(p => (
                          <tr key={p.id} className="border-b border-gray-800/60">
                            <td className="py-2 font-mono text-gray-300">{p.jersey_number}</td>
                            <td className="py-2">{p.first_name} {p.last_name || ''}</td>
                            <td className="py-2 text-gray-400">{p.position || '—'}</td>
                            <td className="py-2 text-right tabular-nums">{p.stats.plays}</td>
                            <td className="py-2 text-right tabular-nums">{p.stats.primary_plays}</td>
                            {!isBball && <td className="py-2 text-right tabular-nums">{p.stats.total_yards}</td>}
                            <td className="py-2 text-right tabular-nums">{p.stats.games}</td>
                            <td className="py-2 text-gray-400 text-xs">{p.top_play_types.map(t => `${t.play_type} ${t.count}`).join(', ') || '—'}</td>
                          </tr>
                        ))}
                        {stats.length === 0 && <tr><td colSpan={8} className="py-6 text-center text-gray-500">No roster players yet.</td></tr>}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
        <ConfirmModal
          open={!!playerToRemove}
          title="Remove player?"
          message={playerToRemove ? `Remove ${playerToRemove.name} from the roster? This deletes the player record.` : ''}
          confirmLabel="Remove player"
          busy={removing}
          onConfirm={removePlayer}
          onCancel={() => setPlayerToRemove(null)}
        />
      </main>
    </div>
  )
}
