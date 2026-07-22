'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'
import { Trophy, Plus } from 'lucide-react'

import { SPORTS } from '@/lib/sports'

export default function TeamsOfMonthPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [submissions, setSubmissions] = useState<any[]>([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ submitter_name: '', submitter_email: '', team_name: '', sport: 'football', school_or_org: '', level: '', achievement: '', season: '' })
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => { if (user) api.get('/teams-of-month').then(r => setSubmissions(r.data)).catch(() => {}) }, [user])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    try {
      await api.post('/teams-of-month/submit', form)
      setSuccess(true)
      setShowForm(false)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Submission failed')
    }
  }

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold flex items-center gap-3"><Trophy className="text-yellow-400" /> Teams of the Month</h2>
            <button onClick={() => setShowForm(true)} className="btn-primary flex items-center gap-2"><Plus size={16} /> Nominate Team</button>
          </div>
          {success && <div className="mb-6 p-4 bg-green-500/10 border border-green-500/30 rounded-lg text-green-400">Your nomination was submitted!</div>}
          {showForm && (
            <form onSubmit={submit} className="card mb-6 space-y-4">
              <h3 className="font-semibold">Nominate a Team</h3>
              {error && <div className="text-red-400 text-sm bg-red-400/10 rounded p-3">{error}</div>}
              <div className="grid grid-cols-2 gap-4">
                <div><label className="label">Your Name</label><input className="input" value={form.submitter_name} onChange={set('submitter_name')} required /></div>
                <div><label className="label">Your Email</label><input type="email" className="input" value={form.submitter_email} onChange={set('submitter_email')} required /></div>
                <div><label className="label">Team Name</label><input className="input" value={form.team_name} onChange={set('team_name')} required /></div>
                <div><label className="label">Sport</label>
                  <select className="input" value={form.sport} onChange={set('sport')}>
                    {SPORTS.map(s => <option key={s} value={s}>{s.replace(/_/g,' ')}</option>)}
                  </select>
                </div>
                <div><label className="label">School / Organization</label><input className="input" value={form.school_or_org} onChange={set('school_or_org')} required /></div>
                <div><label className="label">Level</label><input className="input" placeholder="Varsity, JV..." value={form.level} onChange={set('level')} /></div>
                <div className="col-span-2"><label className="label">Achievement</label><textarea className="input h-24 resize-none" value={form.achievement} onChange={set('achievement')} required placeholder="Describe what makes this team remarkable..." /></div>
              </div>
              <div className="flex gap-2">
                <button type="submit" className="btn-primary">Submit Nomination</button>
                <button type="button" onClick={() => setShowForm(false)} className="btn-secondary">Cancel</button>
              </div>
            </form>
          )}
          <div className="space-y-3">
            {submissions.map(s => (
              <div key={s.id} className="card">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-semibold">{s.team_name}</div>
                    <div className="text-sm text-gray-400 mt-1">{s.sport?.replace(/_/g,' ')} · {s.school_or_org} · {s.month_year}</div>
                    <div className="text-sm text-gray-300 mt-2">{s.achievement}</div>
                  </div>
                  <div className={`text-xs px-2 py-1 rounded ${s.status === 'featured' ? 'bg-yellow-400/20 text-yellow-400' : s.status === 'approved' ? 'bg-green-400/20 text-green-400' : 'bg-gray-700 text-gray-400'}`}>{s.status}</div>
                </div>
              </div>
            ))}
            {submissions.length === 0 && !showForm && <div className="text-center text-gray-500 py-12">No nominations yet this month. Be the first to nominate!</div>}
          </div>
        </div>
      </main>
    </div>
  )
}
