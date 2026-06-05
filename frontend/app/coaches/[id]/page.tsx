'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter, useParams } from 'next/navigation'
import { UserCircle, Plus } from 'lucide-react'

export default function CoachDetailPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const params = useParams()
  const [coach, setCoach] = useState<any>(null)
  const [showMove, setShowMove] = useState(false)
  const [move, setMove] = useState({ school_name: '', role: '', sport: '', start_date: '', end_date: '', is_current: false, wins: '', losses: '' })

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => {
    if (user && params.id) api.get(`/coaches/${params.id}`).then(r => setCoach(r.data)).catch(() => router.push('/coaches'))
  }, [user, params.id])

  async function addMove(e: React.FormEvent) {
    e.preventDefault()
    await api.post(`/coaches/${params.id}/moves`, { ...move, wins: move.wins ? Number(move.wins) : undefined, losses: move.losses ? Number(move.losses) : undefined })
    const r = await api.get(`/coaches/${params.id}`)
    setCoach(r.data)
    setShowMove(false)
  }

  if (!coach) return <div className="flex h-screen overflow-hidden"><Sidebar /><div className="flex-1 flex items-center justify-center text-gray-400">Loading...</div></div>

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-3xl mx-auto">
          <button onClick={() => router.back()} className="text-gray-400 hover:text-gray-200 text-sm mb-4">← Back</button>
          <div className="card mb-6 flex items-center gap-4">
            <UserCircle size={48} className="text-brand-400" />
            <div>
              <h2 className="text-2xl font-bold">{coach.name}</h2>
              <div className="text-gray-400">{coach.sport} {coach.position && `· ${coach.position}`}</div>
            </div>
          </div>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">Career History</h3>
            <button onClick={() => setShowMove(true)} className="btn-primary flex items-center gap-2 text-sm"><Plus size={14} /> Add Move</button>
          </div>
          {showMove && (
            <form onSubmit={addMove} className="card mb-4 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2"><label className="label">School / Organization</label><input className="input" value={move.school_name} onChange={e => setMove(m => ({ ...m, school_name: e.target.value }))} required /></div>
                <div><label className="label">Role/Title</label><input className="input" value={move.role} onChange={e => setMove(m => ({ ...m, role: e.target.value }))} /></div>
                <div><label className="label">Sport</label><input className="input" value={move.sport} onChange={e => setMove(m => ({ ...m, sport: e.target.value }))} /></div>
                <div><label className="label">Start Date</label><input type="date" className="input" value={move.start_date} onChange={e => setMove(m => ({ ...m, start_date: e.target.value }))} /></div>
                <div><label className="label">End Date</label><input type="date" className="input" value={move.end_date} onChange={e => setMove(m => ({ ...m, end_date: e.target.value }))} /></div>
                <div><label className="label">Wins</label><input type="number" className="input" value={move.wins} onChange={e => setMove(m => ({ ...m, wins: e.target.value }))} /></div>
                <div><label className="label">Losses</label><input type="number" className="input" value={move.losses} onChange={e => setMove(m => ({ ...m, losses: e.target.value }))} /></div>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={move.is_current} onChange={e => setMove(m => ({ ...m, is_current: e.target.checked }))} />
                Current position
              </label>
              <div className="flex gap-2">
                <button type="submit" className="btn-primary">Add</button>
                <button type="button" onClick={() => setShowMove(false)} className="btn-secondary">Cancel</button>
              </div>
            </form>
          )}
          <div className="space-y-3">
            {coach.moves?.map((m: any) => (
              <div key={m.id} className="card">
                <div className="flex justify-between items-start">
                  <div>
                    <div className="font-semibold">{m.school_name} {m.is_current && <span className="text-xs text-brand-400 ml-2">CURRENT</span>}</div>
                    <div className="text-sm text-gray-400">{m.role} {m.sport && `· ${m.sport}`}</div>
                    <div className="text-sm text-gray-500">{m.start_date} {m.end_date && `→ ${m.end_date}`}</div>
                  </div>
                  {(m.wins !== null || m.losses !== null) && (
                    <div className="text-sm text-gray-300">{m.wins ?? '-'} W / {m.losses ?? '-'} L</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
