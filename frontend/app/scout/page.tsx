'use client'
import { useEffect, useState, type CSSProperties } from 'react'
import { useRouter } from 'next/navigation'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { Plus, Trash2, Upload, ClipboardPaste, Loader2, Target, ChevronDown, ChevronRight } from 'lucide-react'

// The ten court zones, in the charter taxonomy (Category 6).
const COURT_ZONES = [
  'Restricted Area', 'Paint Non-RA',
  'Mid-Range Left', 'Mid-Range Right', 'Mid-Range Center',
  'Left Corner 3', 'Right Corner 3',
  'Above-the-Break 3 Left', 'Above-the-Break 3 Right', 'Above-the-Break 3 Center',
]
const ORIGINS = ['half_court', 'transition', 'set', 'broken', 'pnr']

type PlayerRow = {
  jersey_number: string; player_name: string
  possession_time_seconds: number; touches: number
  turnovers: number; deflections: number
  shot_attempts_2pt: number; shot_makes_2pt: number
  shot_attempts_3pt: number; shot_makes_3pt: number
}
type ShotRow = { jersey_number: string; court_zone: string; made: boolean; possession_origin: string; quarter: number; possession_seconds: number }

const blankPlayer = (): PlayerRow => ({
  jersey_number: '', player_name: '',
  possession_time_seconds: 0, touches: 0, turnovers: 0, deflections: 0,
  shot_attempts_2pt: 0, shot_makes_2pt: 0, shot_attempts_3pt: 0, shot_makes_3pt: 0,
})
const blankShot = (): ShotRow => ({ jersey_number: '', court_zone: 'Restricted Area', made: false, possession_origin: 'half_court', quarter: 1, possession_seconds: 12 })

const num = (v: string) => (v === '' ? 0 : Number(v) || 0)

// Small, brand-consistent building blocks.
const cellStyle: CSSProperties = {
  width: '100%', background: 'var(--bg3)', border: '1px solid var(--border2)',
  borderRadius: 6, color: 'var(--text)', padding: '6px 8px', fontSize: 13,
}
const CatTag = ({ n, label }: { n: number; label: string }) => (
  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
    <span style={{ background: 'var(--green)', color: '#fff', fontSize: 10, fontWeight: 800, borderRadius: 5, padding: '1px 6px' }}>C{n}</span>
    <span>{label}</span>
  </span>
)

