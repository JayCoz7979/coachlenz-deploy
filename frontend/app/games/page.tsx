'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Film, Plus, CheckCircle, Clock, AlertCircle } from 'lucide-react'

const statusIcon = (s: string) => {
  if (s === 'ready') return <CheckCircle size={14} className="text-green-400" />
  if (s === 'processing') return <Clock size={14} className="text-yellow-400" />
  if (s === 'error') return <AlertCircle size={14} className="text-red-400" />
  return <Clock size={14} className="text-gray-400" />
}

export default function GamesPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [games, setGames] = useState<any[]>([])

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => { if (user) api.get('/games').then(r => setGames(r.data)) }, [user])

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold">Games</h2>
            <div className="flex gap-2">
              <button onClick={() => router.push('/games/upload?tab=url')} className="btn-secondary flex items-center gap-2"><Plus size={16} /> Import URL</button>
              <button onClick={() => router.push('/games/upload')} className="btn-primary flex items-center gap-2"><Plus size={16} /> Upload Film</button>
            </div>
          </div>
          <div className="space-y-3">
            {games.map(g => (
              <div key={g.id} className="card flex items-center justify-between">
                <div>
                  <div className="font-semibold flex items-center gap-2"><Film size={16} className="text-brand-400" />{g.title}</div>
                  <div className="text-sm text-gray-400 mt-1 flex items-center gap-2">
                    {statusIcon(g.status)} {g.status} · {g.sport?.replace(/_/g,' ')} {g.opponent && `vs ${g.opponent}`}
                    {g.is_trial_game && <span className="text-yellow-400 text-xs">TRIAL</span>}
                  </div>
                </div>
                <div className="text-xs text-gray-500">{g.game_date || new Date(g.created_at).toLocaleDateString()}</div>
              </div>
            ))}
            {games.length === 0 && <div className="text-center text-gray-500 py-12">No games yet. Upload your first game film.</div>}
          </div>
        </div>
      </main>
    </div>
  )
}
