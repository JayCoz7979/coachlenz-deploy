'use client'
import { useEffect, useState, type CSSProperties } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { Plus, Trash2, Upload, ClipboardPaste, Loader2, ClipboardList, ChevronDown, ChevronRight, ShieldCheck } from 'lucide-react'

const SIDES = ['offense', 'defense', 'special_teams'] as const
const FORMATIONS = ['Shotgun', 'Under Center', 'Pistol', 'Empty', 'I-Form', 'Trips Right', 'Trips Left', 'Bunch', 'Jumbo', 'Wildcat']
const PLAY_TYPES = ['run', 'pass', 'rpo', 'screen', 'play action', 'punt', 'kickoff', 'field goal', 'pat']

type PlayRow = {
  side: typeof SIDES[number]
  down: string; distance: string; field_position: string
  formation: string; personnel: string; play_type: string
  run_concept: string; pass_concept: string
  yards_gained: string; result: string
  coverage: string; blitz: string; motion: boolean
  game_number: string
}

const blankPlay = (side: typeof SIDES[number] = 'offense'): PlayRow => ({
  side, down: '', distance: '', field_position: '', formation: '', personnel: '',
  play_type: '', run_concept: '', pass_concept: '', yards_gained: '', result: '',
  coverage: '', blitz: '', motion: false, game_number: '1',
})

const asInt = (v: string) => (v.trim() === '' ? null : Number(v))

const cellStyle: CSSProperties = {
  width: '100%', background: 'var(--bg3)', border: '1px solid var(--border2)',
  borderRadius: 6, color: 'var(--text)', padding: '6px 8px', fontSize: 13,
}
const th: CSSProperties = { textAlign: 'left', fontSize: 11, color: 'var(--text3)', fontWeight: 700, padding: '0 6px 8px', whiteSpace: 'nowrap' }

