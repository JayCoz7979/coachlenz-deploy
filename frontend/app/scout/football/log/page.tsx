'use client'
import { useEffect, useState, useRef, useCallback, type CSSProperties } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { Zap, Loader2, Undo2, Save, FileBarChart, CheckCircle2 } from 'lucide-react'

type Side = 'offense' | 'defense' | 'special_teams'
type Play = {
  side: Side; game_number: string; quarter: string; down: string; distance: string
  field_position: string; formation: string; personnel: string; play_type: string
  run_concept: string; pass_concept: string; yards_gained: string; result: string
  coverage: string; blitz: string; motion: boolean; player: string
  _saved?: boolean
}
type Session = { session_id: string; opponent: string; status: string }

const blank = (carry?: Partial<Play>): Play => ({
  side: carry?.side || 'offense', game_number: carry?.game_number || '1',
  quarter: carry?.quarter || '1', down: carry?.down || '1', distance: carry?.distance || '10',
  field_position: carry?.field_position || '', formation: carry?.formation || '',
  personnel: carry?.personnel || '', play_type: '', run_concept: '', pass_concept: '',
  yards_gained: '', result: '', coverage: '', blitz: '', motion: false, player: '',
})

// Field position as an absolute 0-100 yardline (own goal 0 -> opp goal 100).
const toAbs = (spot: string): number | null => {
  const m = spot.trim().toUpperCase().match(/^(OWN|OPP)?\s*(\d{1,2})$/)
  if (!m) return null
  const yl = Number(m[2])
  if (m[1] === 'OPP') return 100 - yl
  if (m[1] === 'OWN' || !m[1]) return yl
  return null
}
const toSpot = (abs: number): string => {
  const a = Math.max(1, Math.min(99, abs))
  if (a === 50) return '50'
  return a < 50 ? `OWN ${a}` : `OPP ${100 - a}`
}

const cell: CSSProperties = {
  width: '100%', background: 'var(--bg3)', border: '1px solid var(--border2)',
  borderRadius: 6, color: 'var(--text)', padding: '8px 9px', fontSize: 14,
}
const lbl: CSSProperties = { fontSize: 10, color: 'var(--text3)', fontWeight: 700, letterSpacing: '0.06em', marginBottom: 3, display: 'block', textTransform: 'uppercase' }
const kbd: CSSProperties = { background: 'var(--bg3)', border: '1px solid var(--border2)', borderRadius: 4, padding: '1px 6px', fontSize: 11, fontFamily: 'monospace', color: 'var(--gold)' }

