'use client'
import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import OSShell from '@/components/os/OSShell'

const statusTag = (s: string) => {
  if (s === 'ready') return <span className="tag tg">Ready</span>
  if (s === 'manual') return <span className="tag tgo">Scout</span>
  if (s === 'error' || (s || '').startsWith('error')) return <span className="tag tr">Error</span>
  return <span className="tag tq">{s}</span>
}

export default function GamesPage() {
  const { user } = useAuth()
  const router = useRouter()
  const [games, setGames] = useState<any[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    if (!user) return
    api.get('/games').then(r => setGames(r.data || [])).catch(() => {}).finally(() => setLoaded(true))
  }, [user])

  return (
    <OSShell title="Film Room">
      <div className="sec-hdr">
        <div className="sec-title">🎬 Film Room</div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="sec-btn" onClick={() => router.push('/games/upload?tab=url')}>🔗 Import URL</button>
          <button className="sec-btn sec-btn-g" onClick={() => router.push('/games/upload')}>⬆️ Upload File</button>
        </div>
      </div>

      {/* Import callout */}
      <div className="ai-box" style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', marginTop: 0, marginBottom: 16 }}>
        <div style={{ flex: 1 }}>
          <strong>Import film from YouTube, Hudl, Vimeo, Google Drive, or Dropbox.</strong>{' '}
          Paste any video link and CoachLenz downloads, tags, and analyzes it automatically.
        </div>
        <button className="sec-btn sec-btn-g" onClick={() => router.push('/games/upload?tab=url')} style={{ whiteSpace: 'nowrap' }}>Paste a link →</button>
      </div>

      <div className="rpt-list">
        {games.map(g => (
          <Link key={g.id} href={`/games/${g.id}`} style={{ textDecoration: 'none' }}>
            <div className="rpt-row">
              <div className="rpt-icon">🎬</div>
              <div className="rpt-info">
                <div className="rpt-name">{g.title || g.opponent}</div>
                <div className="rpt-meta" style={{ textTransform: 'capitalize' }}>
                  {(g.sport || '').replace(/_/g, ' ')}{g.opponent ? ` · vs ${g.opponent}` : ''}
                  {g.is_trial_game ? ' · Trial' : ''}
                </div>
              </div>
              <span className="rpt-meta mono">{g.game_date ? new Date(g.game_date).toLocaleDateString() : (g.created_at ? new Date(g.created_at).toLocaleDateString() : '')}</span>
              {statusTag(g.status)}
            </div>
          </Link>
        ))}
        {loaded && games.length === 0 && (
          <div className="ai-box" style={{ textAlign: 'center' }}>
            No film yet.{' '}
            <Link href="/games/upload?tab=url" style={{ color: 'var(--green3)' }}>Import your first game →</Link>
          </div>
        )}
      </div>
      <div className="powered">Powered by <a href="https://cosbyaisolutions.com" target="_blank" rel="noreferrer">Cosby AI Solutions</a></div>
    </OSShell>
  )
}
