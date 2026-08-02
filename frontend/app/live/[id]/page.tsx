'use client'
/**
 * Live Game Play Logger, the sideline logger (Features 2-8).
 * Mobile-first, one-handed, high-contrast. Auto-saves every play immediately.
 * Consumes only existing CoachLenz CSS tokens; no global styles are modified.
 */
import { useEffect, useState, useCallback, useMemo, type CSSProperties } from 'react'
import { useRouter, useParams } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { SPORT_META } from '@/lib/sports'
import {
  FB_FORMATIONS, FB_PLAY_TYPES, FB_RUN_CATEGORIES, FLAG_RUSH_TYPES, FB_PASS_RESULTS, FB_OUTCOMES,
  DEF_FRONTS, DEF_COVERAGES, OPP_FORMATIONS, OPP_PLAY_TYPES, DEF_RESULTS, DEF_OUTCOMES,
  ST_UNITS, ST_RESULTS, BB_BALL_ENTRY, BB_PRIMARY_ACTION, BB_SHOT_RESULT, BB_TURNOVER_TYPE,
  BB_POSS_RESULT, BB_DEF_SET, BB_OPP_ACTION, BB_DEF_RESULT, BB_SPECIAL, BB_INTENDED,
  type TermSystem,
} from '@/components/live/fields'
import { TapGroup, GapSelector, RushLaneSelector, RouteTree, ShotZoneCourt } from '@/components/live/Selectors'
import { Zap, Loader2, Undo2, FileBarChart, ClipboardList, Flag, Trash2, X, ChevronDown } from 'lucide-react'

type Cur = Record<string, any>
type Play = { event_id?: string; _pending?: boolean; [k: string]: any }
type Config = {
  sport: string; team_name?: string; terminology_system?: TermSystem; custom_routes?: string[]
  league_format?: string; our_roster?: { jersey: string; name?: string }[]
  opponent_roster?: { jersey: string; name?: string }[]
}

const lbl: CSSProperties = { fontSize: 11, color: 'var(--text3)', fontWeight: 700, letterSpacing: '0.05em', marginBottom: 6, display: 'block', textTransform: 'uppercase' }
const input: CSSProperties = { width: '100%', background: 'var(--bg3)', border: '1px solid var(--border2)', borderRadius: 8, color: 'var(--text)', padding: '10px 12px', fontSize: 15, minHeight: 44 }
const card: CSSProperties = { background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: 14, marginBottom: 12 }

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div style={{ marginBottom: 12 }}><span style={lbl}>{label}</span>{children}</div>
}
function Jersey({ label, value, onChange }: { label: string; value?: string; onChange: (v: string) => void }) {
  return (
    <label style={{ display: 'inline-flex', flexDirection: 'column', gap: 4 }}>
      <span style={lbl}>{label}</span>
      <input style={{ ...input, width: 84, textAlign: 'center', fontSize: 18, fontWeight: 700 }}
        inputMode="numeric" value={value || ''} onChange={e => onChange(e.target.value)} placeholder="#" />
    </label>
  )
}

// field position helpers (football), mirrors the existing scout logger
const toAbs = (spot: string): number | null => {
  const m = (spot || '').trim().toUpperCase().match(/^(OWN|OPP)?\s*(\d{1,2})$/)
  if (!m) return null
  const yl = Number(m[2])
  if (m[1] === 'OPP') return 100 - yl
  return yl
}
const toSpot = (abs: number): string => {
  const a = Math.max(1, Math.min(99, abs))
  return a === 50 ? '50' : a < 50 ? `OWN ${a}` : `OPP ${100 - a}`
}
const mmssToSec = (s?: string): number | null => {
  const m = (s || '').match(/^(\d{1,2}):(\d{2})$/)
  return m ? Number(m[1]) * 60 + Number(m[2]) : null
}

