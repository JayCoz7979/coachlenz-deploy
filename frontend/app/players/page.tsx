'use client'
/**
 * Player Grades - grade board for the roster.
 *
 * There is no /players backend endpoint yet, so this attempts GET /players and,
 * when it returns nothing (today: a 404), shows an HONEST empty state that
 * explains how grades are produced. It never renders sample/placeholder players
 * or a fabricated insight as if they were the coach's real data. When a real
 * endpoint exists, the grade distribution is derived from the actual grades.
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
  gradeColor?: string
}

// B grades use gold (CGE brand carries no blue). Derived from the letter grade.
const GRADE_COLOR: Record<string, string> = {
  A: 'var(--green4)', B: 'var(--gold)', C: 'var(--warn)', D: 'var(--warn)', F: 'var(--warn)',
}
function gradeColor(g: string) {
  return GRADE_COLOR[(g || '').trim().charAt(0).toUpperCase()] || 'var(--text2)'
}

// Grade distribution computed from REAL performer grades (never hardcoded counts).
function bands(performers: Performer[]) {
  const labels: Record<string, string> = {
    A: 'A - Elite', B: 'B - Above Average', C: 'C - Average', D: 'D - Needs Development',
  }
  const kinds: Record<string, 'g' | 'o' | 'r'> = { A: 'g', B: 'g', C: 'o', D: 'r' }
  const counts: Record<string, number> = { A: 0, B: 0, C: 0, D: 0 }
  for (const p of performers) {
    let letter = (p.grade || '').trim().charAt(0).toUpperCase()
    if (letter === 'F') letter = 'D'
    if (letter in counts) counts[letter]++
  }
  const total = performers.length || 1
  return (['A', 'B', 'C', 'D'] as const).map(k => ({
    label: labels[k], kind: kinds[k],
    count: `${counts[k]} player${counts[k] === 1 ? '' : 's'}`,
    pct: Math.round((counts[k] / total) * 100),
  }))
}

export default function PlayersPage() {
  const { user } = useAuth()
  const [players, setPlayers] = useState<Performer[] | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    if (!user) return
    // No /players endpoint exists yet - this 404s. Catch it and show the honest
    // empty state (never sample data).
    api.get('/players')
      .then(res => {
        const data = Array.isArray(res.data) ? res.data : res.data?.players
        setPlayers(Array.isArray(data) && data.length ? data : null)
        setLoaded(true)
      })
      .catch(() => { setPlayers(null); setLoaded(true) })
  }, [user])

  const hasData = !!(players && players.length)

  return (
    <OSShell title="Player Grades">
      <div className="sec-title" style={{ marginBottom: 16 }}>👤 Player Grade Board</div>

      {!loaded ? (
        <div className="card">
          <div className="card-body" style={{ color: 'var(--text2)', fontSize: 13 }}>Loading player grades…</div>
        </div>
      ) : !hasData ? (
        // Honest empty state - no sample players, no invented insight, and it sets
        // the real expectation (grading is opt-in and needs legible HD film).
        <div className="card">
          <div className="card-body" style={{ lineHeight: 1.7, fontSize: 13 }}>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>No player grades yet</div>
            <p style={{ color: 'var(--text2)', margin: '0 0 10px' }}>
              Player grades appear here after you run a <strong>graded analysis</strong> on a game.
              Grading is jersey-based and reads best on <strong>HD (720p+) film</strong> - on lower-resolution
              or wide single-camera angles, jersey numbers can be too small to grade reliably.
            </p>
            <p style={{ color: 'var(--text2)', margin: 0 }}>
              Turn on the grading pass when you break down a game, and each player with a legible number
              will show up here with their grade.
            </p>
          </div>
        </div>
      ) : (
        <div className="g2">
          <div className="card">
            <div className="card-hdr"><div className="card-title">🏆 Top Performers</div></div>
            <div className="card-body" style={{ padding: 0 }}>
              {players!.map((p, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '9px 16px',
                    borderBottom: i < players!.length - 1 ? '1px solid var(--border)' : 'none',
                  }}
                >
                  <div
                    style={{
                      width: 30, height: 30, borderRadius: '50%',
                      background: 'linear-gradient(135deg,var(--bg4),var(--bg3))',
                      border: '1px solid var(--border2)', display: 'flex', alignItems: 'center',
                      justifyContent: 'center', fontSize: 10, fontWeight: 700, color: 'var(--text2)',
                      fontFamily: 'var(--display)',
                    }}
                  >
                    {p.jersey}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, fontWeight: 500 }}>{p.name}</div>
                    <div style={{ fontSize: 10, color: 'var(--text2)' }}>{p.meta}</div>
                  </div>
                  <div style={{ fontFamily: 'var(--mono)', fontSize: 13, fontWeight: 700, color: p.gradeColor || gradeColor(p.grade) }}>{p.grade}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-hdr"><div className="card-title">📊 Grade Distribution</div></div>
            <div className="card-body">
              {bands(players!).map((b, i) => (
                <div className="pb-wrap" key={i}>
                  <div className="pb-top"><span>{b.label}</span><b>{b.count}</b></div>
                  <div className="pb"><div className={'pf pf-' + b.kind} style={{ width: b.pct + '%' }} /></div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="powered">Powered by <a href="https://cosbyaisolutions.com" target="_blank" rel="noreferrer">Cosby AI Solutions</a></div>
    </OSShell>
  )
}
