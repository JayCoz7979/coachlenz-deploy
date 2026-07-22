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
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!user) return
    api.get('/games').then(r => setGames(r.data || [])).catch(() => {}).finally(() => setLoaded(true))
  }, [user])

  async function doDelete(id: string) {
    setDeletingId(id)
    setErr('')
    try {
      await api.delete(`/games/${id}`)
      setGames(gs => gs.filter(x => x.id !== id))
      setConfirmId(null)
    } catch {
      setErr('Could not delete that film. Please try again.')
    } finally {
      setDeletingId(null)
    }
  }

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

      {err && <div className="ai-box" style={{ marginTop: 0, marginBottom: 12, color: 'var(--red, #d66)' }}>{err}</div>}

      <div className="rpt-list">
        {games.map(g => {
          const isConfirming = confirmId === g.id
          const isDeleting = deletingId === g.id
          return (
            <div
              key={g.id}
              className="rpt-row"
              style={{ cursor: isConfirming ? 'default' : 'pointer', opacity: isDeleting ? 0.5 : 1 }}
              onClick={() => { if (!isConfirming && !isDeleting) router.push(`/games/${g.id}`) }}
            >
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

              {isConfirming ? (
                <div onClick={e => e.stopPropagation()} style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                  <span className="rpt-meta" style={{ whiteSpace: 'nowrap' }}>Delete permanently?</span>
                  <button
                    className="sec-btn"
                    disabled={isDeleting}
                    onClick={() => doDelete(g.id)}
                    style={{ color: '#e56', borderColor: '#e56', whiteSpace: 'nowrap' }}
                  >
                    {isDeleting ? 'Deleting…' : 'Delete'}
                  </button>
                  <button className="sec-btn" disabled={isDeleting} onClick={() => setConfirmId(null)}>Cancel</button>
                </div>
              ) : (
                <button
                  title="Delete film"
                  aria-label="Delete film"
                  onClick={e => { e.stopPropagation(); setErr(''); setConfirmId(g.id) }}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#7a7a6e', padding: 6, flexShrink: 0, fontSize: 16, lineHeight: 1 }}
                >
                  🗑
                </button>
              )}
            </div>
          )
        })}
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
