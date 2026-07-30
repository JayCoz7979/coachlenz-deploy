'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth, usePermission } from '@/lib/auth'
import api from '@/lib/api'
import { Plus, Trash2, Upload, Copy } from 'lucide-react'

interface Team { id: string; name: string; sport: string; season: string | null }
interface Player {
  id: string; jersey_number: string; first_name: string; last_name: string | null
  position: string | null; grade_year: string | null
}

const BLANK = { jersey_number: '', first_name: '', last_name: '', position: '', grade_year: '' }

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

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => {
    if (user) api.get('/teams').then(r => { setTeams(r.data); if (r.data[0]) setTeamId(r.data[0].id) }).catch(() => {})
  }, [user])

  async function loadRoster(id: string) {
    if (!id) return
    try { const r = await api.get(`/rosters/${id}`); setPlayers(r.data.players || []) } catch { setPlayers([]) }
  }
  useEffect(() => { loadRoster(teamId) }, [teamId])

  function flash(setter: (s: string) => void, text: string) { setter(text); setTimeout(() => setter(''), 3500) }

  async function addPlayer(e: React.FormEvent) {
    e.preventDefault(); setErr('')
    try {
      await api.post(`/rosters/${teamId}/players`, form)
      setForm({ ...BLANK }); setShowForm(false); await loadRoster(teamId)
    } catch (e: any) { flash(setErr, e.response?.data?.detail || 'Could not add player.') }
  }

  async function uploadCsv() {
    setErr('')
    try {
      const r = await api.post(`/rosters/${teamId}/upload`, { csv })
      setCsv(''); setShowCsv(false); await loadRoster(teamId)
      flash(setMsg, `Imported: ${r.data.created} added, ${r.data.updated} updated.`)
    } catch (e: any) { flash(setErr, e.response?.data?.detail || 'CSV import failed.') }
  }

  async function removePlayer(pid: string) {
    if (!confirm('Remove this player from the roster?')) return
    try { await api.delete(`/rosters/${teamId}/players/${pid}`); await loadRoster(teamId) } catch {}
  }

  async function clone() {
    if (!cloneTo) return
    try {
      const r = await api.post(`/rosters/${teamId}/clone-to/${cloneTo}`)
      flash(setMsg, `Cloned ${r.data.cloned} players.`); setCloneTo('')
    } catch (e: any) { flash(setErr, e.response?.data?.detail || 'Clone failed.') }
  }

  const currentTeam = teams.find(t => t.id === teamId)

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold">Rosters</h2>
            {canManage && teamId && (
              <div className="flex gap-2">
                <button onClick={() => { setShowCsv(s => !s); setShowForm(false) }} className="btn-secondary flex items-center gap-2"><Upload size={16} /> Import CSV</button>
                <button onClick={() => { setShowForm(s => !s); setShowCsv(false) }} className="btn-primary flex items-center gap-2"><Plus size={16} /> Add Player</button>
              </div>
            )}
          </div>

          {msg && <div className="mb-4 text-sm bg-brand-500/10 border border-brand-500/30 text-brand-300 rounded p-2">{msg}</div>}
          {err && <div className="mb-4 text-sm bg-red-400/10 border border-red-400/30 text-red-400 rounded p-2">{err}</div>}

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

              {showForm && canManage && (
                <form onSubmit={addPlayer} className="card mb-6 space-y-4">
                  <div className="grid grid-cols-5 gap-3">
                    <div><label className="label">#</label><input className="input" value={form.jersey_number} onChange={e => setForm(f => ({ ...f, jersey_number: e.target.value }))} required /></div>
                    <div><label className="label">First</label><input className="input" value={form.first_name} onChange={e => setForm(f => ({ ...f, first_name: e.target.value }))} required /></div>
                    <div><label className="label">Last</label><input className="input" value={form.last_name} onChange={e => setForm(f => ({ ...f, last_name: e.target.value }))} /></div>
                    <div><label className="label">Pos</label><input className="input" value={form.position} onChange={e => setForm(f => ({ ...f, position: e.target.value }))} /></div>
                    <div><label className="label">Grade/Yr</label><input className="input" value={form.grade_year} onChange={e => setForm(f => ({ ...f, grade_year: e.target.value }))} /></div>
                  </div>
                  <div className="flex gap-2"><button type="submit" className="btn-primary">Add</button><button type="button" onClick={() => setShowForm(false)} className="btn-secondary">Cancel</button></div>
                </form>
              )}

              {showCsv && canManage && (
                <div className="card mb-6 space-y-3">
                  <label className="label">Paste CSV (columns: jersey_number, first_name, last_name, position, grade_year)</label>
                  <textarea className="input font-mono text-xs" rows={5} value={csv} onChange={e => setCsv(e.target.value)} placeholder={'jersey_number,first_name,last_name,position,grade_year\n7,Cam,Newton,QB,2026'} />
                  <div className="flex gap-2"><button onClick={uploadCsv} className="btn-primary" disabled={!csv.trim()}>Import</button><button onClick={() => setShowCsv(false)} className="btn-secondary">Cancel</button></div>
                </div>
              )}

              <div className="card">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-gray-400 border-b border-gray-800">
                    <th className="py-2 w-12">#</th><th className="py-2">Name</th><th className="py-2">Pos</th><th className="py-2">Grade/Yr</th><th></th>
                  </tr></thead>
                  <tbody>
                    {players.map(p => (
                      <tr key={p.id} className="border-b border-gray-800/60">
                        <td className="py-2 font-mono text-gray-300">{p.jersey_number}</td>
                        <td className="py-2">{p.first_name} {p.last_name || ''}</td>
                        <td className="py-2 text-gray-400">{p.position || '—'}</td>
                        <td className="py-2 text-gray-400">{p.grade_year || '—'}</td>
                        <td className="py-2 text-right">{canManage && <button onClick={() => removePlayer(p.id)} className="text-gray-500 hover:text-red-400"><Trash2 size={15} /></button>}</td>
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
            </>
          )}
        </div>
      </main>
    </div>
  )
}
