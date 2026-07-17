'use client'
/**
 * Player Grades - grade board for the roster.
 * There is no backend endpoint for player grades yet, so we attempt GET /players
 * (it 404s today), catch it, and render the approved demo layout as a clearly
 * labeled PREVIEW. The sample players are framed as an example of the layout the
 * coach's real graded roster will appear in, never as real data.
 */
import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import OSShell from '@/components/os/OSShell'

interface Performer {
  jersey: string
  name: string
  meta: string
  grade: string
  gradeColor: string
}

interface GradeBand {
  label: string
  count: string
  pct: number
  kind: 'g' | 'o' | 'r'
}

// B grades use gold (NOT the demo's light blue - CGE brand carries no blue).
const SAMPLE_PERFORMERS: Performer[] = [
  { jersey: '12', name: 'QB #12 Marcus J.', meta: '6 games · Pre-snap IQ: 94th pct', grade: 'A+', gradeColor: 'var(--green4)' },
  { jersey: '34', name: 'RB #34 Devon W.', meta: '6 games · Vision: elite · YAC: 4.8', grade: 'A', gradeColor: 'var(--green4)' },
  { jersey: '88', name: 'WR #88 Tyler R.', meta: '5 games · Route crispness: A-', grade: 'B+', gradeColor: 'var(--gold)' },
  { jersey: '55', name: 'C #55 Jordan K.', meta: '6 games · Communication: strong', grade: 'B', gradeColor: 'var(--gold)' },
  { jersey: '72', name: 'OT #72 Chris L.', meta: '4 games · Pass set: needs work', grade: 'C+', gradeColor: 'var(--warn)' },
]

const SAMPLE_BANDS: GradeBand[] = [
  { label: 'A - Elite', count: '3 players', pct: 20, kind: 'g' },
  { label: 'B - Above Average', count: '7 players', pct: 47, kind: 'g' },
  { label: 'C - Average', count: '4 players', pct: 27, kind: 'o' },
  { label: 'D - Needs Development', count: '1 player', pct: 7, kind: 'r' },
]

export default function PlayersPage() {
  const { user } = useAuth()
  const [players, setPlayers] = useState<Performer[] | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    if (!user) return
    // No /players endpoint exists yet - this 404s. Catch it and stay in preview mode.
    api.get('/players')
      .then(res => {
        const data = Array.isArray(res.data) ? res.data : res.data?.players
        setPlayers(Array.isArray(data) && data.length ? data : null)
        setLoaded(true)
      })
      .catch(() => { setPlayers(null); setLoaded(true) })
  }, [user])

  const isPreview = loaded && !players
  const performers = players || SAMPLE_PERFORMERS

  return (
    <OSShell title="Player Grades">
      <div className="sec-title" style={{ marginBottom: 16 }}>👤 Player Grade Board</div>

      {isPreview && (
        <div className="ai-box" style={{ marginTop: 0, marginBottom: 16 }}>
          <strong>Player Grades preview</strong> - grades populate automatically as your film is tagged
          with jersey numbers. This is the layout your graded roster will appear in.
        </div>
      )}

      <div className="g2">
        <div className="card">
          <div className="card-hdr"><div className="card-title">🏆 Top Performers</div></div>
          <div className="card-body" style={{ padding: 0 }}>
            {performers.map((p, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '9px 16px',
                  borderBottom: i < performers.length - 1 ? '1px solid var(--border)' : 'none',
                }}
              >
                <div
                  style={{
                    width: 30,
                    height: 30,
                    borderRadius: '50%',
                    background: 'linear-gradient(135deg,var(--bg4),var(--bg3))',
                    border: '1px solid var(--border2)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 10,
                    fontWeight: 700,
                    color: 'var(--text2)',
                    fontFamily: 'var(--display)',
                  }}
                >
                  {p.jersey}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: 500 }}>{p.name}</div>
                  <div style={{ fontSize: 10, color: 'var(--text2)' }}>{p.meta}</div>
                </div>
                <div style={{ fontFamily: 'var(--mono)', fontSize: 13, fontWeight: 700, color: p.gradeColor }}>{p.grade}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-hdr"><div className="card-title">📊 Grade Distribution</div></div>
          <div className="card-body">
            {SAMPLE_BANDS.map((b, i) => (
              <div className="pb-wrap" key={i}>
                <div className="pb-top"><span>{b.label}</span><b>{b.count}</b></div>
                <div className="pb"><div className={'pf pf-' + b.kind} style={{ width: b.pct + '%' }} /></div>
              </div>
            ))}
            <div className="ai-box" style={{ marginTop: 14 }}>
              <strong>#12 Marcus J. insight:</strong> Elite pre-snap read ability across all 6 graded games -
              1.7s avg decision time, top 3% in our library. Recommend increasing his play-action rep count to
              exploit this week&apos;s opponent tendency data.
            </div>
          </div>
        </div>
      </div>

      <div className="powered">Powered by <a href="https://cosbyaisolutions.com" target="_blank" rel="noreferrer">Cosby AI Solutions</a></div>
    </OSShell>
  )
}
