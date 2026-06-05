'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { UserCircle, Plus } from 'lucide-react'

export default function CoachesPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [coaches, setCoaches] = useState<any[]>([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', sport: '', position: '' })

  useEffect(() => { fetchMe() }, [])
  useEffect(() => {
    if (!isLoading && !user) { router.push('/login'); return }
    if (!isLoading && user && !user.organization.has_coach_tenure_access) router.push('/dashboard')
  }, [isLoading, user])
  useEffect(() => { if (user?.organization.has_coach_tenure_access) api.get('/coaches').then(r => setCoaches(r.data)).catch(() => {}) }, [user])

  async function createCoach(e: React.FormEvent) {
    e.preventDefault()
    await api.post('/coaches', form)
    const r = await api.get('/coaches')
    setCoaches(r.data)
    setShowForm(false)
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold">Coach Tenure</h2>
            <button onClick={() => setShowForm(true)} className="btn-primary flex items-center gap-2"><Plus size={16} /> Add Coach</button>
          </div>
          {showForm && (
            <form onSubmit={createCoach} className="card mb-6 space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div><label className="label">Name</label><input className="input" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required /></div>
                <div><label className="label">Sport</label><input className="input" value={form.sport} onChange={e => setForm(f => ({ ...f, sport: e.target.value }))} /></div>
                <div><label className="label">Position/Role</label><input className="input" value={form.position} onChange={e => setForm(f => ({ ...f, position: e.target.value }))} /></div>
              </div>
              <div className="flex gap-2">
                <button type="submit" className="btn-primary">Add Coach</button>
                <button type="button" onClick={() => setShowForm(false)} className="btn-secondary">Cancel</button>
              </div>
            </form>
          )}
          <div className="space-y-3">
            {coaches.map(c => (
              <Link key={c.id} href={`/coaches/${c.id}`} className="card block hover:border-brand-500/50 transition-colors">
                <div className="flex items-center gap-3">
                  <UserCircle size={32} className="text-brand-400" />
                  <div>
                    <div className="font-semibold">{c.name}</div>
                    <div className="text-sm text-gray-400">{c.sport} {c.position && `· ${c.position}`}</div>
                  </div>
                </div>
              </Link>
            ))}
            {coaches.length === 0 && <div className="text-center text-gray-500 py-12">No coaches added yet.</div>}
          </div>
        </div>
      </main>
    </div>
  )
}
