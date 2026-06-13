'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Film, Plus, CheckCircle, Clock, AlertCircle, Link2, Upload } from 'lucide-react'

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
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-bold">Film Library</h2>
            <div className="flex gap-2">
              <button onClick={() => router.push('/games/upload?tab=url')} className="btn-secondary flex items-center gap-2"><Link2 size={15} /> Import URL</button>
              <button onClick={() => router.push('/games/upload')} className="btn-primary flex items-center gap-2"><Upload size={15} /> Upload File</button>
            </div>
          </div>

          {/* URL import callout — always visible */}
          <div
            style={{
              background: 'rgba(201,168,76,0.07)',
              border: '1px solid rgba(201,168,76,0.25)',
              borderRadius: 8,
              padding: '14px 18px',
              marginBottom: 20,
              display: 'flex',
              alignItems: 'center',
              gap: 14,
              flexWrap: 'wrap',
            }}
          >
            <Link2 size={20} style={{ color: '#C9A84C', flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 13, color: '#f8f6f0', marginBottom: 2 }}>
                Import film from YouTube, Hudl, Vimeo, Google Drive, or Dropbox
              </div>
              <div style={{ fontSize: 11, color: '#7a7a6e' }}>
                Paste any video link — our system downloads and processes it automatically.
              </div>
            </div>
            <button
              onClick={() => router.push('/games/upload?tab=url')}
              style={{
                background: '#C9A84C', color: '#1c1c1c', border: 'none',
                borderRadius: 4, padding: '8px 18px', fontSize: 12,
                fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap',
                letterSpacing: '0.06em',
              }}
            >
              PASTE A LINK
            </button>
          </div>
          <div className="space-y-3">
            {games.map(g => (
              <Link key={g.id} href={`/games/${g.id}`} style={{ textDecoration: 'none', display: 'block' }}>
                <div className="card flex items-center justify-between" style={{ cursor: 'pointer', transition: 'border-color 0.15s' }}
                  onMouseEnter={e => (e.currentTarget as HTMLElement).style.borderColor = 'rgba(201,168,76,0.25)'}
                  onMouseLeave={e => (e.currentTarget as HTMLElement).style.borderColor = 'rgba(255,255,255,0.06)'}
                >
                  <div>
                    <div className="font-semibold flex items-center gap-2"><Film size={16} className="text-brand-400" />{g.title}</div>
                    <div className="text-sm text-gray-400 mt-1 flex items-center gap-2">
                      {statusIcon(g.status)} {g.status} · {g.sport?.replace(/_/g,' ')} {g.opponent && `vs ${g.opponent}`}
                      {g.is_trial_game && <span className="text-yellow-400 text-xs">TRIAL</span>}
                    </div>
                  </div>
                  <div className="text-xs text-gray-500">{g.game_date || new Date(g.created_at).toLocaleDateString()}</div>
                </div>
              </Link>
            ))}
            {games.length === 0 && <div className="text-center text-gray-500 py-12">No games yet. Upload your first game film.</div>}
          </div>
        </div>
      </main>
    </div>
  )
}