export default function ScoutPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()

  const [opponent, setOpponent] = useState('')
  const [gameDate, setGameDate] = useState('')
  const [season, setSeason] = useState('')
  const [players, setPlayers] = useState<PlayerRow[]>([blankPlayer(), blankPlayer()])
  const [shots, setShots] = useState<ShotRow[]>([])
  const [csvOpen, setCsvOpen] = useState(false)
  const [csvText, setCsvText] = useState('')
  const [shotsOpen, setShotsOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // Sport-aware entry: opponent scouting must stay tied to the sport the client
  // chose for their team/film - never bleed basketball UI (Shot Log, court zones)
  // into a football program. Resolve the org's sport from its teams; football
  // routes to the football scout, basketball renders here, mixed/none picks.
  const [sportMode, setSportMode] = useState<'loading' | 'basketball' | 'choose'>('loading')

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])

  useEffect(() => {
    if (!user) return
    let cancelled = false
    api.get('/teams').then(res => {
      if (cancelled) return
      const sports: string[] = (res.data || []).map((t: any) => t.sport)
      const hasFootball = sports.some(s => s === 'football' || s === 'flag_football')
      const hasBasketball = sports.includes('basketball')
      if (hasFootball && !hasBasketball) router.replace('/scout/football')
      else if (hasBasketball && !hasFootball) setSportMode('basketball')
      else setSportMode('choose')  // both sports, or no teams yet
    }).catch(() => setSportMode('choose'))
    return () => { cancelled = true }
  }, [user, router])

  const setP = (i: number, key: keyof PlayerRow, val: any) =>
    setPlayers(ps => ps.map((p, idx) => (idx === i ? { ...p, [key]: val } : p)))
  const setS = (i: number, key: keyof ShotRow, val: any) =>
    setShots(ss => ss.map((s, idx) => (idx === i ? { ...s, [key]: val } : s)))

  async function createSession(): Promise<string> {
    const res = await api.post('/scout/session', {
      opponent: opponent.trim() || 'Opponent',
      game_date: gameDate || null,
      season: season || null,
    })
    return res.data.session_id
  }

  async function generate() {
    setError('')
    if (!opponent.trim()) { setError('Enter the opponent name first.'); return }
    const validPlayers = players.filter(p => p.jersey_number.trim() !== '')
    const validShots = shots.filter(s => s.jersey_number.trim() !== '')
    if (validPlayers.length === 0 && csvText.trim() === '') {
      setError('Add at least one player row (jersey number) or paste a CSV box score.')
      return
    }
    setBusy(true)
    try {
      const sessionId = await createSession()

      if (csvText.trim()) {
        await api.post('/scout/csv', { session_id: sessionId, csv_text: csvText, replace: true })
      }
      if (validPlayers.length || validShots.length) {
        await api.post('/scout/manual', {
          session_id: sessionId,
          replace: csvText.trim() === '',
          players: validPlayers.map(p => ({
            ...p,
            possession_time_seconds: Number(p.possession_time_seconds),
            touches: Number(p.touches), turnovers: Number(p.turnovers), deflections: Number(p.deflections),
            shot_attempts_2pt: Number(p.shot_attempts_2pt), shot_makes_2pt: Number(p.shot_makes_2pt),
            shot_attempts_3pt: Number(p.shot_attempts_3pt), shot_makes_3pt: Number(p.shot_makes_3pt),
          })),
          shots: validShots.map(s => ({
            jersey_number: s.jersey_number, court_zone: s.court_zone, made: s.made,
            possession_origin: s.possession_origin, quarter: Number(s.quarter),
            possession_seconds: Number(s.possession_seconds),
          })),
        })
      }

      const res = await api.post('/scout/analyze', { session_id: sessionId })
      router.push(`/reports/${res.data.report_id}`)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Something went wrong generating the report.')
      setBusy(false)
    }
  }

  const th: CSSProperties = { textAlign: 'left', fontSize: 11, color: 'var(--text3)', fontWeight: 700, padding: '0 6px 8px', whiteSpace: 'nowrap' }

  // While resolving sport (or redirecting football orgs), never render the
  // basketball UI - that is what caused Shot Log to bleed into football.
  if (sportMode === 'loading') {
    return (
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 flex items-center justify-center">
          <Loader2 size={22} style={{ color: 'var(--gold)' }} className="animate-spin" />
        </main>
      </div>
    )
  }

  if (sportMode === 'choose') {
    return (
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto p-8">
          <div style={{ maxWidth: 640, margin: '0 auto' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
              <Target size={22} style={{ color: 'var(--gold)' }} />
              <h2 className="text-2xl font-bold" style={{ margin: 0 }}>Scout an Opponent</h2>
            </div>
            <p style={{ color: 'var(--text3)', fontSize: 13, marginBottom: 20 }}>
              Pick the sport you are scouting. Everything (fields, tendencies, report) stays tied to that sport.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <button onClick={() => router.push('/scout/football')} className="card" style={{ textAlign: 'left', cursor: 'pointer', border: '1px solid var(--border2)' }}>
                <div style={{ fontWeight: 800, fontSize: 16, color: 'var(--gold)' }}>🏈 Football</div>
                <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 6 }}>Play-by-play, gates, game plan, live logger, position &amp; player exports.</div>
              </button>
              <button onClick={() => setSportMode('basketball')} className="card" style={{ textAlign: 'left', cursor: 'pointer', border: '1px solid var(--border2)' }}>
                <div style={{ fontWeight: 800, fontSize: 16, color: 'var(--green3)' }}>🏀 Basketball</div>
                <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 6 }}>Six-category scout: possession, turnovers, deflections, shot ratio, pace, zones.</div>
              </button>
            </div>
            <p style={{ fontSize: 12, color: 'var(--text3)', marginTop: 16 }}>
              Scouting is available for football and basketball. Set a team&apos;s sport under <span style={{ color: 'var(--green3)' }}>Teams</span> and it will route you automatically next time.
            </p>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <Target size={22} style={{ color: 'var(--gold)' }} />
            <h2 className="text-2xl font-bold" style={{ margin: 0 }}>Scout a Basketball Opponent</h2>
          </div>
          <p style={{ color: 'var(--text3)', fontSize: 13, marginBottom: 20 }}>
            Enter what you charted, in order of importance. CoachLenz turns it into a prioritized, coach-ready scouting brief.
          </p>

          {/* Session header */}
          <div className="card" style={{ marginBottom: 18 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 12 }}>
              <div>
                <label className="label">Opponent</label>
                <input className="input" value={opponent} onChange={e => setOpponent(e.target.value)} placeholder="e.g. Elkmont Red Devils" />
              </div>
              <div>
                <label className="label">Game Date</label>
                <input className="input" type="date" value={gameDate} onChange={e => setGameDate(e.target.value)} />
              </div>
              <div>
                <label className="label">Season</label>
                <input className="input" value={season} onChange={e => setSeason(e.target.value)} placeholder="2025-26" />
              </div>
            </div>
          </div>

          {/* Player table - columns ordered by scouting priority */}
          <div className="card" style={{ marginBottom: 18, overflowX: 'auto' }}>
            <div style={{ fontWeight: 700, marginBottom: 10 }}>Player Stats <span style={{ color: 'var(--text3)', fontWeight: 400, fontSize: 12 }}>(one row per opponent player)</span></div>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
              <thead>
                <tr>
                  <th style={th}>#</th>
                  <th style={th}>Name</th>
                  <th style={th}><CatTag n={1} label="Poss Sec" /></th>
                  <th style={th}><CatTag n={1} label="Touches" /></th>
                  <th style={th}><CatTag n={2} label="TO" /></th>
                  <th style={th}><CatTag n={3} label="Defl" /></th>
                  <th style={th}><CatTag n={4} label="2PA" /></th>
                  <th style={th}>2PM</th>
                  <th style={th}><CatTag n={4} label="3PA" /></th>
                  <th style={th}>3PM</th>
                  <th style={th}></th>
                </tr>
              </thead>
              <tbody>
                {players.map((p, i) => (
                  <tr key={i}>
                    <td style={{ padding: 4, width: 60 }}><input style={cellStyle} value={p.jersey_number} onChange={e => setP(i, 'jersey_number', e.target.value)} placeholder="#" /></td>
                    <td style={{ padding: 4, minWidth: 130 }}><input style={cellStyle} value={p.player_name} onChange={e => setP(i, 'player_name', e.target.value)} placeholder="optional" /></td>
                    <td style={{ padding: 4, width: 80 }}><input style={cellStyle} type="number" value={p.possession_time_seconds} onChange={e => setP(i, 'possession_time_seconds', num(e.target.value))} /></td>
                    <td style={{ padding: 4, width: 70 }}><input style={cellStyle} type="number" value={p.touches} onChange={e => setP(i, 'touches', num(e.target.value))} /></td>
                    <td style={{ padding: 4, width: 60 }}><input style={cellStyle} type="number" value={p.turnovers} onChange={e => setP(i, 'turnovers', num(e.target.value))} /></td>
                    <td style={{ padding: 4, width: 60 }}><input style={cellStyle} type="number" value={p.deflections} onChange={e => setP(i, 'deflections', num(e.target.value))} /></td>
                    <td style={{ padding: 4, width: 60 }}><input style={cellStyle} type="number" value={p.shot_attempts_2pt} onChange={e => setP(i, 'shot_attempts_2pt', num(e.target.value))} /></td>
                    <td style={{ padding: 4, width: 60 }}><input style={cellStyle} type="number" value={p.shot_makes_2pt} onChange={e => setP(i, 'shot_makes_2pt', num(e.target.value))} /></td>
                    <td style={{ padding: 4, width: 60 }}><input style={cellStyle} type="number" value={p.shot_attempts_3pt} onChange={e => setP(i, 'shot_attempts_3pt', num(e.target.value))} /></td>
                    <td style={{ padding: 4, width: 60 }}><input style={cellStyle} type="number" value={p.shot_makes_3pt} onChange={e => setP(i, 'shot_makes_3pt', num(e.target.value))} /></td>
                    <td style={{ padding: 4, width: 40 }}>
                      <button onClick={() => setPlayers(ps => ps.filter((_, idx) => idx !== i))} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text3)' }}><Trash2 size={15} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <button onClick={() => setPlayers(ps => [...ps, blankPlayer()])} className="btn-green" style={{ marginTop: 10, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <Plus size={14} /> Add Player
            </button>
          </div>

          {/* Optional: detailed shot log for the scoring-zone map (Category 6) */}
          <div className="card" style={{ marginBottom: 18 }}>
            <button onClick={() => setShotsOpen(o => !o)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text)', display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, padding: 0 }}>
              {shotsOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />} Shot Log by Zone <span style={{ color: 'var(--text3)', fontWeight: 400, fontSize: 12 }}>(optional - powers the eFG% scoring-zone map)</span>
            </button>
            {shotsOpen && (
              <div style={{ marginTop: 12, overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
                  <thead><tr>
                    <th style={th}>#</th><th style={th}><CatTag n={6} label="Court Zone" /></th><th style={th}>Made?</th>
                    <th style={th}><CatTag n={5} label="Origin" /></th><th style={th}>Qtr</th><th style={th}><CatTag n={5} label="Poss Sec" /></th><th style={th}></th>
                  </tr></thead>
                  <tbody>
                    {shots.map((s, i) => (
                      <tr key={i}>
                        <td style={{ padding: 4, width: 60 }}><input style={cellStyle} value={s.jersey_number} onChange={e => setS(i, 'jersey_number', e.target.value)} placeholder="#" /></td>
                        <td style={{ padding: 4, minWidth: 180 }}>
                          <select style={cellStyle} value={s.court_zone} onChange={e => setS(i, 'court_zone', e.target.value)}>
                            {COURT_ZONES.map(z => <option key={z} value={z}>{z}</option>)}
                          </select>
                        </td>
                        <td style={{ padding: 4, width: 70, textAlign: 'center' }}><input type="checkbox" checked={s.made} onChange={e => setS(i, 'made', e.target.checked)} /></td>
                        <td style={{ padding: 4, width: 130 }}>
                          <select style={cellStyle} value={s.possession_origin} onChange={e => setS(i, 'possession_origin', e.target.value)}>
                            {ORIGINS.map(o => <option key={o} value={o}>{o}</option>)}
                          </select>
                        </td>
                        <td style={{ padding: 4, width: 60 }}><input style={cellStyle} type="number" value={s.quarter} onChange={e => setS(i, 'quarter', num(e.target.value))} /></td>
                        <td style={{ padding: 4, width: 80 }}><input style={cellStyle} type="number" value={s.possession_seconds} onChange={e => setS(i, 'possession_seconds', num(e.target.value))} /></td>
                        <td style={{ padding: 4, width: 40 }}><button onClick={() => setShots(ss => ss.filter((_, idx) => idx !== i))} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text3)' }}><Trash2 size={15} /></button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <button onClick={() => setShots(ss => [...ss, blankShot()])} className="btn-green" style={{ marginTop: 10, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <Plus size={14} /> Add Shot
                </button>
              </div>
            )}
          </div>

          {/* Optional: CSV box-score paste */}
          <div className="card" style={{ marginBottom: 18 }}>
            <button onClick={() => setCsvOpen(o => !o)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text)', display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, padding: 0 }}>
              {csvOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />} <ClipboardPaste size={15} /> Import CSV Box Score <span style={{ color: 'var(--text3)', fontWeight: 400, fontSize: 12 }}>(optional - paste a standard box score, columns auto-mapped)</span>
            </button>
            {csvOpen && (
              <div style={{ marginTop: 12 }}>
                <textarea
                  className="input" style={{ minHeight: 140, fontFamily: 'var(--font-dm-mono, monospace)', fontSize: 12 }}
                  value={csvText} onChange={e => setCsvText(e.target.value)}
                  placeholder={'jersey,name,fg2a,fg2m,fg3a,fg3m,to,defl,touches,poss_sec\n3,Smith,10,6,1,0,2,1,40,110\n11,Jones,3,1,8,4,1,0,18,44'}
                />
                <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 6 }}>
                  Recognized columns: jersey/number, name, fg2a/fg2m, fg3a/fg3m, to, defl, touches, poss_sec. Unmatched columns are ignored.
                </div>
              </div>
            )}
          </div>

          {error && (
            <div style={{ background: 'var(--redl)', border: '1px solid rgba(224,112,112,0.3)', color: 'var(--red)', borderRadius: 8, padding: '10px 14px', marginBottom: 14, fontSize: 13 }}>{error}</div>
          )}

          <button onClick={generate} disabled={busy} className="btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, opacity: busy ? 0.7 : 1 }}>
            {busy ? <><Loader2 size={16} className="animate-spin" /> Generating Report…</> : <><Upload size={16} /> Generate Scouting Report</>}
          </button>
          <p style={{ fontSize: 11, color: 'var(--text3)', marginTop: 10 }}>
            Report priority order: <strong>1</strong> Time of Possession · <strong>2</strong> Turnovers · <strong>3</strong> Deflections · <strong>4</strong> Shot Ratio · <strong>5</strong> Pace · <strong>6</strong> Scoring Areas, plus auto game-plan.
          </p>
        </div>
      </main>
    </div>
  )
}