export default function LiveLoggerPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()

  const [session, setSession] = useState<Session | null>(null)
  const [sessions, setSessions] = useState<Session[]>([])
  const [newOpponent, setNewOpponent] = useState('')
  const [cur, setCur] = useState<Play>(blank())
  const [plays, setPlays] = useState<Play[]>([])
  const [busy, setBusy] = useState(false)
  const [flushing, setFlushing] = useState(false)
  const [error, setError] = useState('')
  const [savedAt, setSavedAt] = useState('')
  const firstRef = useRef<HTMLSelectElement>(null)

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])

  // Load sessions; auto-select if ?session= is present.
  useEffect(() => {
    if (!user) return
    api.get('/scout/football/sessions').then(r => {
      const list: Session[] = r.data.sessions || []
      setSessions(list)
      const sid = typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get('session') : null
      if (sid) { const s = list.find(x => x.session_id === sid); if (s) setSession(s) }
    }).catch(() => {})
  }, [user])

  const set = (k: keyof Play, v: any) => setCur(c => ({ ...c, [k]: v }))
  const unsaved = plays.filter(p => !p._saved).length

  const flush = useCallback(async (): Promise<boolean> => {
    if (!session) return false
    const pending = plays.filter(p => !p._saved)
    if (!pending.length) return true
    setFlushing(true); setError('')
    try {
      await api.post('/scout/football/plays', {
        session_id: session.session_id,
        plays: pending.map(({ _saved, ...p }) => ({
          side: p.side, game_number: Number(p.game_number) || null, quarter: Number(p.quarter) || null,
          down: Number(p.down) || null, distance: Number(p.distance) || null,
          field_position: p.field_position || null, formation: p.formation || null,
          personnel: p.personnel || null, play_type: p.play_type || null,
          run_concept: p.run_concept || null, pass_concept: p.pass_concept || null,
          yards_gained: p.yards_gained === '' ? null : Number(p.yards_gained),
          result: p.result || null, coverage: p.coverage || null, blitz: p.blitz || null, motion: p.motion,
          primary_player_jersey: p.player || null,
        })),
      })
      setPlays(ps => ps.map(p => ({ ...p, _saved: true })))
      setSavedAt(new Date().toLocaleTimeString())
      return true
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Save failed. Your plays are still here, try Save again.')
      return false
    } finally { setFlushing(false) }
  }, [session, plays])

  const commit = useCallback(() => {
    setCur(c => {
      // Need at least a play type or a down to be a real play.
      if (!c.play_type && !c.down) return c
      const gained = c.yards_gained === '' ? 0 : Number(c.yards_gained) || 0
      const dist = Number(c.distance) || 10
      const dn = Number(c.down) || 1
      const changePoss = /turnover|int|interception|fumble|punt|downs|touchdown|td\b|safety|field goal|missed/i.test(c.result)
      const converted = gained >= dist
      let nDown = dn + 1, nDist = Math.max(dist - gained, 1)
      if (changePoss || converted || dn >= 4) { nDown = 1; nDist = 10 }

      // Advance the ball unless possession changed.
      let nSpot = c.field_position
      const abs = toAbs(c.field_position)
      if (abs != null && !changePoss) nSpot = toSpot(abs + gained)
      if (changePoss) nSpot = ''

      setPlays(ps => [...ps, { ...c }])
      return blank({
        side: c.side, game_number: c.game_number, quarter: c.quarter,
        formation: converted || changePoss ? c.formation : c.formation,
        personnel: c.personnel, down: String(nDown), distance: String(nDist), field_position: nSpot,
      })
    })
    setTimeout(() => firstRef.current?.focus(), 0)
  }, [])

  const undo = useCallback(() => setPlays(ps => ps.slice(0, -1)), [])

  // Autosave every 8 unsaved plays.
  useEffect(() => { if (unsaved >= 8 && !flushing) flush() }, [unsaved, flushing, flush])

  // Global hotkeys, only when NOT typing in a text field.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!session) return
      const el = document.activeElement as HTMLElement | null
      const typing = el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); commit(); return }
      if (typing) return
      const k = e.key.toLowerCase()
      if (k === 'o') set('side', 'offense')
      else if (k === 'd') set('side', 'defense')
      else if (k === 's') set('side', 'special_teams')
      else if (k === 'r') set('play_type', 'run')
      else if (k === 'p') set('play_type', 'pass')
      else if (['1', '2', '3', '4'].includes(k)) set('down', k)
      else if (k === 'u') undo()
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [session, commit, undo])

  async function createSession() {
    if (!newOpponent.trim()) { setError('Enter the opponent name.'); return }
    setBusy(true); setError('')
    try {
      const r = await api.post('/scout/football/session', { opponent: newOpponent.trim() })
      setSession({ session_id: r.data.session_id, opponent: r.data.opponent, status: 'draft' })
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Could not create session.')
    } finally { setBusy(false) }
  }

  async function generate() {
    setBusy(true)
    const ok = await flush()
    if (!ok) { setBusy(false); return }
    try {
      const r = await api.post('/scout/football/analyze', { session_id: session!.session_id })
      router.push(`/reports/${r.data.report_id}`)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Could not generate the report.')
      setBusy(false)
    }
  }

  // ── session gate ──────────────────────────────────────────────────────────
  if (!session) {
    return (
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto p-8">
          <div style={{ maxWidth: 640, margin: '0 auto' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
              <Zap size={22} style={{ color: 'var(--gold)' }} />
              <h2 className="text-2xl font-bold" style={{ margin: 0 }}>Live Play Logger</h2>
            </div>
            <p style={{ color: 'var(--text3)', fontSize: 13, marginBottom: 20 }}>
              Keyboard-first charting for game film. Pick a session or start a new one.
            </p>
            {error && <div style={{ background: 'var(--redl)', color: 'var(--red)', borderRadius: 8, padding: '10px 14px', marginBottom: 14, fontSize: 13 }}>{error}</div>}
            <div className="card" style={{ marginBottom: 16 }}>
              <label className="label">New opponent</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <input className="input" value={newOpponent} onChange={e => setNewOpponent(e.target.value)} placeholder="e.g. Athens Golden Eagles" onKeyDown={e => e.key === 'Enter' && createSession()} />
                <button onClick={createSession} disabled={busy} className="btn-primary" style={{ whiteSpace: 'nowrap' }}>
                  {busy ? <Loader2 size={15} className="animate-spin" /> : 'Start'}
                </button>
              </div>
            </div>
            {sessions.length > 0 && (
              <div className="card">
                <div style={{ fontWeight: 700, marginBottom: 10 }}>Continue a session</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {sessions.map(s => (
                    <button key={s.session_id} onClick={() => setSession(s)} style={{ ...cell, textAlign: 'left', cursor: 'pointer', display: 'flex', justifyContent: 'space-between' }}>
                      <span>{s.opponent}</span><span style={{ color: 'var(--text3)', fontSize: 12 }}>{s.status}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    )
  }

  // ── logger ────────────────────────────────────────────────────────────────
  const sideBtn = (s: Side, label: string, key: string) => (
    <button onClick={() => set('side', s)} style={{
      flex: 1, padding: '8px 0', borderRadius: 6, fontSize: 13, fontWeight: 700, cursor: 'pointer',
      border: '1px solid ' + (cur.side === s ? 'var(--gold)' : 'var(--border2)'),
      background: cur.side === s ? 'rgba(201,168,76,0.15)' : 'var(--bg3)',
      color: cur.side === s ? 'var(--gold)' : 'var(--text2)',
    }}>{label} <span style={{ opacity: 0.6, fontSize: 10 }}>({key})</span></button>
  )

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6">
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
            <Zap size={20} style={{ color: 'var(--gold)' }} />
            <h2 className="text-xl font-bold" style={{ margin: 0 }}>Logging: {session.opponent}</h2>
            <span style={{ fontSize: 12, color: 'var(--text3)' }}>{plays.length} plays</span>
            {unsaved > 0
              ? <span style={{ fontSize: 12, color: 'var(--gold)' }}>{unsaved} unsaved</span>
              : savedAt && <span style={{ fontSize: 12, color: 'var(--green3)', display: 'inline-flex', alignItems: 'center', gap: 4 }}><CheckCircle2 size={13} /> saved {savedAt}</span>}
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
              <button onClick={() => flush()} disabled={flushing || unsaved === 0} className="btn-green" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, opacity: unsaved === 0 ? 0.5 : 1 }}>
                {flushing ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save
              </button>
              <button onClick={generate} disabled={busy || plays.length === 0} className="btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                {busy ? <Loader2 size={14} className="animate-spin" /> : <FileBarChart size={14} />} Generate Report
              </button>
            </div>
          </div>

          {error && <div style={{ background: 'var(--redl)', color: 'var(--red)', borderRadius: 8, padding: '10px 14px', marginBottom: 12, fontSize: 13 }}>{error}</div>}

          {/* Now logging */}
          <div className="card" style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              {sideBtn('offense', 'Offense', 'o')}
              {sideBtn('defense', 'Defense', 'd')}
              {sideBtn('special_teams', 'Special', 's')}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 10 }}>
              <div><span style={lbl}>Gm</span><select ref={firstRef} style={cell} value={cur.game_number} onChange={e => set('game_number', e.target.value)}>{[1,2,3,4,5].map(n => <option key={n} value={n}>{n}</option>)}</select></div>
              <div><span style={lbl}>Qtr</span><select style={cell} value={cur.quarter} onChange={e => set('quarter', e.target.value)}>{[1,2,3,4,5].map(n => <option key={n} value={n}>{n}</option>)}</select></div>
              <div><span style={lbl}>Down</span><select style={cell} value={cur.down} onChange={e => set('down', e.target.value)}>{[1,2,3,4].map(n => <option key={n} value={n}>{n}</option>)}</select></div>
              <div><span style={lbl}>Dist</span><input style={cell} value={cur.distance} onChange={e => set('distance', e.target.value)} inputMode="numeric" /></div>
              <div><span style={lbl}>Ball On</span><input style={cell} value={cur.field_position} onChange={e => set('field_position', e.target.value)} placeholder="OWN 35" /></div>
              <div><span style={lbl}>Formation</span><input style={cell} value={cur.formation} onChange={e => set('formation', e.target.value)} placeholder="Shotgun" /></div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 10, marginTop: 10 }}>
              <div><span style={lbl}>Pers</span><input style={cell} value={cur.personnel} onChange={e => set('personnel', e.target.value)} placeholder="11" /></div>
              <div><span style={lbl}>Play (r/p)</span><input style={cell} value={cur.play_type} onChange={e => set('play_type', e.target.value)} placeholder="run" /></div>
              <div><span style={lbl}>Run Concept</span><input style={cell} value={cur.run_concept} onChange={e => set('run_concept', e.target.value)} placeholder="Inside Zone" /></div>
              <div><span style={lbl}>Pass Concept</span><input style={cell} value={cur.pass_concept} onChange={e => set('pass_concept', e.target.value)} placeholder="Four Verts" /></div>
              <div><span style={lbl}>Yards</span><input style={cell} value={cur.yards_gained} onChange={e => set('yards_gained', e.target.value)} inputMode="numeric" /></div>
              <div><span style={lbl}>Result</span><input style={cell} value={cur.result} onChange={e => set('result', e.target.value)} placeholder="gain / TD" /></div>
            </div>
            {cur.side === 'defense' && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 10, marginTop: 10 }}>
                <div><span style={lbl}>Coverage</span><input style={cell} value={cur.coverage} onChange={e => set('coverage', e.target.value)} placeholder="Cover 3" /></div>
                <div><span style={lbl}>Blitz</span><input style={cell} value={cur.blitz} onChange={e => set('blitz', e.target.value)} placeholder="Edge L" /></div>
              </div>
            )}
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 12 }}>
              <label style={{ fontSize: 12, color: 'var(--text2)', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span style={{ color: 'var(--text3)', fontWeight: 700 }}>BC / Tgt #</span>
                <input style={{ ...cell, width: 70, padding: '6px 8px' }} value={cur.player} onChange={e => set('player', e.target.value)} placeholder="#" inputMode="numeric" />
              </label>
              <label style={{ fontSize: 13, color: 'var(--text2)', display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                <input type="checkbox" checked={cur.motion} onChange={e => set('motion', e.target.checked)} /> Motion
              </label>
              <button onClick={commit} className="btn-primary" style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                Log Play <span style={{ ...kbd, color: '#1c1c1c', background: 'rgba(0,0,0,0.15)', borderColor: 'transparent' }}>Enter</span>
              </button>
              <button onClick={undo} disabled={!plays.length} style={{ background: 'transparent', border: '1px solid var(--border2)', borderRadius: 8, color: 'var(--text3)', padding: '8px 12px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, opacity: plays.length ? 1 : 0.5 }}>
                <Undo2 size={14} /> Undo <span style={kbd}>u</span>
              </button>
            </div>
          </div>

          {/* Shortcut legend */}
          <div style={{ fontSize: 12, color: 'var(--text3)', marginBottom: 14, display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            <span><b style={{ color: 'var(--text2)' }}>Hotkeys:</b></span>
            <span><span style={kbd}>o</span>/<span style={kbd}>d</span>/<span style={kbd}>s</span> side</span>
            <span><span style={kbd}>1</span>-<span style={kbd}>4</span> down</span>
            <span><span style={kbd}>r</span>/<span style={kbd}>p</span> run/pass</span>
            <span><span style={kbd}>Enter</span> log play (auto-advances down &amp; distance)</span>
            <span><span style={kbd}>u</span> undo</span>
          </div>

          {/* Recent plays */}
          {plays.length > 0 && (
            <div className="card" style={{ overflowX: 'auto' }}>
              <div style={{ fontWeight: 700, marginBottom: 8, fontSize: 13 }}>Recent plays</div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, minWidth: 640 }}>
                <thead><tr style={{ color: 'var(--text3)', textAlign: 'left' }}>
                  <th style={{ padding: '4px 8px' }}>#</th><th style={{ padding: '4px 8px' }}>Side</th><th style={{ padding: '4px 8px' }}>D&amp;D</th>
                  <th style={{ padding: '4px 8px' }}>Form</th><th style={{ padding: '4px 8px' }}>Play</th><th style={{ padding: '4px 8px' }}>Concept</th>
                  <th style={{ padding: '4px 8px' }}>Yds</th><th style={{ padding: '4px 8px' }}>Result</th><th style={{ padding: '4px 8px' }}></th>
                </tr></thead>
                <tbody>
                  {plays.slice(-14).reverse().map((p, i) => (
                    <tr key={plays.length - i} style={{ borderTop: '1px solid var(--border2)' }}>
                      <td style={{ padding: '4px 8px', color: 'var(--text3)' }}>{plays.length - i}</td>
                      <td style={{ padding: '4px 8px' }}>{p.side === 'special_teams' ? 'ST' : p.side[0].toUpperCase()}</td>
                      <td style={{ padding: '4px 8px' }}>{p.down}&amp;{p.distance}</td>
                      <td style={{ padding: '4px 8px' }}>{p.formation || '-'}</td>
                      <td style={{ padding: '4px 8px' }}>{p.play_type || '-'}</td>
                      <td style={{ padding: '4px 8px' }}>{p.run_concept || p.pass_concept || '-'}</td>
                      <td style={{ padding: '4px 8px' }}>{p.yards_gained || '-'}</td>
                      <td style={{ padding: '4px 8px' }}>{p.result || '-'}</td>
                      <td style={{ padding: '4px 8px', color: p._saved ? 'var(--green3)' : 'var(--gold)' }}>{p._saved ? '✓' : '•'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div style={{ marginTop: 16 }}>
            <Link href="/scout/football" style={{ fontSize: 12, color: 'var(--text3)' }}>← back to scout setup</Link>
          </div>
        </div>
      </main>
    </div>
  )
}