export default function ScoutFootballPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()

  // Module 1 - intake / intelligence brief
  const [opponent, setOpponent] = useState('')
  const [gameDate, setGameDate] = useState('')
  const [season, setSeason] = useState('')
  const [week, setWeek] = useState('')
  const [site, setSite] = useState('')
  const [gamesScouted, setGamesScouted] = useState('')
  const [injuryNote, setInjuryNote] = useState('')

  // Module 2 - play log (manual grid + Hudl CSV paste)
  const [plays, setPlays] = useState<PlayRow[]>([blankPlay('offense'), blankPlay('offense')])
  const [csvOpen, setCsvOpen] = useState(false)
  const [csvText, setCsvText] = useState('')
  const [defaultSide, setDefaultSide] = useState<typeof SIDES[number]>('offense')

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])

  const setPlay = (i: number, key: keyof PlayRow, val: any) =>
    setPlays(ps => ps.map((p, idx) => (idx === i ? { ...p, [key]: val } : p)))

  // Live, honest confidence warnings (mirror the backend gates before submit).
  const warnings: string[] = []
  const filledPlays = plays.filter(p => p.down || p.play_type || p.formation || p.result)
  const totalPlanned = filledPlays.length + (csvText.trim() ? csvText.trim().split('\n').length - 1 : 0)
  if (totalPlanned > 0 && totalPlanned < 60) warnings.push(`~${totalPlanned} plays entered - under the 60-play line, the report will be PRELIMINARY (Gate 1).`)
  if (gamesScouted && Number(gamesScouted) < 3) warnings.push('Fewer than 3 games scouted reduces data confidence (Gate 1).')
  warnings.push('You are the primary analyst. A second review-authorized user must sign off before the report can be FINAL (Gate 2).')

  async function createSession(): Promise<string> {
    const res = await api.post('/scout/football/session', {
      opponent: opponent.trim() || 'Opponent',
      game_date: gameDate || null,
      season: season || null,
      week: asInt(week),
      site: site || null,
      games_scouted: asInt(gamesScouted),
      injury_flags: injuryNote.trim() ? [injuryNote.trim()] : [],
    })
    return res.data.session_id
  }

  async function generate() {
    setError('')
    if (!opponent.trim()) { setError('Enter the opponent name first.'); return }
    if (filledPlays.length === 0 && csvText.trim() === '') {
      setError('Log at least one play, or paste a Hudl CSV play log.')
      return
    }
    setBusy(true)
    try {
      const sessionId = await createSession()

      if (csvText.trim()) {
        await api.post('/scout/football/csv', {
          session_id: sessionId, csv_text: csvText, default_side: defaultSide, replace: true,
        })
      }
      if (filledPlays.length) {
        await api.post('/scout/football/plays', {
          session_id: sessionId,
          replace: csvText.trim() === '',
          plays: filledPlays.map(p => ({
            side: p.side,
            game_number: asInt(p.game_number),
            down: asInt(p.down), distance: asInt(p.distance),
            field_position: p.field_position || null,
            formation: p.formation || null, personnel: p.personnel || null,
            play_type: p.play_type || null,
            run_concept: p.run_concept || null, pass_concept: p.pass_concept || null,
            yards_gained: asInt(p.yards_gained), result: p.result || null,
            coverage: p.coverage || null, blitz: p.blitz || null, motion: p.motion,
          })),
        })
      }

      const res = await api.post('/scout/football/analyze', { session_id: sessionId })
      router.push(`/reports/${res.data.report_id}`)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Something went wrong generating the report.')
      setBusy(false)
    }
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <ClipboardList size={22} style={{ color: 'var(--gold)' }} />
              <h2 className="text-2xl font-bold" style={{ margin: 0 }}>Scout a Football Opponent</h2>
            </div>
            <Link href="/scout/football/sessions" style={{ fontSize: 13, color: 'var(--green3)' }}>Sessions &amp; review queue</Link>
          </div>
          <p style={{ color: 'var(--text3)', fontSize: 13, marginBottom: 20 }}>
            Log the play-by-play (or paste a Hudl export). CoachLenz runs seven validation gates and returns an installable,
            coordinator-grade game plan with a confidence tier on every call.
          </p>

          {/* Module 1 - intelligence brief */}
          <div className="card" style={{ marginBottom: 18 }}>
            <div style={{ fontWeight: 700, marginBottom: 10 }}>Intelligence Brief</div>
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 12 }}>
              <div><label className="label">Opponent</label>
                <input className="input" value={opponent} onChange={e => setOpponent(e.target.value)} placeholder="e.g. Athens Golden Eagles" /></div>
              <div><label className="label">Game Date</label>
                <input className="input" type="date" value={gameDate} onChange={e => setGameDate(e.target.value)} /></div>
              <div><label className="label">Week</label>
                <input className="input" type="number" value={week} onChange={e => setWeek(e.target.value)} placeholder="7" /></div>
              <div><label className="label">Site</label>
                <select className="input" value={site} onChange={e => setSite(e.target.value)}>
                  <option value="">-</option><option value="home">Home</option><option value="away">Away</option><option value="neutral">Neutral</option>
                </select></div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12, marginTop: 12 }}>
              <div><label className="label">Season</label>
                <input className="input" value={season} onChange={e => setSeason(e.target.value)} placeholder="2025-26" /></div>
              <div><label className="label">Primary Analyst</label>
                <input className="input" value={user?.name ? `${user.name} (you)` : 'you'} disabled style={{ opacity: 0.7 }} /></div>
              <div><label className="label">Reviewer</label>
                <input className="input" value="set at sign-off" disabled style={{ opacity: 0.7 }} /></div>
              <div><label className="label">Games Scouted</label>
                <input className="input" type="number" value={gamesScouted} onChange={e => setGamesScouted(e.target.value)} placeholder="3+" /></div>
            </div>
            <div style={{ marginTop: 12 }}>
              <label className="label">Injury / Missing Starter Note (flags affected tendencies - Gate 7)</label>
              <input className="input" value={injuryNote} onChange={e => setInjuryNote(e.target.value)} placeholder="e.g. Starting MLB #44 out since Week 5" />
            </div>
          </div>

          {/* Module 2 - play log grid */}
          <div className="card" style={{ marginBottom: 18, overflowX: 'auto' }}>
            <div style={{ fontWeight: 700, marginBottom: 10 }}>Play Log <span style={{ color: 'var(--text3)', fontWeight: 400, fontSize: 12 }}>(one row per play - opponent offense, defense, or special teams)</span></div>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1080 }}>
              <thead><tr>
                <th style={th}>Side</th><th style={th}>Gm</th><th style={th}>Dn</th><th style={th}>Dist</th>
                <th style={th}>Ball On</th><th style={th}>Formation</th><th style={th}>Pers</th><th style={th}>Play</th>
                <th style={th}>Run Concept</th><th style={th}>Pass Concept</th><th style={th}>Yds</th><th style={th}>Result</th>
                <th style={th}>Coverage</th><th style={th}>Blitz</th><th style={th}>Mot</th><th style={th}></th>
              </tr></thead>
              <tbody>
                {plays.map((p, i) => (
                  <tr key={i}>
                    <td style={{ padding: 4, width: 110 }}>
                      <select style={cellStyle} value={p.side} onChange={e => setPlay(i, 'side', e.target.value)}>
                        {SIDES.map(s => <option key={s} value={s}>{s === 'special_teams' ? 'special' : s}</option>)}
                      </select></td>
                    <td style={{ padding: 4, width: 44 }}><input style={cellStyle} value={p.game_number} onChange={e => setPlay(i, 'game_number', e.target.value)} /></td>
                    <td style={{ padding: 4, width: 44 }}><input style={cellStyle} value={p.down} onChange={e => setPlay(i, 'down', e.target.value)} /></td>
                    <td style={{ padding: 4, width: 48 }}><input style={cellStyle} value={p.distance} onChange={e => setPlay(i, 'distance', e.target.value)} /></td>
                    <td style={{ padding: 4, width: 80 }}><input style={cellStyle} value={p.field_position} onChange={e => setPlay(i, 'field_position', e.target.value)} placeholder="OWN 35" /></td>
                    <td style={{ padding: 4, minWidth: 120 }}>
                      <input style={cellStyle} list="fb-formations" value={p.formation} onChange={e => setPlay(i, 'formation', e.target.value)} /></td>
                    <td style={{ padding: 4, width: 56 }}><input style={cellStyle} value={p.personnel} onChange={e => setPlay(i, 'personnel', e.target.value)} placeholder="11" /></td>
                    <td style={{ padding: 4, width: 100 }}>
                      <input style={cellStyle} list="fb-playtypes" value={p.play_type} onChange={e => setPlay(i, 'play_type', e.target.value)} /></td>
                    <td style={{ padding: 4, minWidth: 120 }}><input style={cellStyle} value={p.run_concept} onChange={e => setPlay(i, 'run_concept', e.target.value)} placeholder="Inside Zone" /></td>
                    <td style={{ padding: 4, minWidth: 120 }}><input style={cellStyle} value={p.pass_concept} onChange={e => setPlay(i, 'pass_concept', e.target.value)} placeholder="Four Verticals" /></td>
                    <td style={{ padding: 4, width: 52 }}><input style={cellStyle} value={p.yards_gained} onChange={e => setPlay(i, 'yards_gained', e.target.value)} /></td>
                    <td style={{ padding: 4, width: 100 }}><input style={cellStyle} value={p.result} onChange={e => setPlay(i, 'result', e.target.value)} placeholder="gain / TD" /></td>
                    <td style={{ padding: 4, minWidth: 100 }}><input style={cellStyle} value={p.coverage} onChange={e => setPlay(i, 'coverage', e.target.value)} placeholder="Cover 3" /></td>
                    <td style={{ padding: 4, minWidth: 90 }}><input style={cellStyle} value={p.blitz} onChange={e => setPlay(i, 'blitz', e.target.value)} placeholder="Edge L" /></td>
                    <td style={{ padding: 4, width: 40, textAlign: 'center' }}><input type="checkbox" checked={p.motion} onChange={e => setPlay(i, 'motion', e.target.checked)} /></td>
                    <td style={{ padding: 4, width: 36 }}>
                      <button onClick={() => setPlays(ps => ps.filter((_, idx) => idx !== i))} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text3)' }}><Trash2 size={15} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <datalist id="fb-formations">{FORMATIONS.map(f => <option key={f} value={f} />)}</datalist>
            <datalist id="fb-playtypes">{PLAY_TYPES.map(f => <option key={f} value={f} />)}</datalist>
            <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
              <button onClick={() => setPlays(ps => [...ps, blankPlay(ps[ps.length - 1]?.side || 'offense')])} className="btn-green" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <Plus size={14} /> Add Play
              </button>
              <button onClick={() => setPlays(ps => [...ps, ...Array.from({ length: 5 }, () => blankPlay(ps[ps.length - 1]?.side || 'offense'))])} className="btn-green" style={{ opacity: 0.85 }}>
                +5 Rows
              </button>
            </div>
          </div>

          {/* Hudl CSV paste */}
          <div className="card" style={{ marginBottom: 18 }}>
            <button onClick={() => setCsvOpen(o => !o)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text)', display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, padding: 0 }}>
              {csvOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />} <ClipboardPaste size={15} /> Import Hudl CSV Play Log <span style={{ color: 'var(--text3)', fontWeight: 400, fontSize: 12 }}>(optional - paste an export, columns auto-mapped, ODK sets the side)</span>
            </button>
            {csvOpen && (
              <div style={{ marginTop: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <span style={{ fontSize: 12, color: 'var(--text3)' }}>If there is no ODK column, treat rows as:</span>
                  <select className="input" style={{ width: 160 }} value={defaultSide} onChange={e => setDefaultSide(e.target.value as any)}>
                    {SIDES.map(s => <option key={s} value={s}>{s === 'special_teams' ? 'special teams' : s}</option>)}
                  </select>
                </div>
                <textarea
                  className="input" style={{ minHeight: 150, fontFamily: 'var(--font-dm-mono, monospace)', fontSize: 12 }}
                  value={csvText} onChange={e => setCsvText(e.target.value)}
                  placeholder={'ODK,GN,DN,DIST,YARD LN,FORM,PLAY TYPE,GN/LS,COVERAGE,BLITZ\nO,1,1,10,OWN 35,Shotgun,run,6,,\nO,1,3,9,OWN 44,Empty,pass,12,,\nD,2,2,7,OPP 30,Trips Rt,,4,Cover 3,Edge L'}
                />
                <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 6 }}>
                  Recognized: ODK, DN, DIST, YARD LN, FORM, PERSONNEL, PLAY TYPE, GN/LS, DEF FRONT, COVERAGE, BLITZ, QTR, GAME. Unmatched columns are ignored.
                </div>
              </div>
            )}
          </div>

          {/* Live gate warnings (honest confidence, before submit) */}
          {warnings.length > 0 && (
            <div className="card" style={{ marginBottom: 18, borderColor: 'rgba(201,168,76,0.4)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, marginBottom: 8, color: 'var(--gold)' }}>
                <ShieldCheck size={16} /> Validation Preview
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: 'var(--text2)' }}>
                {warnings.map((w, i) => <li key={i} style={{ marginBottom: 4 }}>{w}</li>)}
              </ul>
            </div>
          )}

          {error && (
            <div style={{ background: 'var(--redl)', border: '1px solid rgba(224,112,112,0.3)', color: 'var(--red)', borderRadius: 8, padding: '10px 14px', marginBottom: 14, fontSize: 13 }}>{error}</div>
          )}

          <button onClick={generate} disabled={busy} className="btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, opacity: busy ? 0.7 : 1 }}>
            {busy ? <><Loader2 size={16} className="animate-spin" /> Generating Report…</> : <><Upload size={16} /> Generate Scouting Report</>}
          </button>
          <p style={{ fontSize: 11, color: 'var(--text3)', marginTop: 10 }}>
            Runs 7 checks-and-balances gates, then builds the installable game plan: featured explosive threats, coverage
            answers, protection slides, and special-teams alerts - each with a sample size and confidence tier.
          </p>
        </div>
      </main>
    </div>
  )
}
