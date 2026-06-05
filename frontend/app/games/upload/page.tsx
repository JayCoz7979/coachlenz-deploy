'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'
import axios from 'axios'

const SPORTS = ['football','flag_football','basketball','baseball','softball','volleyball','soccer']

export default function UploadPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [teams, setTeams] = useState<any[]>([])
  const [form, setForm] = useState({ title: '', sport: 'football', team_id: '', opponent: '', game_date: '', is_home: '' })
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState('')

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => { if (user) api.get('/teams').then(r => setTeams(r.data)) }, [user])

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault()
    if (!file) return
    setUploading(true)
    setError('')
    try {
      const gameRes = await api.post('/games', {
        ...form,
        file_name: file.name,
        file_size_bytes: file.size,
        team_id: form.team_id || undefined,
        is_home: form.is_home === '' ? undefined : form.is_home === 'true',
      })
      await axios.put(gameRes.data.upload_url, file, {
        headers: { 'Content-Type': file.type || 'video/mp4' },
        onUploadProgress: (e) => setProgress(Math.round((e.loaded / (e.total || 1)) * 100)),
      })
      await api.post(`/upload/complete?game_id=${gameRes.data.id}`)
      router.push('/games')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-2xl mx-auto">
          <div className="flex items-center gap-3 mb-6">
            <button onClick={() => router.back()} className="text-gray-400 hover:text-gray-200 text-sm">← Back</button>
            <h2 className="text-2xl font-bold">Upload Game Film</h2>
          </div>
          <form onSubmit={handleUpload} className="card space-y-4">
            {error && <div className="text-red-400 text-sm bg-red-400/10 rounded p-3">{error}</div>}
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2"><label className="label">Game Title</label><input className="input" value={form.title} onChange={set('title')} required placeholder="vs Lincoln High - Week 5" /></div>
              <div><label className="label">Sport</label>
                <select className="input" value={form.sport} onChange={set('sport')}>
                  {SPORTS.map(s => <option key={s} value={s}>{s.replace(/_/g,' ')}</option>)}
                </select>
              </div>
              <div><label className="label">Team</label>
                <select className="input" value={form.team_id} onChange={set('team_id')}>
                  <option value="">Select team...</option>
                  {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
              <div><label className="label">Opponent</label><input className="input" value={form.opponent} onChange={set('opponent')} placeholder="Lincoln High" /></div>
              <div><label className="label">Game Date</label><input type="date" className="input" value={form.game_date} onChange={set('game_date')} /></div>
            </div>
            <div>
              <label className="label">Game Film (Video)</label>
              <input type="file" accept="video/*" className="input" onChange={e => setFile(e.target.files?.[0] || null)} required />
              <p className="text-xs text-gray-500 mt-1">Max 20GB. MP4, MOV, AVI supported.</p>
            </div>
            {uploading && (
              <div>
                <div className="flex justify-between text-sm mb-1"><span>Uploading...</span><span>{progress}%</span></div>
                <div className="w-full bg-gray-700 rounded-full h-2"><div className="bg-brand-500 h-2 rounded-full transition-all" style={{ width: `${progress}%` }} /></div>
              </div>
            )}
            <button type="submit" disabled={uploading || !file} className="btn-primary w-full">{uploading ? `Uploading ${progress}%...` : 'Upload Film'}</button>
          </form>
        </div>
      </main>
    </div>
  )
}