export default function LoggerPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const params = useParams()
  const sessionId = String(params.id)

  const [config, setConfig] = useState<Config | null>(null)
  const [opponent, setOpponent] = useState('')
  const [plays, setPlays] = useState<Play[]>([])
  const [mode, setMode] = useState<'us' | 'them' | 'st'>('us')
  const [period, setPeriod] = useState('1')          // quarter or half
  const [scoreUs, setScoreUs] = useState('0')
  const [scoreThem, setScoreThem] = useState('0')
  const [clock, setClock] = useState('')
  const [cur, setCur] = useState<Cur>({ down: '1', distance: '10', field_position: '' })
  const [quick, setQuick] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [filterSide, setFilterSide] = useState('all')
  const [editing, setEditing] = useState<string | null>(null)
  const [reportScope, setReportScope] = useState('full')

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])

  useEffect(() => {
    if (!user) return
    api.get(`/live/session/${sessionId}`).then(r => {
      setConfig(r.data.config); setOpponent(r.data.opponent || 'Opponent'); setPlays(r.data.plays || [])
    }).catch(e => setError(e?.response?.data?.detail || 'Could not load this game session.'))
  }, [user, sessionId])

  const sport = config?.sport || 'football'
  const isFB = sport === 'football' || sport === 'flag_football'
  const isFlag = sport === 'flag_football'
  const isBB = sport === 'basketball'
  const term: TermSystem = (config?.terminology_system as TermSystem) || 'gap_letters'
  const lateGame = isBB && (() => { const s = mmssToSec(clock); return s !== null && s < 120 })()
  // Numeric current period (OT -> 5 for football, 3 for basketball) for logging + report scope.
  const periodNum = period === 'OT' ? (isBB ? 3 : 5) : (Number(period) || 1)

  const set = (k: string, v: any) => setCur(c => ({ ...c, [k]: v }))
  const roster = (opp: boolean) => (opp ? config?.opponent_roster : config?.our_roster) || []

  const buildPlay = (): Play => {
    const possession = mode === 'them' ? 'them' : 'us'
    const p: Play = {
      possession,
      side: mode === 'st' ? 'special_teams' : undefined,
      play_number: plays.length + 1,
      time_clock: clock || undefined,
      time_seconds: mmssToSec(clock) ?? undefined,
      score_us: Number(scoreUs) || 0,
      score_them: Number(scoreThem) || 0,
      is_quick_log: quick || undefined,
      ...cur,
    }
    if (isBB) { p.half = periodNum; if (lateGame) p.late_game = true }
    else { p.quarter = periodNum }
    // Derive the primary player (-> Event.player, which the tendency engine reads
    // for player-level tendencies) from whichever jersey fits this play.
    if (!p.primary_player_jersey) {
      p.primary_player_jersey = isBB
        ? (mode === 'them' ? p.opp_shooter : (p.shooter_jersey || p.ball_handler_jersey))
        : mode === 'st' ? (p.returner_jersey || p.kicker_jersey)
          : mode === 'them' ? (p.stop_maker_jersey || p.opp_ball_carrier || p.opp_target)
            : (p.ball_carrier_jersey || p.target_jersey)
    }
    // numeric coercions for the columns the engine reads
    if (p.down) p.down = Number(p.down)
    if (p.distance) p.distance = Number(p.distance)
    if (p.yards_gained !== undefined && p.yards_gained !== '') p.yards_gained = Number(p.yards_gained)
    return p
  }

  const advance = () => {
    // football: auto-advance down/distance/field position from yards (offense only)
    if (!isFB || mode !== 'us') return
    const gained = Number(cur.yards_gained) || 0
    const dist = Number(cur.distance) || 10
    const dn = Number(cur.down) || 1
    const changePoss = /turnover|interception|touchdown|downs|punt|safety|fumble/i.test(String(cur.result || '') + String(cur.pass_result || ''))
    const converted = gained >= dist
    let nDown = dn + 1, nDist = Math.max(dist - gained, 1)
    if (changePoss || converted || dn >= 4) { nDown = 1; nDist = 10 }
    let nSpot = cur.field_position
    const abs = toAbs(cur.field_position || '')
    if (abs != null && !changePoss) nSpot = toSpot(abs + gained)
    if (changePoss) nSpot = ''
    setCur({ down: String(nDown), distance: String(nDist), field_position: nSpot })
  }

  const log = useCallback(async () => {
    if (!config) return
    const play = buildPlay()
    setError(''); setOk('')
    const optimistic: Play = { ...play, _pending: true }
    setPlays(ps => [...ps, optimistic])
    const carry = { down: cur.down, distance: cur.distance, field_position: cur.field_position }
    advance()
    try {
      const r = await api.post('/live/plays', { session_id: sessionId, plays: [play] })
      const id = r.data.event_ids?.[0]
      setPlays(ps => ps.map(p => (p === optimistic ? { ...p, event_id: id, _pending: false } : p)))
      setOk('saved'); setTimeout(() => setOk(''), 1200)
    } catch (e: any) {
      setPlays(ps => ps.map(p => (p === optimistic ? { ...p, _pending: false, _failed: true } : p)))
      setError(e?.response?.data?.detail || 'Save failed, the play is kept locally.')
      setCur(carry)  // restore so the coach can retry
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config, cur, mode, period, clock, scoreUs, scoreThem, quick, sessionId, plays.length])

  const undo = async () => {
    const last = plays[plays.length - 1]
    if (!last) return
    setPlays(ps => ps.slice(0, -1))
    if (last.event_id) { try { await api.delete(`/live/play/${last.event_id}`) } catch {} }
  }

  async function flagPlay(p: Play) {
    if (!p.event_id) return
    const next = !p.is_coaching_point
    setPlays(ps => ps.map(x => (x.event_id === p.event_id ? { ...x, is_coaching_point: next } : x)))
    try { await api.post(`/live/play/${p.event_id}/flag`, { is_coaching_point: next }) } catch {}
  }
  async function deletePlay(p: Play) {
    setPlays(ps => ps.filter(x => x.event_id !== p.event_id))
    setEditing(null)
    if (p.event_id) { try { await api.delete(`/live/play/${p.event_id}`) } catch {} }
  }
  async function saveEdit(p: Play, patch: any) {
    setPlays(ps => ps.map(x => (x.event_id === p.event_id ? { ...x, ...patch } : x)))
    if (p.event_id) { try { await api.patch(`/live/play/${p.event_id}`, patch) } catch {} }
    setEditing(null)
  }

  async function report(scope: string) {
    setBusy(true); setError('')
    try {
      const r = await api.post('/live/report', { session_id: sessionId, scope, period: periodNum })
      router.push(`/reports/${r.data.report_id}`)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Could not generate the report.')
      setBusy(false)
    }
  }

  const filtered = useMemo(() => {
    let list = [...plays].reverse()
    if (filterSide !== 'all') list = list.filter(p => (p.side || (p.possession === 'them' ? 'defense' : 'offense')) === filterSide)
    return list
  }, [plays, filterSide])

  if (isLoading || !user || !config) {
    return <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      {error ? <div style={{ color: 'var(--red)' }}>{error}</div> : <Loader2 className="animate-spin" style={{ color: 'var(--gold)' }} />}
    </div>
  }

  const periods = isBB ? ['1', '2', 'OT'] : ['1', '2', '3', '4', 'OT']
  const modeBtn = (m: typeof mode, label: string) => (
    <button onClick={() => setMode(m)} style={{
      flex: 1, minHeight: 46, borderRadius: 8, fontSize: 14, fontWeight: 800, cursor: 'pointer',
      border: '1px solid ' + (mode === m ? 'var(--gold)' : 'var(--border2)'),
      background: mode === m ? 'rgba(201,168,76,0.18)' : 'var(--bg3)',
      color: mode === m ? 'var(--gold)' : 'var(--text2)',
    }}>{label}</button>
  )

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}>
      {/* sticky header */}
      <div style={{ position: 'sticky', top: 0, zIndex: 5, background: 'var(--bg)', borderBottom: '1px solid var(--border2)', padding: '10px 14px' }}>
        <div style={{ maxWidth: 720, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <Zap size={18} style={{ color: 'var(--gold)' }} />
          <b style={{ fontSize: 15 }}>{config.team_name || 'Us'} vs {opponent}</b>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginLeft: 'auto' }}>
            <input style={{ ...input, width: 54, minHeight: 36, textAlign: 'center', padding: 6 }} inputMode="numeric" value={scoreUs} onChange={e => setScoreUs(e.target.value)} />
            <span style={{ color: 'var(--text3)' }}>–</span>
            <input style={{ ...input, width: 54, minHeight: 36, textAlign: 'center', padding: 6 }} inputMode="numeric" value={scoreThem} onChange={e => setScoreThem(e.target.value)} />
          </div>
        </div>
        <div style={{ maxWidth: 720, margin: '6px auto 0', display: 'flex', gap: 8, alignItems: 'center', fontSize: 12, color: 'var(--text3)' }}>
          <span>{plays.length} plays</span>
          {ok && <span style={{ color: 'var(--green3)' }}>✓ {ok}</span>}
          <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6 }}>
            <input style={{ ...input, width: 74, minHeight: 32, textAlign: 'center', padding: 5 }} placeholder="MM:SS" value={clock} onChange={e => setClock(e.target.value)} />
          </span>
        </div>
      </div>

      <div style={{ maxWidth: 720, margin: '0 auto', padding: '12px 14px 40px' }}>
        {error && <div style={{ background: 'var(--redl)', color: 'var(--red)', borderRadius: 8, padding: '10px 14px', marginBottom: 12, fontSize: 13 }}>{error}</div>}

        {/* period + possession */}
        <div style={card}>
          <Field label={isBB ? 'Half' : 'Quarter'}>
            <TapGroup options={periods} value={period} onChange={setPeriod} cols={periods.length} />
          </Field>
          <div style={{ display: 'flex', gap: 8 }}>
            {modeBtn('us', '🏈 Our Ball'.replace('🏈', SPORT_META[sport]?.emoji || '🏈'))}
            {modeBtn('them', 'Their Ball')}
            {!isBB && modeBtn('st', 'Special Teams')}
          </div>
          {lateGame && <div style={{ marginTop: 10, fontSize: 12, color: 'var(--gold)', fontWeight: 700 }}>⏱ Late game (&lt;2:00), flagged automatically</div>}
        </div>

        {/* quick log toggle */}
        <button onClick={() => setQuick(q => !q)} style={{
          width: '100%', minHeight: 42, borderRadius: 8, marginBottom: 12, cursor: 'pointer', fontWeight: 700, fontSize: 13,
          border: '1px solid ' + (quick ? 'var(--gold)' : 'var(--border2)'),
          background: quick ? 'rgba(201,168,76,0.14)' : 'var(--bg2)', color: quick ? 'var(--gold)' : 'var(--text2)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
        }}><ClipboardList size={15} /> {quick ? 'Quick Log ON, minimal taps' : 'Switch to Quick Log'}</button>

        {/* ENTRY PANEL */}
        <div style={card}>
          {quick ? (
            <QuickPanel isBB={isBB} cur={cur} set={set} />
          ) : isBB ? (
            <BasketballPanel mode={mode} cur={cur} set={set} lateGame={lateGame} roster={roster} />
          ) : (
            <FootballPanel mode={mode} sport={sport} isFlag={isFlag} term={term} customRoutes={config.custom_routes} cur={cur} set={set} roster={roster} />
          )}

          <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
            <button onClick={log} style={{
              flex: 1, minHeight: 52, borderRadius: 10, border: 'none', cursor: 'pointer',
              background: 'var(--gold)', color: '#1c1c1c', fontSize: 16, fontWeight: 800,
            }}>Log Play</button>
            <button onClick={undo} disabled={!plays.length} style={{
              minHeight: 52, padding: '0 18px', borderRadius: 10, cursor: 'pointer', fontSize: 14, fontWeight: 700,
              background: 'transparent', border: '1px solid var(--border2)', color: 'var(--text3)',
              display: 'inline-flex', alignItems: 'center', gap: 6, opacity: plays.length ? 1 : 0.5,
            }}><Undo2 size={16} /> Undo</button>
          </div>
        </div>

        {/* REPORTS — scope selector + one Generate button (as of this moment) */}
        <div style={{ ...card, marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 10 }}>
            <span style={lbl}>Report scope</span>
            <span style={{ fontSize: 11, color: 'var(--text3)' }}>as of {isBB ? `Half ${period}` : (period === 'OT' ? 'OT' : `Q${period}`)}</span>
          </div>
          <div style={{ marginBottom: 12 }}>
            <TapGroup
              options={isBB
                ? [{ value: 'full', label: 'Whole game' }, { value: 'this_half', label: 'This half' }]
                : [{ value: 'full', label: 'Whole game' }, { value: 'this_half', label: 'This half' }, { value: 'this_quarter', label: 'This quarter' }]}
              value={reportScope}
              onChange={setReportScope}
              cols={isBB ? 2 : 3}
            />
          </div>
          <button onClick={() => report(reportScope)} disabled={busy || !plays.length} style={{
            width: '100%', minHeight: 50, borderRadius: 10, border: 'none', cursor: 'pointer',
            background: 'var(--green3)', color: '#fff', fontSize: 15, fontWeight: 800,
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            opacity: (busy || !plays.length) ? 0.5 : 1,
          }}>
            {busy ? <Loader2 size={16} className="animate-spin" /> : <FileBarChart size={16} />} Generate Report
          </button>
          <p style={{ fontSize: 11.5, color: 'var(--text3)', margin: '10px 0 0', textAlign: 'center' }}>
            {reportScope === 'this_quarter' ? 'Isolates what is happening now — the adjustment view.'
              : reportScope === 'this_half' ? 'This half only.'
              : 'Everything logged so far.'}
          </p>
        </div>

        {/* REVIEW */}
        {plays.length > 0 && (
          <div style={card}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
              <b style={{ fontSize: 14 }}>Play Log</b>
              <select style={{ ...input, width: 'auto', minHeight: 34, padding: '4px 8px', marginLeft: 'auto', fontSize: 13 }} value={filterSide} onChange={e => setFilterSide(e.target.value)}>
                <option value="all">All</option>
                <option value="offense">Our Offense</option>
                <option value="defense">Our Defense</option>
                <option value="special_teams">Special Teams</option>
              </select>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {filtered.map((p, i) => {
                const rowColor = /touchdown|score|made|2 pts|3 pts/i.test(String(p.result || p.shot_result || p.possession_result || ''))
                  ? 'var(--greenl)'
                  : /turnover|interception|fumble|steal|blocked/i.test(String(p.result || p.pass_result || p.shot_result || ''))
                    ? 'var(--redl)'
                    : /penalty/i.test(String(p.result || '')) ? 'rgba(201,168,76,0.12)' : 'transparent'
                const num = plays.length - i
                const side = p.side || (p.possession === 'them' ? 'defense' : 'offense')
                return (
                  <div key={p.event_id || `t${num}`}>
                    <div onClick={() => setEditing(editing === (p.event_id || `t${num}`) ? null : (p.event_id || `t${num}`))}
                      style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', borderRadius: 8, cursor: 'pointer', background: rowColor, border: '1px solid var(--border2)' }}>
                      <span style={{ color: 'var(--text3)', fontSize: 12, width: 22 }}>{num}</span>
                      <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text3)', width: 30 }}>{side === 'special_teams' ? 'ST' : side === 'defense' ? 'DEF' : 'OFF'}</span>
                      <span style={{ fontSize: 13, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{playSummary(p, isBB)}</span>
                      {p.is_coaching_point && <Flag size={13} style={{ color: 'var(--gold)' }} />}
                      {p._pending && <span style={{ fontSize: 11, color: 'var(--gold)' }}>•</span>}
                      {p._failed && <span style={{ fontSize: 11, color: 'var(--red)' }}>!</span>}
                      <ChevronDown size={14} style={{ color: 'var(--text3)' }} />
                    </div>
                    {editing === (p.event_id || `t${num}`) && (
                      <EditRow p={p} onFlag={() => flagPlay(p)} onDelete={() => deletePlay(p)} onSave={(patch: any) => saveEdit(p, patch)} onClose={() => setEditing(null)} />
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        <div style={{ textAlign: 'center', marginTop: 10 }}>
          <Link href="/live" style={{ fontSize: 13, color: 'var(--text3)' }}>← games</Link>
        </div>
      </div>
    </div>
  )
}

// ── situational row (down/distance/field position) ───────────────────────────
function Situational({ cur, set }: { cur: Cur; set: (k: string, v: any) => void }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 12 }}>
      <Field label="Down"><TapGroup options={['1', '2', '3', '4']} value={String(cur.down || '')} onChange={v => set('down', v)} cols={4} /></Field>
      <Field label="Distance"><input style={input} inputMode="numeric" value={cur.distance || ''} onChange={e => set('distance', e.target.value)} /></Field>
      <Field label="Ball On"><input style={input} value={cur.field_position || ''} onChange={e => set('field_position', e.target.value)} placeholder="OWN 35" /></Field>
    </div>
  )
}

// ── FOOTBALL / FLAG panel ────────────────────────────────────────────────────
function FootballPanel({ mode, sport, isFlag, term, customRoutes, cur, set, roster }: any) {
  if (mode === 'st') {
    return (
      <>
        <Field label="Unit"><TapGroup options={ST_UNITS} value={cur.st_unit} onChange={v => set('st_unit', v)} cols={2} /></Field>
        <div style={{ display: 'flex', gap: 14 }}>
          <Jersey label="Kicker/Punter #" value={cur.kicker_jersey} onChange={v => set('kicker_jersey', v)} />
          <Jersey label="Returner #" value={cur.returner_jersey} onChange={v => set('returner_jersey', v)} />
        </div>
        <Field label="Result"><TapGroup options={ST_RESULTS} value={cur.st_result} onChange={v => { set('st_result', v); set('result', v) }} cols={3} /></Field>
        <Field label="Yards"><input style={input} inputMode="numeric" value={cur.st_yards || ''} onChange={e => set('st_yards', e.target.value)} /></Field>
      </>
    )
  }
  const isDef = mode === 'them'
  const playType = isDef ? cur.opp_play_type : cur.play_type
  const isRun = /run|sneak|scramble/i.test(String(playType || ''))
  const isPass = /pass|rpo/i.test(String(playType || ''))
  return (
    <>
      <Situational cur={cur} set={set} />
      {!isDef ? (
        <>
          <Field label="Formation"><TapGroup options={FB_FORMATIONS} value={cur.formation} onChange={v => set('formation', v)} cols={3} /></Field>
          <Field label="Play type"><TapGroup options={FB_PLAY_TYPES} value={cur.play_type} onChange={v => set('play_type', v)} cols={3} /></Field>
          {isRun && (
            <>
              <Field label={isFlag ? 'Rush lane' : 'Gap / Hole'}>
                {isFlag
                  ? <RushLaneSelector value={cur.rush_lane} onChange={v => set('rush_lane', v)} />
                  : <GapSelector value={cur.run_gap} onChange={v => set('run_gap', v)} system={term} />}
              </Field>
              <div style={{ display: 'flex', gap: 14, marginBottom: 12 }}>
                <Jersey label="Ball carrier #" value={cur.ball_carrier_jersey} onChange={v => set('ball_carrier_jersey', v)} />
              </div>
              <Field label={isFlag ? 'Rush type' : 'Run category'}>
                <TapGroup options={isFlag ? FLAG_RUSH_TYPES : FB_RUN_CATEGORIES} value={cur.run_category} onChange={v => set('run_category', v)} cols={3} />
              </Field>
            </>
          )}
          {isPass && (
            <>
              <div style={{ display: 'flex', gap: 14, marginBottom: 12 }}>
                <Jersey label="Passer #" value={cur.passer_jersey} onChange={v => set('passer_jersey', v)} />
                <Jersey label="Target #" value={cur.target_jersey} onChange={v => set('target_jersey', v)} />
              </div>
              <Field label="Route"><RouteTree value={cur.route} onChange={v => set('route', v)} customRoutes={customRoutes} /></Field>
              <Field label="Pass result"><TapGroup options={FB_PASS_RESULTS} value={cur.pass_result} onChange={v => set('pass_result', v)} cols={3} /></Field>
            </>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 10 }}>
            <Field label="Yards"><input style={input} inputMode="numeric" value={cur.yards_gained ?? ''} onChange={e => set('yards_gained', e.target.value)} /></Field>
            <Field label="Outcome"><TapGroup options={FB_OUTCOMES} value={cur.result} onChange={v => set('result', v)} cols={3} /></Field>
          </div>
        </>
      ) : (
        <>
          <Field label="Our front"><TapGroup options={DEF_FRONTS} value={cur.defensive_front} onChange={v => set('defensive_front', v)} cols={4} /></Field>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <Field label={isFlag ? 'Pass rush' : 'Blitz'}><TapGroup options={['Yes', 'No']} value={cur.blitz} onChange={v => set('blitz', v)} cols={2} /></Field>
            <Field label="Coverage"><TapGroup options={DEF_COVERAGES} value={cur.coverage} onChange={v => set('coverage', v)} cols={2} /></Field>
          </div>
          <Field label="Opp formation"><TapGroup options={OPP_FORMATIONS} value={cur.opp_formation} onChange={v => set('opp_formation', v)} cols={3} /></Field>
          <Field label="Opp play type"><TapGroup options={OPP_PLAY_TYPES} value={cur.opp_play_type} onChange={v => set('opp_play_type', v)} cols={4} /></Field>
          {isRun && (
            <>
              <Field label={isFlag ? 'Opp rush lane' : 'Opp gap / hole'}>
                {isFlag ? <RushLaneSelector value={cur.opp_run_gap} onChange={v => set('opp_run_gap', v)} />
                  : <GapSelector value={cur.opp_run_gap} onChange={v => set('opp_run_gap', v)} system={term} />}
              </Field>
              <div style={{ marginTop: 12 }}>
                <Jersey label="Opp ball carrier #" value={cur.opp_ball_carrier} onChange={v => set('opp_ball_carrier', v)} />
              </div>
              <Field label={isFlag ? 'Opp rush type' : 'Opp run concept'}>
                <TapGroup options={isFlag ? FLAG_RUSH_TYPES : FB_RUN_CATEGORIES} value={cur.opp_run_concept} onChange={v => set('opp_run_concept', v)} cols={3} />
              </Field>
            </>
          )}
          {isPass && (
            <>
              <div style={{ display: 'flex', gap: 14, marginBottom: 12 }}>
                <Jersey label="Opp QB #" value={cur.opp_passer_jersey} onChange={v => set('opp_passer_jersey', v)} />
                <Jersey label="Opp target #" value={cur.opp_target} onChange={v => set('opp_target', v)} />
              </div>
              <Field label="Opp route"><RouteTree value={cur.opp_route} onChange={v => set('opp_route', v)} customRoutes={customRoutes} /></Field>
            </>
          )}
          <div style={{ display: 'flex', gap: 14, marginBottom: 12 }}>
            <Jersey label="Stop by #" value={cur.stop_maker_jersey} onChange={v => set('stop_maker_jersey', v)} />
          </div>
          <Field label="Result"><TapGroup options={DEF_RESULTS} value={cur.result} onChange={v => set('result', v)} cols={3} /></Field>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 10 }}>
            <Field label="Yards allowed"><input style={input} inputMode="numeric" value={cur.yards_gained ?? ''} onChange={e => set('yards_gained', e.target.value)} /></Field>
            <Field label="Outcome"><TapGroup options={DEF_OUTCOMES} value={cur.opp_outcome} onChange={v => set('opp_outcome', v)} cols={2} /></Field>
          </div>
        </>
      )}
    </>
  )
}

// ── BASKETBALL panel ─────────────────────────────────────────────────────────
function BasketballPanel({ mode, cur, set, lateGame, roster }: any) {
  const isDef = mode === 'them'
  return (
    <>
      {!isDef ? (
        <>
          <div style={{ display: 'flex', gap: 14, marginBottom: 12 }}>
            <Jersey label="Ball handler #" value={cur.ball_handler_jersey} onChange={v => set('ball_handler_jersey', v)} />
            <Jersey label="Shooter #" value={cur.shooter_jersey} onChange={v => set('shooter_jersey', v)} />
          </div>
          <Field label="Ball entry"><TapGroup options={BB_BALL_ENTRY} value={cur.ball_entry} onChange={v => set('ball_entry', v)} cols={3} /></Field>
          <Field label="Primary action"><TapGroup options={BB_PRIMARY_ACTION} value={cur.primary_action} onChange={v => set('primary_action', v)} cols={3} /></Field>
          <Field label="Shot zone (tap the court)"><ShotZoneCourt value={cur.shot_zone} onChange={v => set('shot_zone', v)} onPoint={p => { set('shot_x', p.x); set('shot_y', p.y) }} /></Field>
          <Field label="Shot result"><TapGroup options={BB_SHOT_RESULT} value={cur.shot_result} onChange={v => { set('shot_result', v); set('result', v) }} cols={3} /></Field>
          {/turnover/i.test(String(cur.shot_result || '')) && (
            <Field label="Turnover type"><TapGroup options={BB_TURNOVER_TYPE} value={cur.turnover_type} onChange={v => set('turnover_type', v)} cols={3} /></Field>
          )}
          <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
            <TapGroup options={[{ value: 'oreb', label: 'Off. Rebound' }]} value={cur.offensive_rebound ? 'oreb' : ''} onChange={() => set('offensive_rebound', !cur.offensive_rebound)} cols={1} />
          </div>
          <Field label="Possession result"><TapGroup options={BB_POSS_RESULT} value={cur.possession_result} onChange={v => set('possession_result', v)} cols={3} /></Field>
          {lateGame && <Field label="Intended outcome"><TapGroup options={BB_INTENDED} value={cur.intended_outcome} onChange={v => set('intended_outcome', v)} cols={4} /></Field>}
        </>
      ) : (
        <>
          <Field label="Our defensive set"><TapGroup options={BB_DEF_SET} value={cur.defensive_set} onChange={v => set('defensive_set', v)} cols={2} /></Field>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <Field label="Pressure"><TapGroup options={['Yes', 'No']} value={cur.pressure_applied} onChange={v => set('pressure_applied', v)} cols={2} /></Field>
            <Field label="Help D"><TapGroup options={['Yes', 'No']} value={cur.help_defense} onChange={v => set('help_defense', v)} cols={2} /></Field>
          </div>
          <div style={{ display: 'flex', gap: 14, marginBottom: 12 }}>
            <Jersey label="Opp handler #" value={cur.opp_ball_handler} onChange={v => set('opp_ball_handler', v)} />
            <Jersey label="Opp shooter #" value={cur.opp_shooter} onChange={v => set('opp_shooter', v)} />
          </div>
          <Field label="Opp primary action"><TapGroup options={BB_OPP_ACTION} value={cur.opp_primary_action} onChange={v => set('opp_primary_action', v)} cols={3} /></Field>
          <Field label="Shot zone allowed (tap the court)"><ShotZoneCourt value={cur.shot_zone_allowed} onChange={v => set('shot_zone_allowed', v)} onPoint={p => { set('shot_x', p.x); set('shot_y', p.y) }} /></Field>
          <Field label="Result"><TapGroup options={BB_DEF_RESULT} value={cur.result} onChange={v => set('result', v)} cols={3} /></Field>
          <div style={{ display: 'flex', gap: 10 }}>
            <TapGroup options={[{ value: 'dreb', label: 'Def. Rebound' }]} value={cur.defensive_rebound ? 'dreb' : ''} onChange={() => set('defensive_rebound', !cur.defensive_rebound)} cols={1} />
          </div>
        </>
      )}
    </>
  )
}

// ── QUICK LOG panel ──────────────────────────────────────────────────────────
function QuickPanel({ isBB, cur, set }: any) {
  return (
    <>
      <Field label="Play type"><TapGroup options={isBB ? ['Shot', 'Turnover', 'Foul'] : ['Run', 'Pass', 'Special Teams']} value={cur.play_type} onChange={v => set('play_type', v)} cols={3} /></Field>
      <Field label="Result"><TapGroup options={['Positive', 'Negative', 'Turnover', 'Score']} value={cur.result} onChange={v => set('result', v)} cols={4} /></Field>
      <Field label={isBB ? 'Points' : 'Yards'}><input style={input} inputMode="numeric" value={cur.yards_gained ?? ''} onChange={e => set('yards_gained', e.target.value)} /></Field>
      <div style={{ fontSize: 12, color: 'var(--text3)' }}>Quick entries are flagged incomplete, tap them in the Play Log to finish during dead-ball time.</div>
    </>
  )
}

// ── inline edit row ──────────────────────────────────────────────────────────
function EditRow({ p, onFlag, onDelete, onSave, onClose }: any) {
  const [yards, setYards] = useState(String(p.yards_gained ?? ''))
  const [result, setResult] = useState(String(p.result ?? ''))
  const [note, setNote] = useState(String(p.note ?? ''))
  const [player, setPlayer] = useState(String(p.player ?? ''))
  return (
    <div style={{ ...card, marginTop: 6, marginBottom: 6, background: 'var(--bg3)' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <Field label="Yards"><input style={input} inputMode="numeric" value={yards} onChange={e => setYards(e.target.value)} /></Field>
        <Field label="Player #"><input style={input} inputMode="numeric" value={player} onChange={e => setPlayer(e.target.value)} /></Field>
      </div>
      <Field label="Result"><input style={input} value={result} onChange={e => setResult(e.target.value)} /></Field>
      <Field label="Note (coaching point)"><input style={input} maxLength={60} value={note} onChange={e => setNote(e.target.value)} placeholder="Max 60 chars" /></Field>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button onClick={() => onSave({ yards_gained: yards === '' ? null : Number(yards), result, note, primary_player_jersey: player || null })}
          style={{ flex: 1, minHeight: 44, borderRadius: 8, border: 'none', background: 'var(--gold)', color: '#1c1c1c', fontWeight: 800, cursor: 'pointer' }}>Save</button>
        <button onClick={onFlag} style={{ minHeight: 44, padding: '0 14px', borderRadius: 8, cursor: 'pointer', fontWeight: 700, border: '1px solid var(--gold)', background: p.is_coaching_point ? 'rgba(201,168,76,0.2)' : 'transparent', color: 'var(--gold)', display: 'inline-flex', alignItems: 'center', gap: 6 }}><Flag size={14} /> {p.is_coaching_point ? 'Unflag' : 'Coaching Point'}</button>
        <button onClick={onDelete} style={{ minHeight: 44, padding: '0 14px', borderRadius: 8, cursor: 'pointer', fontWeight: 700, border: '1px solid var(--border2)', background: 'transparent', color: 'var(--red)', display: 'inline-flex', alignItems: 'center', gap: 6 }}><Trash2 size={14} /> Delete</button>
        <button onClick={onClose} style={{ minHeight: 44, width: 44, borderRadius: 8, cursor: 'pointer', border: '1px solid var(--border2)', background: 'transparent', color: 'var(--text3)' }}><X size={14} /></button>
      </div>
    </div>
  )
}

// ── one-line play summary for the review list ────────────────────────────────
function playSummary(p: Play, isBB: boolean): string {
  const parts: string[] = []
  if (!isBB) {
    if (p.down) parts.push(`${p.down}&${p.distance ?? ''}`)
    parts.push(p.play_type || p.opp_play_type || p.st_unit || 'play')
    if (p.route || p.opp_route) parts.push(String(p.route || p.opp_route))
    if (p.run_category) parts.push(String(p.run_category))
    if (p.yards_gained !== undefined && p.yards_gained !== '') parts.push(`${p.yards_gained} yd`)
  } else {
    parts.push(p.ball_entry || p.opp_primary_action || p.primary_action || 'poss')
    if (p.shot_zone || p.shot_zone_allowed) parts.push(String(p.shot_zone || p.shot_zone_allowed))
    if (p.possession_result || p.shot_result) parts.push(String(p.possession_result || p.shot_result))
  }
  const jersey = p.player || p.ball_carrier_jersey || p.shooter_jersey || p.target_jersey
  if (jersey) parts.push(`#${jersey}`)
  if (p.result && !parts.includes(p.result)) parts.push(String(p.result))
  return parts.filter(Boolean).join(' · ')
}
