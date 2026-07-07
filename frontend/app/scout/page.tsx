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
// Module 8 (free throws + box-outs), Module 7 (special situations), Module 5 (player grades).
type FreeThrowRow = { jersey_number: string; attempts: number; makes: number; pressure_situation: boolean; shooter_tempo: string; box_out_formation_offense: string; box_out_formation_defense: string; quarter: number }
type SpecialRow = { situation_type: string; formation: string; primary_action: string; target: string; result: string; late_and_close: boolean; quarter: number }
type GradeRow = { jersey: string; position: string; handedness: string; role: string; visible_examples: number; scoring: number; defense: number; playmaking: number; rebounding: number }

const SITUATION_TYPES = ['BLOB', 'SLOB', 'press_break', 'last_second', 'end_of_quarter']
const TEMPOS = ['', 'quick', 'routine', 'slow']
const RESULTS = ['made', 'missed', 'reset', 'turnover']
const POSITIONS = ['PG', 'SG', 'SF', 'PF', 'C']
const HANDS = ['', 'right', 'left', 'ambidextrous']

const blankPlayer = (): PlayerRow => ({
  jersey_number: '', player_name: '',
  possession_time_seconds: 0, touches: 0, turnovers: 0, deflections: 0,
  shot_attempts_2pt: 0, shot_makes_2pt: 0, shot_attempts_3pt: 0, shot_makes_3pt: 0,
})
const blankShot = (): ShotRow => ({ jersey_number: '', court_zone: 'Restricted Area', made: false, possession_origin: 'half_court', quarter: 1, possession_seconds: 12 })
const blankFT = (): FreeThrowRow => ({ jersey_number: '', attempts: 2, makes: 0, pressure_situation: false, shooter_tempo: '', box_out_formation_offense: '', box_out_formation_defense: '', quarter: 1 })
const blankSpecial = (): SpecialRow => ({ situation_type: 'BLOB', formation: '', primary_action: '', target: '', result: 'made', late_and_close: false, quarter: 4 })
const blankGrade = (): GradeRow => ({ jersey: '', position: 'PG', handedness: '', role: '', visible_examples: 0, scoring: 0, defense: 0, playmaking: 0, rebounding: 0 })

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
  // Module 1 intake + single-camera calibration — feeds the validation gates
  // (games scouted -> Gate 1, injury -> Gate 8) and the camera-confidence summary.
  const [gamesScouted, setGamesScouted] = useState('')
  const [cameraAngle, setCameraAngle] = useState('')
  const [cameraQuality, setCameraQuality] = useState('')
  const [injuryNote, setInjuryNote] = useState('')
  const [setupOpen, setSetupOpen] = useState(false)
  const [players, setPlayers] = useState<PlayerRow[]>([blankPlayer(), blankPlayer()])
  const [shots, setShots] = useState<ShotRow[]>([])
  const [freeThrows, setFreeThrows] = useState<FreeThrowRow[]>([])
  const [specials, setSpecials] = useState<SpecialRow[]>([])
  const [grades, setGrades] = useState<GradeRow[]>([])
  const [csvOpen, setCsvOpen] = useState(false)
  const [csvText, setCsvText] = useState('')
  const [shotsOpen, setShotsOpen] = useState(false)
  const [ftOpen, setFtOpen] = useState(false)
  const [specialsOpen, setSpecialsOpen] = useState(false)
  const [gradesOpen, setGradesOpen] = useState(false)
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
  const setFT = (i: number, key: keyof FreeThrowRow, val: any) =>
    setFreeThrows(rs => rs.map((r, idx) => (idx === i ? { ...r, [key]: val } : r)))
  const setSpec = (i: number, key: keyof SpecialRow, val: any) =>
    setSpecials(rs => rs.map((r, idx) => (idx === i ? { ...r, [key]: val } : r)))
  const setGrade = (i: number, key: keyof GradeRow, val: any) =>
    setGrades(rs => rs.map((r, idx) => (idx === i ? { ...r, [key]: val } : r)))

  async function createSession(): Promise<string> {
    const res = await api.post('/scout/session', {
      opponent: opponent.trim() || 'Opponent',
      game_date: gameDate || null,
      season: season || null,
      games_scouted: gamesScouted ? Number(gamesScouted) : null,
      camera_angle: cameraAngle || null,
      camera_quality: cameraQuality || null,
      injury_flags: injuryNote.trim() ? [injuryNote.trim()] : null,
    })
    return res.data.session_id
  }

  async function generate() {
    setError('')
    if (!opponent.trim()) { setError('Enter the opponent name first.'); return }
    const validPlayers = players.filter(p => p.jersey_number.trim() !== '')
    const validShots = shots.filter(s => s.jersey_number.trim() !== '')
    const validFT = freeThrows.filter(f => f.jersey_number.trim() !== '')
    const validSpecials = specials  // every added row carries a situation_type
    const validGrades = grades.filter(g => g.jersey.trim() !== '')
    const hasManual = validPlayers.length || validShots.length || validFT.length || validSpecials.length || validGrades.length
    if (!hasManual && csvText.trim() === '') {
      setError('Add at least one player row, shot, free throw, special situation, or grade — or paste a CSV box score.')
      return
    }
    setBusy(true)
    try {
      const sessionId = await createSession()

      if (csvText.trim()) {
        await api.post('/scout/csv', { session_id: sessionId, csv_text: csvText, replace: true })
      }
      if (hasManual) {
        // Drop 1-5 grade fields that are still 0 (ungraded) so the report card
        // only shows grades the analyst actually set.
        const grade = (v: number) => (Number(v) > 0 ? Number(v) : undefined)
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
          free_throws: validFT.map(f => ({
            jersey_number: f.jersey_number, attempts: Number(f.attempts), makes: Number(f.makes),
            pressure_situation: f.pressure_situation, shooter_tempo: f.shooter_tempo || null,
            box_out_formation_offense: f.box_out_formation_offense || null,
            box_out_formation_defense: f.box_out_formation_defense || null, quarter: Number(f.quarter),
          })),
          special_situations: validSpecials.map(s => ({
            situation_type: s.situation_type, formation: s.formation || null,
            primary_action: s.primary_action || null, target: s.target || null,
            result: s.result || null, late_and_close: s.late_and_close, quarter: Number(s.quarter),
          })),
          player_profiles: validGrades.map(g => ({
            jersey: g.jersey, position: g.position || null, handedness: g.handedness || null,
            role: g.role || null, visible_examples: Number(g.visible_examples),
            scoring: grade(g.scoring), defense: grade(g.defense),
            playmaking: grade(g.playmaking), rebounding: grade(g.rebounding),
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

          {/* Module 1 intake + single-camera calibration (powers the validation gates) */}
          <div className="card" style={{ marginBottom: 18 }}>
            <button onClick={() => setSetupOpen(o => !o)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text)', display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, padding: 0 }}>
              {setupOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />} Scouting Setup &amp; Single-Camera Calibration <span style={{ color: 'var(--text3)', fontWeight: 400, fontSize: 12 }}>(optional - sharpens the report&apos;s confidence gates)</span>
            </button>
            {setupOpen && (
              <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                <div>
                  <label className="label">Games Scouted</label>
                  <input className="input" type="number" min={1} value={gamesScouted} onChange={e => setGamesScouted(e.target.value)} placeholder="3+ recommended" />
                </div>
                <div>
                  <label className="label">Camera Angle</label>
                  <select className="input" value={cameraAngle} onChange={e => setCameraAngle(e.target.value)}>
                    <option value="">Not recorded</option>
                    <option value="high and wide">High &amp; wide (full-team spacing)</option>
                    <option value="sideline mid-level">Sideline mid-level (technique)</option>
                    <option value="end zone">Baseline / end zone (paint actions)</option>
                  </select>
                </div>
                <div>
                  <label className="label">Camera Quality</label>
                  <select className="input" value={cameraQuality} onChange={e => setCameraQuality(e.target.value)}>
                    <option value="">Not recorded</option>
                    <option value="clear">Clear</option>
                    <option value="standard">Standard</option>
                    <option value="poor">Poor (drops individual grades a tier)</option>
                  </select>
                </div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <label className="label">Missing Starter / Injury Note</label>
                  <input className="input" value={injuryNote} onChange={e => setInjuryNote(e.target.value)} placeholder="e.g. Starting C out Game 3 - flags affected tendencies (Gate 8)" />
                </div>
              </div>
            )}
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

          {/* Optional: free throws + box-out formations (Module 8) */}
          <div className="card" style={{ marginBottom: 18 }}>
            <button onClick={() => setFtOpen(o => !o)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text)', display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, padding: 0 }}>
              {ftOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />} Free Throws &amp; Box-Outs <span style={{ color: 'var(--text3)', fontWeight: 400, fontSize: 12 }}>(optional - strategic foul targets &amp; never-foul list)</span>
            </button>
            {ftOpen && (
              <div style={{ marginTop: 12, overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 820 }}>
                  <thead><tr>
                    <th style={th}>#</th><th style={th}>Att</th><th style={th}>Made</th><th style={th}>Late/Close?</th>
                    <th style={th}>Tempo</th><th style={th}>Off Box-Out</th><th style={th}>Def Box-Out</th><th style={th}>Qtr</th><th style={th}></th>
                  </tr></thead>
                  <tbody>
                    {freeThrows.map((f, i) => (
                      <tr key={i}>
                        <td style={{ padding: 4, width: 60 }}><input style={cellStyle} value={f.jersey_number} onChange={e => setFT(i, 'jersey_number', e.target.value)} placeholder="#" /></td>
                        <td style={{ padding: 4, width: 60 }}><input style={cellStyle} type="number" value={f.attempts} onChange={e => setFT(i, 'attempts', num(e.target.value))} /></td>
                        <td style={{ padding: 4, width: 60 }}><input style={cellStyle} type="number" value={f.makes} onChange={e => setFT(i, 'makes', num(e.target.value))} /></td>
                        <td style={{ padding: 4, width: 80, textAlign: 'center' }}><input type="checkbox" checked={f.pressure_situation} onChange={e => setFT(i, 'pressure_situation', e.target.checked)} /></td>
                        <td style={{ padding: 4, width: 110 }}>
                          <select style={cellStyle} value={f.shooter_tempo} onChange={e => setFT(i, 'shooter_tempo', e.target.value)}>
                            {TEMPOS.map(t => <option key={t} value={t}>{t || '—'}</option>)}
                          </select>
                        </td>
                        <td style={{ padding: 4, minWidth: 120 }}><input style={cellStyle} value={f.box_out_formation_offense} onChange={e => setFT(i, 'box_out_formation_offense', e.target.value)} placeholder="optional" /></td>
                        <td style={{ padding: 4, minWidth: 120 }}><input style={cellStyle} value={f.box_out_formation_defense} onChange={e => setFT(i, 'box_out_formation_defense', e.target.value)} placeholder="optional" /></td>
                        <td style={{ padding: 4, width: 55 }}><input style={cellStyle} type="number" value={f.quarter} onChange={e => setFT(i, 'quarter', num(e.target.value))} /></td>
                        <td style={{ padding: 4, width: 40 }}><button onClick={() => setFreeThrows(rs => rs.filter((_, idx) => idx !== i))} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text3)' }}><Trash2 size={15} /></button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 6 }}>Under 60% (min 4 attempts) becomes a strategic foul target; 90%+ goes on the never-foul-late list. Check <strong>Late/Close?</strong> for clutch attempts.</div>
                <button onClick={() => setFreeThrows(rs => [...rs, blankFT()])} className="btn-green" style={{ marginTop: 10, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <Plus size={14} /> Add Free Throw
                </button>
              </div>
            )}
          </div>

          {/* Optional: special situations - BLOB/SLOB/press/last-second/EOQ (Module 7) */}
          <div className="card" style={{ marginBottom: 18 }}>
            <button onClick={() => setSpecialsOpen(o => !o)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text)', display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, padding: 0 }}>
              {specialsOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />} Special Situations <span style={{ color: 'var(--text3)', fontWeight: 400, fontSize: 12 }}>(optional - inbounds, press break, last-second sets)</span>
            </button>
            {specialsOpen && (
              <div style={{ marginTop: 12, overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 860 }}>
                  <thead><tr>
                    <th style={th}>Type</th><th style={th}>Formation</th><th style={th}>Primary Action</th><th style={th}>Target #</th>
                    <th style={th}>Result</th><th style={th}>Late &amp; Close?</th><th style={th}>Qtr</th><th style={th}></th>
                  </tr></thead>
                  <tbody>
                    {specials.map((s, i) => (
                      <tr key={i}>
                        <td style={{ padding: 4, width: 150 }}>
                          <select style={cellStyle} value={s.situation_type} onChange={e => setSpec(i, 'situation_type', e.target.value)}>
                            {SITUATION_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                          </select>
                        </td>
                        <td style={{ padding: 4, minWidth: 130 }}><input style={cellStyle} value={s.formation} onChange={e => setSpec(i, 'formation', e.target.value)} placeholder="e.g. Box, Stack" /></td>
                        <td style={{ padding: 4, minWidth: 160 }}><input style={cellStyle} value={s.primary_action} onChange={e => setSpec(i, 'primary_action', e.target.value)} placeholder="e.g. screen the screener" /></td>
                        <td style={{ padding: 4, width: 70 }}><input style={cellStyle} value={s.target} onChange={e => setSpec(i, 'target', e.target.value)} placeholder="#" /></td>
                        <td style={{ padding: 4, width: 110 }}>
                          <select style={cellStyle} value={s.result} onChange={e => setSpec(i, 'result', e.target.value)}>
                            {RESULTS.map(r => <option key={r} value={r}>{r}</option>)}
                          </select>
                        </td>
                        <td style={{ padding: 4, width: 90, textAlign: 'center' }}><input type="checkbox" checked={s.late_and_close} onChange={e => setSpec(i, 'late_and_close', e.target.checked)} /></td>
                        <td style={{ padding: 4, width: 55 }}><input style={cellStyle} type="number" value={s.quarter} onChange={e => setSpec(i, 'quarter', num(e.target.value))} /></td>
                        <td style={{ padding: 4, width: 40 }}><button onClick={() => setSpecials(rs => rs.filter((_, idx) => idx !== i))} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text3)' }}><Trash2 size={15} /></button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 6 }}>A set logged 2+ times — especially <strong>Late &amp; Close</strong> — is flagged as a trusted, must-defend call.</div>
                <button onClick={() => setSpecials(rs => [...rs, blankSpecial()])} className="btn-green" style={{ marginTop: 10, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <Plus size={14} /> Add Special Situation
                </button>
              </div>
            )}
          </div>

          {/* Optional: individual player grade cards (Module 5) */}
          <div className="card" style={{ marginBottom: 18 }}>
            <button onClick={() => setGradesOpen(o => !o)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text)', display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, padding: 0 }}>
              {gradesOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />} Player Grades <span style={{ color: 'var(--text3)', fontWeight: 400, fontSize: 12 }}>(optional - 1-5 scouting grades, single-camera visibility audit)</span>
            </button>
            {gradesOpen && (
              <div style={{ marginTop: 12, overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
                  <thead><tr>
                    <th style={th}>#</th><th style={th}>Pos</th><th style={th}>Hand</th><th style={th}>Role</th>
                    <th style={th}>Visible Looks</th><th style={th}>Scoring</th><th style={th}>Defense</th><th style={th}>Playmaking</th><th style={th}>Reb</th><th style={th}></th>
                  </tr></thead>
                  <tbody>
                    {grades.map((g, i) => (
                      <tr key={i}>
                        <td style={{ padding: 4, width: 60 }}><input style={cellStyle} value={g.jersey} onChange={e => setGrade(i, 'jersey', e.target.value)} placeholder="#" /></td>
                        <td style={{ padding: 4, width: 75 }}>
                          <select style={cellStyle} value={g.position} onChange={e => setGrade(i, 'position', e.target.value)}>
                            {POSITIONS.map(p => <option key={p} value={p}>{p}</option>)}
                          </select>
                        </td>
                        <td style={{ padding: 4, width: 110 }}>
                          <select style={cellStyle} value={g.handedness} onChange={e => setGrade(i, 'handedness', e.target.value)}>
                            {HANDS.map(h => <option key={h} value={h}>{h || '—'}</option>)}
                          </select>
                        </td>
                        <td style={{ padding: 4, minWidth: 130 }}><input style={cellStyle} value={g.role} onChange={e => setGrade(i, 'role', e.target.value)} placeholder="e.g. primary handler" /></td>
                        <td style={{ padding: 4, width: 90 }}><input style={cellStyle} type="number" value={g.visible_examples} onChange={e => setGrade(i, 'visible_examples', num(e.target.value))} placeholder="5+" /></td>
                        <td style={{ padding: 4, width: 70 }}><input style={cellStyle} type="number" min={0} max={5} value={g.scoring} onChange={e => setGrade(i, 'scoring', num(e.target.value))} /></td>
                        <td style={{ padding: 4, width: 70 }}><input style={cellStyle} type="number" min={0} max={5} value={g.defense} onChange={e => setGrade(i, 'defense', num(e.target.value))} /></td>
                        <td style={{ padding: 4, width: 70 }}><input style={cellStyle} type="number" min={0} max={5} value={g.playmaking} onChange={e => setGrade(i, 'playmaking', num(e.target.value))} /></td>
                        <td style={{ padding: 4, width: 70 }}><input style={cellStyle} type="number" min={0} max={5} value={g.rebounding} onChange={e => setGrade(i, 'rebounding', num(e.target.value))} /></td>
                        <td style={{ padding: 4, width: 40 }}><button onClick={() => setGrades(rs => rs.filter((_, idx) => idx !== i))} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text3)' }}><Trash2 size={15} /></button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 6 }}>Grades resting on fewer than 5 clearly visible looks are flagged ESTIMATE (Gate 5). Leave a grade at 0 to omit it.</div>
                <button onClick={() => setGrades(rs => [...rs, blankGrade()])} className="btn-green" style={{ marginTop: 10, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <Plus size={14} /> Add Player Grade
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
