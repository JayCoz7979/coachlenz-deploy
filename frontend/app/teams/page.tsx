'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'
import { Users, Plus, Trash2 } from 'lucide-react'

const SPORTS = ['football','flag_football','basketball','baseball','softball','volleyball','soccer']

export default function TeamsPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [teams, setTeams] = useState<any[]>([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', sport: 'football', level: '', season: '' })

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => { if (user) api.get('/teams').then(r => setTeams(r.data)) }, [user])

  async function createTeam(e: React.FormEvent) {
    e.preventDefault()
    await api.post('/teams', form)
    const r = await api.get('/teams')
    setTeams(r.data)
    setShowForm(false)
    setForm({ name: '', sport: 'football', level: '', season: '' })
  }

  async function deleteTeam(id: string) {
    await api.delete(`/teams/${id}`)
    setTeams(t => t.filter(x => x.id !== id))
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold">Teams</h2>
            <button onClick={() => setShowForm(true)} className="btn-primary flex items-center gap-2"><Plus size={16} /> New Team</button>
          </div>
          {showForm && (
            <form onSubmit={createTeam} className="card mb-6 space-y-4">
              <h3 className="font-semibold">Create Team</h3>
              <div className="grid grid-cols-2 gap-4">
                <div><label className="label">Team Name</label><input className="input" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required /></div>
                <div><label className="label">Sport</label>
                  <select className="input" value={form.sport} onChange={e => setForm(f => ({ ...f, sport: e.target.value }))}>
                    {SPORTS.map(s => <option key={s} value={s}>{s.replace(/_/g,' ')}</option>)}
                  </select>
                </div>
                <div><label className="label">Level</label><input className="input" placeholder="Varsity, JV..." value={form.level} onChange={e => setForm(f => ({ ...f, level: e.target.value }))} /></div>
                <div><label className="label">Season</label><input className="input" placeholder="2024-25" value={form.season} onChange={e => setForm(f => ({ ...f, season: e.target.value }))} /></div>
              </div>
              <div className="flex gap-2">
                <button type="submit" className="btn-primary">Create</button>
                <button type="button" onClick={() => setShowForm(false)} className="btn-secondary">Cancel</button>
              </div>
            </form>
          )}
          <div className="space-y-3">
            {teams.map(t => (
              <div key={t.id} className="card flex items-center justify-between">
                <div>
                  <div className="font-semibold flex items-center gap-2"><Users size={16} className="text-brand-400" />{t.name}</div>
                  <div className="text-sm text-gray-400 mt-1">{t.sport?.replace(/_/g,' ')} {t.level && `· ${t.level}`} {t.season && `· ${t.season}`}</div>
                </div>
                <button onClick={() => deleteTeam(t.id)} className="text-gray-500 hover:text-red-400 transition-colors"><Trash2 size={16} /></button>
              </div>
            ))}
            {teams.length === 0 && <div className="text-center text-gray-500 py-12">No teams yet. Create your first team to get started.</div>}
          </div>
        </div>
      </main>
    </div>
  )
}
