'use client'
import { useEffect, useRef, useState, useCallback, Fragment, type RefObject } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { ChevronLeft, Tag, Play, Pause, Trash2, Clock, FileText, Loader2, CheckCircle, AlertCircle, Zap, Pencil, Check, X, Activity, TrendingUp, Users, Film, SkipForward, SkipBack } from 'lucide-react'
import Link from 'next/link'

// ── Types ──────────────────────────────────────────────────────────────────
interface AgentLogEntry {
  id: string
  agent_name: string
  agent_role: string | null
  phase: string | null
  action: string
  reason: string | null
  confidence: number | null
  level: string
  detail: Record<string, any>
  created_at: string | null
}

interface GameDetail {
  id: string
  title: string
  sport: string
  opponent: string | null
  status: string
  download_url: string | null
  duration_seconds: number | null
  is_trial_game: boolean
}

interface TaggedEvent {
  id: string
  event_type: string
  side?: string
  time_seconds: number | null
  down: number | null
  distance: number | null
  formation: string | null
  play_type: string | null
  defensive_front?: string | null
  coverage?: string | null
  blitz?: string | null
  result: string | null
  yards_gained: number | null
  personnel: string | null
  motion: boolean
  player?: string | null
  // auto_detected/confidence are set by the vision engine; basketball scheme and
  // shot fields (offensive_set, shot_zone, press_type, ...) also live here.
  extra_data?: { auto_detected?: boolean; confidence?: number; [k: string]: any }
}

// ── Helpers ────────────────────────────────────────────────────────────────
function fmtTime(secs: number | null): string {
  if (secs == null) return '--'
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

const FORMATIONS = ['I-Form', 'Shotgun', 'Pistol', 'Singleback', 'Wildcat', 'Empty', 'Trips', 'Bunch', 'Pro Set', 'Other']
const PLAY_TYPES = ['Run', 'Pass', 'Screen', 'Draw', 'Option', 'RPO', 'QB Sneak', 'Punt', 'Kickoff', 'Field Goal', 'PAT', 'Other']
const RESULTS = ['Gain', 'Loss', 'Incomplete', 'Touchdown', 'Interception', 'Fumble', 'Sack', 'Penalty', 'First Down', 'Turnover on Downs', 'Punt', 'Made', 'Missed']
const PERSONNEL = ['11', '12', '21', '22', '10', '20', '13', '00']
// Defensive options
const FRONTS = ['4-3', '3-4', '4-2-5', '3-3-5', '4-4', '5-2', 'Bear', 'Nickel', 'Dime', 'Goal Line', 'Other']
const COVERAGES = ['Cover 0', 'Cover 1', 'Cover 2', 'Cover 3', 'Cover 4', 'Cover 6', 'Man', 'Zone', 'Tampa 2', 'Other']
const BLITZES = ['None', 'Edge', 'A-Gap', 'B-Gap', 'Corner', 'Safety', 'Zone Blitz', 'Double A', 'Other']
// Special teams options
const ST_UNITS = ['Punt', 'Punt Return', 'Kickoff', 'Kick Return', 'Field Goal', 'PAT', 'Onside Kick', 'Fake', 'Block Attempt']
const ST_RESULTS = ['Made', 'Missed', 'Good', 'Blocked', 'Returned', 'Touchback', 'Fair Catch', 'Downed', 'Out of Bounds', 'Muffed', 'Fumble', 'Touchdown', 'Fake Success', 'Fake Stopped']

// ── Status Banner ─────────────────────────────────────────────────────────
function StatusBanner({ status }: { status: string }) {
  if (status === 'ready' || status === 'analyzing') return null
  const processing = ['queued', 'downloading', 'processing'].includes(status)
  return (
    <div style={{
      background: processing ? 'rgba(201,168,76,0.12)' : 'rgba(224,112,112,0.12)',
      border: `1px solid ${processing ? 'rgba(201,168,76,0.3)' : 'rgba(224,112,112,0.3)'}`,
      borderRadius: 6, padding: '10px 16px', marginBottom: 16,
      display: 'flex', alignItems: 'center', gap: 10, fontSize: 13,
      color: processing ? '#C9A84C' : '#e07070',
    }}>
      {processing
        ? <><Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} /> Film is {status} — video will appear when ready.</>
        : <><AlertCircle size={15} /> Processing failed: {status}</>
      }
    </div>
  )
}

// ── Agent Activity Panel (UATP live transparency) ──────────────────────────
function confColor(level: string): string {
  if (level === 'error') return '#e07070'
  if (level === 'escalation') return '#e0a050'
  if (level === 'warn') return '#d4b94c'
  if (level === 'success') return '#2d8c40'
  return '#7a9cc9'
}

function confBand(c: number | null): string {
  if (c == null) return ''
  if (c >= 0.8) return 'high'
  if (c >= 0.65) return 'medium'
  return 'low'
}

function AgentActivityPanel({ entries, live }: { entries: AgentLogEntry[]; live: boolean }) {
  const scrollRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [entries.length])

  if (!entries.length) return null
  const identity = entries[0]

  return (
    <div style={{
      marginBottom: 12, background: 'rgba(255,255,255,0.02)',
      border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6, overflow: 'hidden',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px',
        borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: 11,
      }}>
        <Activity size={13} style={{ color: '#C9A84C', ...(live ? { animation: 'pulseDot 1.4s ease-in-out infinite' } : {}) }} />
        <span style={{ color: '#f8f6f0', fontWeight: 700, letterSpacing: '0.04em' }}>
          {identity.agent_name} ACTIVITY
        </span>
        {identity.agent_role && (
          <span style={{ color: '#7a7a6e' }}>· {identity.agent_role}</span>
        )}
        {live && <span style={{ marginLeft: 'auto', color: '#2d8c40', fontWeight: 600 }}>● LIVE</span>}
      </div>
      <div ref={scrollRef} style={{ maxHeight: 190, overflowY: 'auto', padding: '6px 0' }}>
        {entries.map(e => (
          <div key={e.id} style={{ display: 'flex', gap: 9, padding: '5px 14px', fontSize: 12, alignItems: 'baseline' }}>
            <span style={{ color: confColor(e.level), fontSize: 9, marginTop: 1, flexShrink: 0 }}>●</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ color: '#e8e4d8' }}>{e.action}</div>
              {e.reason && <div style={{ color: '#7a7a6e', fontSize: 11, marginTop: 1 }}>{e.reason}</div>}
            </div>
            {e.confidence != null && (
              <span style={{
                flexShrink: 0, fontSize: 10, fontWeight: 600, color: confColor(e.confidence >= 0.65 ? 'success' : 'escalation'),
              }}>
                {Math.round(e.confidence * 100)}% {confBand(e.confidence)}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Tagging Form ──────────────────────────────────────────────────────────
function TagForm({
  currentTime,
  onSave,
  saving,
  side,
  setSide,
  opponent,
}: {
  currentTime: number
  onSave: (data: Partial<TaggedEvent>) => Promise<void>
  saving: boolean
  side: 'offense' | 'defense' | 'special_teams'
  setSide: (s: 'offense' | 'defense' | 'special_teams') => void
  opponent: string | null
}) {
  const [down, setDown] = useState<number | ''>('')
  const [distance, setDistance] = useState<number | ''>('')
  const [formation, setFormation] = useState('')
  const [playType, setPlayType] = useState('')
  const [personnel, setPersonnel] = useState('')
  const [motion, setMotion] = useState(false)
  const [front, setFront] = useState('')
  const [coverage, setCoverage] = useState('')
  const [blitz, setBlitz] = useState('')
  const [stUnit, setStUnit] = useState('')
  const [result, setResult] = useState('')
  const [yards, setYards] = useState<number | ''>('')

  const reset = () => {
    setDown(''); setDistance(''); setFormation(''); setPlayType(''); setPersonnel(''); setMotion(false)
    setFront(''); setCoverage(''); setBlitz(''); setStUnit(''); setResult(''); setYards('')
  }

  const handleSave = async () => {
    const common = {
      event_type: 'play',
      side,
      time_seconds: currentTime,
      down: down === '' ? undefined : Number(down),
      distance: distance === '' ? undefined : Number(distance),
      result: result || undefined,
      yards_gained: yards === '' ? undefined : Number(yards),
    }
    if (side === 'offense') {
      await onSave({ ...common, formation: formation || undefined, play_type: playType || undefined, personnel: personnel || undefined, motion })
    } else if (side === 'defense') {
      await onSave({ ...common, defensive_front: front || undefined, coverage: coverage || undefined, blitz: blitz || undefined })
    } else {
      // special teams: store the unit in play_type, optional formation
      await onSave({ ...common, play_type: stUnit || undefined, formation: formation || undefined })
    }
    reset()
  }

  const sel = (val: string, set: (v: string) => void, options: string[]) => (
    <select value={val} onChange={e => set(e.target.value)} className="input" style={{ fontSize: 12, padding: '6px 10px', height: 36 }}>
      <option value="">—</option>
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  )
  // Free-entry field: preset formations/fronts/coverages as suggestions, but a
  // coach can type an unorthodox one — it saves and flows into the AI report.
  const selFree = (val: string, set: (v: string) => void, listId: string, options: string[]) => (
    <>
      <input list={listId} value={val} onChange={e => set(e.target.value)} placeholder="pick or type your own"
        className="input" style={{ fontSize: 12, padding: '6px 10px', height: 36, width: '100%' }} />
      <datalist id={listId}>{options.map(o => <option key={o} value={o} />)}</datalist>
    </>
  )
  const lbl = (t: string) => <div style={{ fontSize: 10, color: '#7a7a6e', marginBottom: 4, letterSpacing: '0.08em' }}>{t}</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Scouting context */}
      {opponent && (
        <div style={{ fontSize: 11, color: '#7a7a6e' }}>
          Scouting <span style={{ color: '#f8f6f0', fontWeight: 600 }}>{opponent}</span> — tag what they do on each side of the ball.
        </div>
      )}

      {/* Offense / Defense / Special Teams toggle */}
      <div style={{ display: 'flex', background: 'rgba(255,255,255,0.05)', borderRadius: 6, padding: 3, gap: 2 }}>
        {([
          { k: 'offense', label: 'Offense', bg: '#C9A84C', fg: '#1c1c1c' },
          { k: 'defense', label: 'Defense', bg: '#1a5c2a', fg: '#f8f6f0' },
          { k: 'special_teams', label: 'Spec. Teams', bg: '#3d5a80', fg: '#f8f6f0' },
        ] as const).map(s => (
          <button
            key={s.k}
            onClick={() => setSide(s.k)}
            style={{
              flex: 1, padding: '8px 0', fontSize: 11, fontWeight: 700, cursor: 'pointer',
              borderRadius: 4, border: 'none', textTransform: 'uppercase', letterSpacing: '0.03em',
              background: side === s.k ? s.bg : 'transparent',
              color: side === s.k ? s.fg : '#7a7a6e',
              transition: 'all 0.12s',
            }}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Timestamp */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(201,168,76,0.08)', border: '1px solid rgba(201,168,76,0.2)', borderRadius: 4, padding: '6px 12px' }}>
        <Clock size={13} style={{ color: '#C9A84C' }} />
        <span style={{ fontFamily: 'var(--font-dm-mono)', fontSize: 13, color: '#C9A84C' }}>{fmtTime(currentTime)}</span>
        <span style={{ fontSize: 11, color: '#7a7a6e', marginLeft: 4 }}>current timestamp</span>
      </div>

      {/* Down & Distance (both sides) */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <div>
          {lbl('DOWN')}
          <div style={{ display: 'flex', gap: 4 }}>
            {[1, 2, 3, 4].map(d => (
              <button key={d} onClick={() => setDown(down === d ? '' : d)}
                style={{ flex: 1, height: 32, borderRadius: 3, fontSize: 13, fontWeight: 600, cursor: 'pointer',
                  background: down === d ? '#C9A84C' : 'rgba(255,255,255,0.05)', color: down === d ? '#1c1c1c' : '#f8f6f0',
                  border: down === d ? 'none' : '1px solid rgba(255,255,255,0.1)' }}>{d}</button>
            ))}
          </div>
        </div>
        <div>
          {lbl('DISTANCE')}
          <input type="number" min={0} max={99} placeholder="yds" value={distance}
            onChange={e => setDistance(e.target.value === '' ? '' : Number(e.target.value))}
            className="input" style={{ fontSize: 13, padding: '6px 10px', height: 36, width: '100%' }} />
        </div>
      </div>

      {side === 'offense' ? (
        <>
          <div>{lbl('FORMATION')}{selFree(formation, setFormation, 'dlf-off-form', FORMATIONS)}</div>
          <div>{lbl('PLAY TYPE')}{sel(playType, setPlayType, PLAY_TYPES)}</div>
          <div>
            {lbl('PERSONNEL')}
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              {PERSONNEL.map(p => (
                <button key={p} onClick={() => setPersonnel(personnel === p ? '' : p)}
                  style={{ padding: '4px 10px', borderRadius: 3, fontSize: 12, cursor: 'pointer',
                    background: personnel === p ? 'rgba(26,92,42,0.5)' : 'rgba(255,255,255,0.05)',
                    color: personnel === p ? '#2d8c40' : '#ede9df',
                    border: personnel === p ? '1px solid #2d8c40' : '1px solid rgba(255,255,255,0.08)',
                    fontFamily: 'var(--font-dm-mono)' }}>{p}</button>
              ))}
            </div>
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
            <div onClick={() => setMotion(!motion)} style={{ width: 36, height: 20, borderRadius: 10, position: 'relative', cursor: 'pointer',
              background: motion ? '#1a5c2a' : 'rgba(255,255,255,0.1)', border: motion ? '1px solid #2d8c40' : '1px solid rgba(255,255,255,0.15)' }}>
              <div style={{ position: 'absolute', top: 2, left: motion ? 16 : 2, width: 14, height: 14, borderRadius: '50%',
                background: motion ? '#C9A84C' : '#7a7a6e', transition: 'left 0.15s' }} />
            </div>
            <span style={{ color: motion ? '#f8f6f0' : '#7a7a6e' }}>Motion</span>
          </label>
        </>
      ) : side === 'defense' ? (
        <>
          <div>{lbl('FRONT')}{selFree(front, setFront, 'dlf-def-front', FRONTS)}</div>
          <div>{lbl('COVERAGE')}{selFree(coverage, setCoverage, 'dlf-def-cov', COVERAGES)}</div>
          <div>{lbl('BLITZ')}{sel(blitz, setBlitz, BLITZES)}</div>
        </>
      ) : (
        <>
          <div>{lbl('UNIT / PLAY')}{sel(stUnit, setStUnit, ST_UNITS)}</div>
          <div>{lbl('FORMATION (optional)')}{sel(formation, setFormation, FORMATIONS)}</div>
        </>
      )}

      {/* Result & Yards (all phases) */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px', gap: 8 }}>
        <div>{lbl('RESULT')}{sel(result, setResult, side === 'special_teams' ? ST_RESULTS : RESULTS)}</div>
        <div>
          {lbl('YDS')}
          <input type="number" placeholder="0" value={yards}
            onChange={e => setYards(e.target.value === '' ? '' : Number(e.target.value))}
            className="input" style={{ fontSize: 13, padding: '6px 10px', height: 36, width: '100%' }} />
        </div>
      </div>

      <button onClick={handleSave} disabled={saving} className="btn-primary"
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: 4,
          background: side === 'defense' ? '#1a5c2a' : side === 'special_teams' ? '#3d5a80' : undefined,
          color: side === 'offense' ? undefined : '#f8f6f0' }}>
        {saving ? <><Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Saving...</>
          : <><Tag size={14} /> TAG {side === 'offense' ? 'OFFENSE' : side === 'defense' ? 'DEFENSE' : 'SPECIAL TEAMS'} PLAY</>}
      </button>
    </div>
  )
}

// ── Basketball Tagging Form ─────────────────────────────────────────────────
// Basketball has NO special teams. Sides are Offense / Defense / Special
// Situations (inbounds, press break, last-second). Every tag writes an event the
// scout engine already reads: shots (zone/type/result/origin), turnovers,
// deflections, and special_situation rows.
const BB_ZONES = [
  'Restricted Area', 'Paint Non-RA', 'Mid-Range Left', 'Mid-Range Right', 'Mid-Range Center',
  'Left Corner 3', 'Right Corner 3', 'Above-the-Break 3 Left', 'Above-the-Break 3 Right', 'Above-the-Break 3 Center',
]
const BB_THREE = new Set(['Left Corner 3', 'Right Corner 3', 'Above-the-Break 3 Left', 'Above-the-Break 3 Right', 'Above-the-Break 3 Center'])
const BB_ORIGINS = ['half_court', 'transition', 'set', 'pnr', 'broken']
const BB_TURNOVERS = ['bad_pass', 'live_ball_steal', 'travel', 'shot_clock', 'out_of_bounds', 'charge', 'double_dribble', 'offensive_foul']
const BB_DEFL = ['tipped_pass', 'contested_catch', 'redirected_dribble']
const BB_SITUATIONS = ['BLOB', 'SLOB', 'press_break', 'last_second', 'end_of_quarter']
const BB_SIT_RESULTS = ['made', 'missed', 'reset', 'turnover']
// Scheme-level tags (persist across a stretch of plays). 'Other' reveals a text
// box so an unorthodox call gets named and lands in the AI report verbatim.
const BB_OFFENSIVE_SETS = ['5-out motion', '4-out 1-in', '3-out 2-in', 'Horns', 'Flex', 'Princeton', 'Dribble-drive', 'Pick & Roll (primary)', 'Isolation', 'Post-up', 'Transition / early offense', 'Other']
const BB_DEFENSES = ['Man-to-man', '2-3 zone', '1-3-1 zone', '3-2 zone', 'Matchup zone', 'Junk (box-and-1 / triangle-2)', 'Full-court press', 'Half-court trap', 'Other']
const BB_PRESSES = ['1-2-1-1 zone press', '2-2-1 zone press', 'Full-court man', 'Run-and-jump', 'Half-court trap (1-3-1 / 1-2-2)', 'Diamond press', 'Other']
const BB_PRESS_BREAKS = ['Dribble up the middle', 'Long pass over the top', 'Middle-man reversal', 'Guard-to-guard release', '1-4 spread break', '2-1-2 break', 'Other']
// Legal HS jersey numbers use only digits 0-5 (refs signal them by hand).
const bbLegalJersey = (n: string) => { const s = (n || '').trim(); return s !== '' && /^[0-5]{1,2}$/.test(s) }

function BasketballTagForm({ currentTime, onSave, saving, opponent }: {
  currentTime: number
  onSave: (data: any) => Promise<void>
  saving: boolean
  opponent: string | null
}) {
  const [bside, setBside] = useState<'offense' | 'defense' | 'special'>('offense')
  const [jersey, setJersey] = useState('')
  const [quarter, setQuarter] = useState<number | ''>('')
  // offense
  const [offAction, setOffAction] = useState<'shot' | 'turnover'>('shot')
  const [zone, setZone] = useState('Restricted Area')
  const [made, setMade] = useState(false)
  const [origin, setOrigin] = useState('half_court')
  const [toType, setToType] = useState('')
  // defense
  const [defAction, setDefAction] = useState<'deflection' | 'steal' | 'block' | 'rebound'>('deflection')
  const [deflType, setDeflType] = useState('')
  const [possChange, setPossChange] = useState(false)
  // special situations
  const [sitType, setSitType] = useState('BLOB')
  const [formation, setFormation] = useState('')
  const [action, setAction] = useState('')
  const [target, setTarget] = useState('')
  const [sitResult, setSitResult] = useState('made')
  const [lateClose, setLateClose] = useState(false)
  // scheme-level tags (persist across plays; 'Other' -> free text into the report)
  const [offSet, setOffSet] = useState(''); const [offSetOther, setOffSetOther] = useState('')
  const [pressBreak, setPressBreak] = useState(''); const [pressBreakOther, setPressBreakOther] = useState('')
  const [defScheme, setDefScheme] = useState(''); const [defSchemeOther, setDefSchemeOther] = useState('')
  const [pressType, setPressType] = useState(''); const [pressTypeOther, setPressTypeOther] = useState('')

  const reset = () => {
    setJersey(''); setMade(false); setToType(''); setDeflType(''); setPossChange(false)
    setFormation(''); setAction(''); setTarget(''); setLateClose(false)
  }

  const jerseyBad = jersey.trim() !== '' && !bbLegalJersey(jersey)

  const handleSave = async () => {
    const q = quarter === '' ? undefined : Number(quarter)
    const j = jersey.trim() || undefined
    // 'Other' resolves to the typed text so an unorthodox call is named in the report.
    const resolve = (v: string, other: string) => (v === 'Other' ? (other.trim() || undefined) : (v || undefined))
    const offScheme = { offensive_set: resolve(offSet, offSetOther), press_break_action: resolve(pressBreak, pressBreakOther) }
    const defSchemeData = { defensive_scheme: resolve(defScheme, defSchemeOther), press_type: resolve(pressType, pressTypeOther) }
    let data: any
    if (bside === 'offense') {
      if (offAction === 'shot') {
        data = { event_type: 'shot', side: 'offense', time_seconds: currentTime, result: made ? 'made' : 'missed', player: j,
          extra_data: { primary_player_jersey: j, shot_zone: zone, shot_type: BB_THREE.has(zone) ? '3pt' : '2pt', possession_origin: origin, quarter: q, ...offScheme } }
      } else {
        data = { event_type: 'turnover', side: 'offense', time_seconds: currentTime, player: j,
          extra_data: { primary_player_jersey: j, turnover_type: toType || undefined, quarter: q, ...offScheme } }
      }
    } else if (bside === 'defense') {
      if (defAction === 'deflection') {
        data = { event_type: 'deflection', side: 'defense', time_seconds: currentTime, result: possChange ? 'possession_change' : undefined, player: j,
          extra_data: { primary_player_jersey: j, deflection_type: deflType || undefined, resulted_in_possession_change: possChange, quarter: q, ...defSchemeData } }
      } else {
        data = { event_type: defAction, side: 'defense', time_seconds: currentTime, player: j,
          extra_data: { primary_player_jersey: j, quarter: q, ...defSchemeData } }
      }
    } else {
      data = { event_type: 'special_situation', side: 'offense', time_seconds: currentTime, result: sitResult, player: target.trim() || undefined,
        extra_data: { situation_type: sitType, formation: formation || undefined, primary_action: action || undefined, target: target.trim() || undefined, result: sitResult, late_and_close: lateClose, quarter: q } }
    }
    await onSave(data)
    reset()
  }

  const lbl = (t: string) => <div style={{ fontSize: 10, color: '#7a7a6e', marginBottom: 4, letterSpacing: '0.08em' }}>{t}</div>
  const sel = (val: string, set: (v: string) => void, options: string[], placeholder = '—') => (
    <select value={val} onChange={e => set(e.target.value)} className="input" style={{ fontSize: 12, padding: '6px 10px', height: 36 }}>
      <option value="">{placeholder}</option>
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  )
  const pill = (active: boolean, label: string, onClick: () => void, color = '#C9A84C') => (
    <button onClick={onClick} style={{ flex: 1, padding: '7px 0', fontSize: 12, fontWeight: 700, cursor: 'pointer', borderRadius: 4,
      border: active ? 'none' : '1px solid rgba(255,255,255,0.1)', background: active ? color : 'transparent', color: active ? '#1c1c1c' : '#f8f6f0' }}>{label}</button>
  )
  // A scheme dropdown that reveals a text box when 'Other' is chosen. The typed
  // description is what lands in the report. Scheme tags persist across plays.
  const schemeField = (label: string, val: string, setVal: (v: string) => void, otherVal: string, setOther: (v: string) => void, options: string[], placeholder = '—') => (
    <div>
      {lbl(label)}
      {sel(val, setVal, options, placeholder)}
      {val === 'Other' && (
        <input value={otherVal} onChange={e => setOther(e.target.value)} placeholder="Name it — this goes in the report"
          className="input" style={{ fontSize: 12, padding: '6px 10px', height: 34, width: '100%', marginTop: 6, border: '1px solid #7a5c1e' }} />
      )}
    </div>
  )

  const SIDE_META = { offense: { bg: '#C9A84C', fg: '#1c1c1c' }, defense: { bg: '#1a5c2a', fg: '#f8f6f0' }, special: { bg: '#7a5c1e', fg: '#f8f6f0' } } as const

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {opponent && (
        <div style={{ fontSize: 11, color: '#7a7a6e' }}>
          Scouting <span style={{ color: '#f8f6f0', fontWeight: 600 }}>{opponent}</span> — tag shots, turnovers, deflections, and their inbound / press / last-second sets.
        </div>
      )}

      {/* Offense / Defense / Special Situations toggle (NO special teams in basketball) */}
      <div style={{ display: 'flex', background: 'rgba(255,255,255,0.05)', borderRadius: 6, padding: 3, gap: 2 }}>
        {([
          { k: 'offense', label: 'Offense', bg: '#C9A84C', fg: '#1c1c1c' },
          { k: 'defense', label: 'Defense', bg: '#1a5c2a', fg: '#f8f6f0' },
          { k: 'special', label: 'Special Sit.', bg: '#7a5c1e', fg: '#f8f6f0' },
        ] as const).map(s => (
          <button key={s.k} onClick={() => setBside(s.k)}
            style={{ flex: 1, padding: '8px 0', fontSize: 11, fontWeight: 700, cursor: 'pointer', borderRadius: 4, border: 'none',
              textTransform: 'uppercase', letterSpacing: '0.03em', background: bside === s.k ? s.bg : 'transparent', color: bside === s.k ? s.fg : '#7a7a6e' }}>
            {s.label}
          </button>
        ))}
      </div>

      {/* Timestamp */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(201,168,76,0.08)', border: '1px solid rgba(201,168,76,0.2)', borderRadius: 4, padding: '6px 12px' }}>
        <Clock size={13} style={{ color: '#C9A84C' }} />
        <span style={{ fontFamily: 'var(--font-dm-mono)', fontSize: 13, color: '#C9A84C' }}>{fmtTime(currentTime)}</span>
        <span style={{ fontSize: 11, color: '#7a7a6e', marginLeft: 4 }}>current timestamp</span>
      </div>

      {/* Jersey (# 0-5 rule) + Quarter — common to offense & defense */}
      {bside !== 'special' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px', gap: 8 }}>
          <div>
            {lbl('JERSEY #')}
            <input value={jersey} onChange={e => setJersey(e.target.value)} placeholder="0-5 only"
              className="input" style={{ fontSize: 13, padding: '6px 10px', height: 36, width: '100%', border: jerseyBad ? '1px solid #b45c5c' : undefined }} />
            {jerseyBad && <div style={{ fontSize: 10, color: '#e07070', marginTop: 3 }}>Not a legal HS number (digits 0-5 only).</div>}
          </div>
          <div>{lbl('QTR')}<input type="number" min={1} max={8} value={quarter} onChange={e => setQuarter(e.target.value === '' ? '' : Number(e.target.value))} className="input" style={{ fontSize: 13, padding: '6px 10px', height: 36, width: '100%' }} /></div>
        </div>
      )}

      {bside === 'offense' ? (
        <>
          <div style={{ display: 'flex', gap: 6 }}>{pill(offAction === 'shot', 'Shot', () => setOffAction('shot'))}{pill(offAction === 'turnover', 'Turnover', () => setOffAction('turnover'), '#b45c5c')}</div>
          {offAction === 'shot' ? (
            <>
              <div>{lbl('SHOT ZONE')}{sel(zone, setZone, BB_ZONES)}<div style={{ fontSize: 10, color: '#7a7a6e', marginTop: 3 }}>{BB_THREE.has(zone) ? '3-point' : '2-point'}</div></div>
              <div>{lbl('ORIGIN')}{sel(origin, setOrigin, BB_ORIGINS)}</div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={made} onChange={e => setMade(e.target.checked)} /><span style={{ color: made ? '#2d8c40' : '#7a7a6e', fontWeight: 600 }}>{made ? 'MADE' : 'Missed'}</span>
              </label>
            </>
          ) : (
            <div>{lbl('TURNOVER TYPE')}{sel(toType, setToType, BB_TURNOVERS)}</div>
          )}
          {schemeField('OFFENSIVE SET', offSet, setOffSet, offSetOther, setOffSetOther, BB_OFFENSIVE_SETS)}
          {schemeField('PRESS BREAK (if breaking a press)', pressBreak, setPressBreak, pressBreakOther, setPressBreakOther, BB_PRESS_BREAKS)}
        </>
      ) : bside === 'defense' ? (
        <>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {(['deflection', 'steal', 'block', 'rebound'] as const).map(a => (
              <button key={a} onClick={() => setDefAction(a)} style={{ flex: '1 0 45%', padding: '6px 0', fontSize: 12, fontWeight: 700, cursor: 'pointer', borderRadius: 4,
                border: defAction === a ? 'none' : '1px solid rgba(255,255,255,0.1)', background: defAction === a ? '#1a5c2a' : 'transparent', color: defAction === a ? '#f8f6f0' : '#7a7a6e', textTransform: 'capitalize' }}>{a}</button>
            ))}
          </div>
          {defAction === 'deflection' && (
            <>
              <div>{lbl('DEFLECTION TYPE')}{sel(deflType, setDeflType, BB_DEFL)}</div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={possChange} onChange={e => setPossChange(e.target.checked)} /><span style={{ color: possChange ? '#2d8c40' : '#7a7a6e' }}>Flipped possession</span>
              </label>
            </>
          )}
          {schemeField('DEFENSE', defScheme, setDefScheme, defSchemeOther, setDefSchemeOther, BB_DEFENSES)}
          {schemeField('PRESS (if pressing)', pressType, setPressType, pressTypeOther, setPressTypeOther, BB_PRESSES)}
        </>
      ) : (
        <>
          <div>{lbl('SITUATION')}{sel(sitType, setSitType, BB_SITUATIONS)}</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px', gap: 8 }}>
            <div>{lbl('FORMATION')}<input value={formation} onChange={e => setFormation(e.target.value)} placeholder="e.g. Box, Stack" className="input" style={{ fontSize: 13, padding: '6px 10px', height: 36, width: '100%' }} /></div>
            <div>{lbl('QTR')}<input type="number" min={1} max={8} value={quarter} onChange={e => setQuarter(e.target.value === '' ? '' : Number(e.target.value))} className="input" style={{ fontSize: 13, padding: '6px 10px', height: 36, width: '100%' }} /></div>
          </div>
          <div>{lbl('PRIMARY ACTION')}<input value={action} onChange={e => setAction(e.target.value)} placeholder="e.g. screen the screener" className="input" style={{ fontSize: 13, padding: '6px 10px', height: 36, width: '100%' }} /></div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div>{lbl('TARGET #')}<input value={target} onChange={e => setTarget(e.target.value)} placeholder="#" className="input" style={{ fontSize: 13, padding: '6px 10px', height: 36, width: '100%' }} /></div>
            <div>{lbl('RESULT')}{sel(sitResult, setSitResult, BB_SIT_RESULTS)}</div>
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
            <input type="checkbox" checked={lateClose} onChange={e => setLateClose(e.target.checked)} /><span style={{ color: lateClose ? '#C9A84C' : '#7a7a6e' }}>Late &amp; close (final 30s, within 3)</span>
          </label>
        </>
      )}

      <button onClick={handleSave} disabled={saving} className="btn-primary"
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: 4, background: SIDE_META[bside].bg, color: SIDE_META[bside].fg }}>
        {saving ? <><Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Saving...</>
          : <><Tag size={14} /> TAG {bside === 'offense' ? (offAction === 'shot' ? 'SHOT' : 'TURNOVER') : bside === 'defense' ? defAction.toUpperCase() : 'SPECIAL SITUATION'}</>}
      </button>
    </div>
  )
}

// ── Play Log ──────────────────────────────────────────────────────────────
function PlayLog({
  events,
  onDelete,
  onSeek,
  onUpdate,
  sport,
}: {
  events: TaggedEvent[]
  onDelete: (id: string) => void
  onSeek: (t: number) => void
  onUpdate: (id: string, data: Partial<TaggedEvent>) => Promise<void>
  sport?: string
}) {
  const isBball = sport === 'basketball'
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState<Partial<TaggedEvent>>({})
  const [filter, setFilter] = useState<'all' | 'offense' | 'defense' | 'special_teams'>('all')
  const [savingId, setSavingId] = useState<string | null>(null)

  const startEdit = (ev: TaggedEvent) => { setEditingId(ev.id); setDraft({ ...ev }) }
  const cancel = () => { setEditingId(null); setDraft({}) }
  const save = async (id: string) => {
    setSavingId(id)
    try { await onUpdate(id, draft); setEditingId(null); setDraft({}) }
    finally { setSavingId(null) }
  }
  const set = (k: keyof TaggedEvent, v: any) => setDraft(d => ({ ...d, [k]: v }))

  const esel = (k: keyof TaggedEvent, options: string[]) => (
    <select value={(draft[k] as string) || ''} onChange={e => set(k, e.target.value || null)}
      className="input" style={{ fontSize: 11, padding: '4px 6px', height: 30, minWidth: 0 }}>
      <option value="">—</option>
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  )
  // Free-entry version of esel for a direct column: preset suggestions PLUS any
  // unorthodox formation/front/coverage the coach types (it flows straight to the report).
  const efree = (k: keyof TaggedEvent, listId: string, options: string[]) => (
    <div style={{ minWidth: 0 }}>
      <input list={listId} value={(draft[k] as string) || ''} onChange={e => set(k, e.target.value || null)}
        className="input" placeholder="—" style={{ fontSize: 11, padding: '4px 6px', height: 30, width: '100%', minWidth: 0 }} />
      <datalist id={listId}>{options.map(o => <option key={o} value={o} />)}</datalist>
    </div>
  )

  // ── extra_data editors (basketball scheme fields live in JSONB extra_data) ──
  // Empty selection is sent as null so the backend MERGE actually clears it.
  const xd = () => (draft.extra_data as any) || {}
  const setX = (k: string, v: any) => setDraft(d => ({ ...d, extra_data: { ...((d.extra_data as any) || {}), [k]: v } }))
  const xv = (k: string) => (xd()[k] ?? '')
  const xsel = (k: string, options: string[]) => (
    <select value={xv(k)} onChange={e => setX(k, e.target.value || null)}
      className="input" style={{ fontSize: 11, padding: '4px 6px', height: 30, minWidth: 0 }}>
      <option value="">—</option>
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  )
  // Datalist-backed field: dropdown of the common calls PLUS free text, so a
  // standard set or an unorthodox one the coach names both save and reach the report.
  const xfree = (k: string, listId: string, options: string[]) => (
    <div style={{ minWidth: 0 }}>
      <input list={listId} value={xv(k)} onChange={e => setX(k, e.target.value || null)}
        className="input" placeholder="—" style={{ fontSize: 11, padding: '4px 6px', height: 30, width: '100%', minWidth: 0 }} />
      <datalist id={listId}>{options.filter(o => o !== 'Other').map(o => <option key={o} value={o} />)}</datalist>
    </div>
  )
  // Jersey lives in BOTH the player column and extra_data — keep them in lockstep.
  const setJersey = (raw: string) => {
    const v = raw.trim() || null
    setDraft(d => ({ ...d, player: v, extra_data: { ...((d.extra_data as any) || {}), primary_player_jersey: v } }))
  }

  if (events.length === 0) {
    return (
      <div style={{ textAlign: 'center', color: '#7a7a6e', padding: '32px 0', fontSize: 13 }}>
        No plays tagged yet. Pause the video and click TAG PLAY.
      </div>
    )
  }

  const shown = filter === 'all' ? events : events.filter(e => (e.side || 'offense') === filter)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {/* Phase filter */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 4 }}>
        {((isBball
          ? [['all', 'All'], ['offense', 'Off'], ['defense', 'Def']]
          : [['all', 'All'], ['offense', 'Off'], ['defense', 'Def'], ['special_teams', 'ST']]) as [('all' | 'offense' | 'defense' | 'special_teams'), string][]).map(([k, label]) => (
          <button key={k} onClick={() => setFilter(k)}
            style={{ flex: 1, padding: '4px 0', fontSize: 10, fontWeight: 600, cursor: 'pointer', borderRadius: 3,
              background: filter === k ? 'rgba(201,168,76,0.2)' : 'rgba(255,255,255,0.04)',
              color: filter === k ? '#C9A84C' : '#7a7a6e', border: 'none', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            {label}
          </button>
        ))}
      </div>

      {shown.map((ev, i) => editingId === ev.id ? (
        // ── Inline editor ──
        <div key={ev.id} style={{ background: 'rgba(201,168,76,0.06)', border: '1px solid rgba(201,168,76,0.25)', borderRadius: 4, padding: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ fontSize: 10, color: '#C9A84C', fontWeight: 700, letterSpacing: '0.06em' }}>EDITING {fmtTime(ev.time_seconds)} · {isBball ? (ev.event_type || 'play').replace('_', ' ').toUpperCase() : (ev.side || 'offense').replace('_', ' ').toUpperCase()}</div>
          {isBball ? (
            // ── Basketball editor: fields depend on what was tagged; scheme calls
            //    (offensive set / defense / press / press break) are always editable
            //    via a dropdown-plus-free-text so unorthodox calls survive edits. ──
            <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 64px', gap: 6 }}>
                <input placeholder="jersey # (0-5)" value={(draft.player as string) ?? (xv('primary_player_jersey') || '')}
                  onChange={e => setJersey(e.target.value)} className="input" style={{ fontSize: 11, padding: '4px 6px', height: 30 }} />
                <input type="number" placeholder="qtr" value={xv('quarter')} onChange={e => setX('quarter', e.target.value === '' ? null : Number(e.target.value))}
                  className="input" style={{ fontSize: 11, padding: '4px 6px', height: 30 }} />
              </div>
              {ev.event_type === 'shot' && (
                <>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>{xsel('shot_zone', BB_ZONES)}{xsel('possession_origin', BB_ORIGINS)}</div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>{esel('result', ['made', 'missed'])}{xsel('shot_type', ['2pt', '3pt'])}</div>
                </>
              )}
              {ev.event_type === 'turnover' && xsel('turnover_type', BB_TURNOVERS)}
              {ev.event_type === 'deflection' && xsel('deflection_type', BB_DEFL)}
              {ev.event_type === 'special_situation' && (
                <>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>{xsel('situation_type', BB_SITUATIONS)}{esel('result', BB_SIT_RESULTS)}</div>
                  <input placeholder="formation (e.g. Box, Stack)" value={xv('formation')} onChange={e => setX('formation', e.target.value || null)} className="input" style={{ fontSize: 11, padding: '4px 6px', height: 30 }} />
                  <input placeholder="primary action" value={xv('primary_action')} onChange={e => setX('primary_action', e.target.value || null)} className="input" style={{ fontSize: 11, padding: '4px 6px', height: 30 }} />
                </>
              )}
              {ev.side === 'defense' ? (
                <>
                  <div style={{ fontSize: 9, color: '#7a7a6e', letterSpacing: '0.06em' }}>DEFENSE SCHEME · PRESS</div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>{xfree('defensive_scheme', 'dl-bb-def', BB_DEFENSES)}{xfree('press_type', 'dl-bb-press', BB_PRESSES)}</div>
                </>
              ) : ev.event_type !== 'special_situation' ? (
                <>
                  <div style={{ fontSize: 9, color: '#7a7a6e', letterSpacing: '0.06em' }}>OFFENSIVE SET · PRESS BREAK</div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>{xfree('offensive_set', 'dl-bb-offset', BB_OFFENSIVE_SETS)}{xfree('press_break_action', 'dl-bb-pbreak', BB_PRESS_BREAKS)}</div>
                </>
              ) : null}
            </>
          ) : (
            <>
              <div style={{ display: 'flex', gap: 6 }}>
                <select value={(draft.side as string) || 'offense'} onChange={e => set('side', e.target.value)} className="input" style={{ fontSize: 11, padding: '4px 6px', height: 30 }}>
                  <option value="offense">Offense</option>
                  <option value="defense">Defense</option>
                  <option value="special_teams">Special Teams</option>
                </select>
                <input type="number" placeholder="down" value={(draft.down as number) ?? ''} onChange={e => set('down', e.target.value === '' ? null : Number(e.target.value))} className="input" style={{ fontSize: 11, padding: '4px 6px', height: 30, width: 56 }} />
                <input type="number" placeholder="dist" value={(draft.distance as number) ?? ''} onChange={e => set('distance', e.target.value === '' ? null : Number(e.target.value))} className="input" style={{ fontSize: 11, padding: '4px 6px', height: 30, width: 56 }} />
              </div>
              {draft.side === 'defense' ? (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
                  {efree('defensive_front', 'dl-fb-front', FRONTS)}{efree('coverage', 'dl-fb-cov', COVERAGES)}{esel('blitz', BLITZES)}
                </div>
              ) : draft.side === 'special_teams' ? (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                  {esel('play_type', ST_UNITS)}{efree('formation', 'dl-fb-stform', FORMATIONS)}
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
                  {efree('formation', 'dl-fb-form', FORMATIONS)}{esel('play_type', PLAY_TYPES)}{esel('personnel', PERSONNEL)}
                </div>
              )}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 70px', gap: 6 }}>
                {esel('result', draft.side === 'special_teams' ? ST_RESULTS : RESULTS)}
                <input type="number" placeholder="yds" value={(draft.yards_gained as number) ?? ''} onChange={e => set('yards_gained', e.target.value === '' ? null : Number(e.target.value))} className="input" style={{ fontSize: 11, padding: '4px 6px', height: 30 }} />
              </div>
            </>
          )}
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={() => save(ev.id)} disabled={savingId === ev.id} className="btn-primary" style={{ flex: 1, height: 32, fontSize: 11, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
              {savingId === ev.id ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Check size={12} />} Save
            </button>
            <button onClick={cancel} className="btn-secondary" style={{ flex: 1, height: 32, fontSize: 11, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
              <X size={12} /> Cancel
            </button>
          </div>
        </div>
      ) : (
        // ── Read-only row ──
        <div key={ev.id} style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'rgba(255,255,255,0.03)', borderRadius: 4, padding: '8px 12px', border: '1px solid rgba(255,255,255,0.05)' }}>
          <span style={{ fontSize: 11, color: '#7a7a6e', width: 24, textAlign: 'right', flexShrink: 0 }}>{i + 1}</span>
          <button onClick={() => ev.time_seconds != null && onSeek(ev.time_seconds)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#C9A84C', padding: 0, fontFamily: 'var(--font-dm-mono)', fontSize: 12, flexShrink: 0 }}>
            {fmtTime(ev.time_seconds)}
          </button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, color: '#f8f6f0', display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
              {(() => {
                const isDef = ev.side === 'defense', isSt = ev.side === 'special_teams'
                const bg = isDef ? 'rgba(26,92,42,0.4)' : isSt ? 'rgba(61,90,128,0.4)' : 'rgba(201,168,76,0.2)'
                const fg = isDef ? '#2d8c40' : isSt ? '#7ea0d0' : '#C9A84C'
                const txt = isDef ? 'DEF' : isSt ? 'ST' : 'OFF'
                return <span style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.08em', padding: '1px 5px', borderRadius: 3, background: bg, color: fg }}>{txt}</span>
              })()}
              {isBball ? (() => {
                const x: any = ev.extra_data || {}
                const et = ev.event_type
                const made = ev.result === 'made'
                const clean = (s: any) => String(s).replace(/_/g, ' ')
                return (
                  <>
                    <span style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.06em', padding: '1px 5px', borderRadius: 3, background: 'rgba(255,255,255,0.06)', color: '#ede9df' }}>{clean(et).toUpperCase()}</span>
                    {et === 'shot' && (
                      <>
                        {x.shot_zone && <span>{x.shot_zone}</span>}
                        {x.shot_type && <span style={{ color: '#7a7a6e' }}>{x.shot_type}</span>}
                        <span style={{ color: made ? '#2d8c40' : '#b45c5c', fontWeight: 600 }}>{made ? 'made' : 'missed'}</span>
                      </>
                    )}
                    {et === 'turnover' && x.turnover_type && <span style={{ color: '#e07070' }}>{clean(x.turnover_type)}</span>}
                    {et === 'deflection' && x.deflection_type && <span style={{ color: '#7ea0d0' }}>{clean(x.deflection_type)}</span>}
                    {et === 'special_situation' && (
                      <>
                        {x.situation_type && <span style={{ color: '#C9A84C' }}>{x.situation_type}</span>}
                        {x.primary_action && <span style={{ color: '#ede9df' }}>{x.primary_action}</span>}
                        {ev.result && <span style={{ color: '#7a7a6e' }}>{clean(ev.result)}</span>}
                      </>
                    )}
                    {x.offensive_set && <span style={{ color: '#7a7a6e', fontStyle: 'italic' }}>{x.offensive_set}</span>}
                    {x.defensive_scheme && <span style={{ color: '#7a7a6e', fontStyle: 'italic' }}>{x.defensive_scheme}</span>}
                    {x.press_type && <span style={{ color: '#e0a060', fontStyle: 'italic' }}>press: {x.press_type}</span>}
                    {x.press_break_action && <span style={{ color: '#7ea0d0', fontStyle: 'italic' }}>break: {x.press_break_action}</span>}
                    {x.quarter != null && x.quarter !== '' && <span style={{ fontSize: 10, color: '#7a7a6e' }}>Q{x.quarter}</span>}
                    {ev.player && <span style={{ fontSize: 10, color: '#7a7a6e' }}>#{ev.player}</span>}
                  </>
                )
              })() : (
                <>
                  {ev.down && <span style={{ color: '#C9A84C', fontWeight: 600 }}>{ev.down}&amp;{ev.distance}</span>}
                  {ev.side === 'defense' ? (
                    <>
                      {ev.defensive_front && <span>{ev.defensive_front}</span>}
                      {ev.coverage && <span style={{ color: '#ede9df' }}>{ev.coverage}</span>}
                      {ev.blitz && ev.blitz !== 'None' && <span style={{ color: '#e07070' }}>{ev.blitz} blitz</span>}
                    </>
                  ) : ev.side === 'special_teams' ? (
                    <>
                      {ev.play_type && <span style={{ color: '#7ea0d0' }}>{ev.play_type}</span>}
                      {ev.formation && <span style={{ color: '#7a7a6e' }}>{ev.formation}</span>}
                    </>
                  ) : (
                    <>
                      {ev.formation && <span>{ev.formation}</span>}
                      {ev.play_type && <span style={{ color: '#ede9df' }}>{ev.play_type}</span>}
                      {ev.motion && <span style={{ fontSize: 10, color: '#7a7a6e', fontStyle: 'italic' }}>motion</span>}
                    </>
                  )}
                  {ev.result && <span style={{ color: ev.result === 'Touchdown' ? '#2d8c40' : ev.result === 'Interception' || ev.result === 'Fumble' ? '#e07070' : '#7a7a6e' }}>{ev.result}</span>}
                  {ev.yards_gained != null && <span style={{ color: '#7a7a6e' }}>{ev.yards_gained > 0 ? '+' : ''}{ev.yards_gained} yds</span>}
                </>
              )}
              {ev.extra_data?.auto_detected && (
                <span style={{ fontSize: 9, color: '#C9A84C', letterSpacing: '0.1em', opacity: 0.7 }}>AI</span>
              )}
            </div>
          </div>
          <button onClick={() => startEdit(ev)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#7a7a6e', padding: 4, flexShrink: 0 }} title="Edit">
            <Pencil size={12} />
          </button>
          <button onClick={() => onDelete(ev.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#7a7a6e', padding: 4, flexShrink: 0 }} title="Delete">
            <Trash2 size={13} />
          </button>
        </div>
      ))}
    </div>
  )
}

// ── Cut-Ups ─────────────────────────────────────────────────────────────────
// Virtual film cut-ups: pick a dimension (concept / formation / down&distance /
// personnel / player / big plays), pick a value, and get a playlist of every
// matching play. Playback drives the EXISTING <video> to each play's window and
// auto-advances — no server-side clipping, works on the film already loaded.
const CLIP_PRE = 4   // seconds of lead-in before the tagged snap
const CLIP_POST = 6  // seconds after
const _ORD = (d: number) => (({ 1: '1st', 2: '2nd', 3: '3rd', 4: '4th' } as Record<number, string>)[d] || `${d}`)

function CutUps({ events, videoRef, sport }: {
  events: TaggedEvent[]
  videoRef: RefObject<HTMLVideoElement | null>
  sport?: string
}) {
  const isBball = sport === 'basketball'
  const DIMS: [string, string][] = isBball
    ? [['zone', 'Shot Zone'], ['set', 'Off Set'], ['def', 'Defense'], ['quarter', 'Quarter'], ['player', 'Player'], ['result', 'Result']]
    : [['concept', 'Concept'], ['formation', 'Formation'], ['dd', 'Down & Dist'], ['personnel', 'Personnel'], ['player', 'Player'], ['impact', 'Big Plays']]
  const [dim, setDim] = useState(DIMS[0][0])
  const [value, setValue] = useState<string | null>(null)
  const [idx, setIdx] = useState(0)
  const [playing, setPlaying] = useState(false)

  const groupValue = (e: TaggedEvent): string | null => {
    const x: any = e.extra_data || {}
    if (isBball) {
      if (dim === 'zone') return x.shot_zone || null
      if (dim === 'set') return x.offensive_set || null
      if (dim === 'def') return x.defensive_scheme || null
      if (dim === 'quarter') return x.quarter != null ? `Q${x.quarter}` : null
      if (dim === 'player') return (e.player != null && `${e.player}` !== '') ? `#${e.player}` : null
      if (dim === 'result') return e.result || null
      return null
    }
    if (dim === 'concept') return x.run_concept || x.pass_concept || null
    if (dim === 'formation') return e.formation || null
    if (dim === 'dd') return e.down != null ? `${_ORD(e.down)} & ${e.distance == null ? '?' : e.distance <= 3 ? 'Short' : e.distance <= 7 ? 'Med' : 'Long'}` : null
    if (dim === 'personnel') return e.personnel || null
    if (dim === 'player') return (e.player != null && `${e.player}` !== '') ? `#${e.player}` : null
    if (dim === 'impact') {
      const y = e.yards_gained
      const res = (e.result || '').toLowerCase()
      if (res.includes('touchdown') || res === 'td') return 'Touchdown'
      const passish = !!x.pass_concept || /pass|screen|rpo/i.test(e.play_type || '')
      if (y != null && y >= (passish ? 15 : 10)) return 'Explosive'
      if ((y != null && y < 0) || res.includes('sack') || res.includes('loss') || res.includes('intercept') || res.includes('fumble')) return 'Negative'
      return null
    }
    return null
  }

  const clipLabel = (e: TaggedEvent): string => {
    const x: any = e.extra_data || {}
    if (isBball) {
      const bits = [x.shot_zone || e.event_type, e.result].filter(Boolean)
      return bits.join(' · ')
    }
    const bits = [e.formation, x.run_concept || x.pass_concept || e.play_type, e.result].filter(Boolean)
    return bits.join(' · ') || 'play'
  }

  const clipable = events.filter(e => e.time_seconds != null)
  const groups = new Map<string, TaggedEvent[]>()
  for (const e of clipable) {
    const v = groupValue(e)
    if (!v) continue
    const arr = groups.get(v)
    if (arr) arr.push(e); else groups.set(v, [e])
  }
  const sortedGroups = [...groups.entries()].sort((a, b) => b[1].length - a[1].length)

  const clips = (value ? (groups.get(value) || []) : [])
    .slice().sort((a, b) => (a.time_seconds || 0) - (b.time_seconds || 0))
    .map(e => ({ ev: e, start: Math.max(0, (e.time_seconds || 0) - CLIP_PRE), end: (e.time_seconds || 0) + CLIP_POST }))

  const stateRef = useRef({ clips, idx })
  stateRef.current = { clips, idx }

  // Auto-advance: when the current clip window ends, jump to the next (or stop).
  useEffect(() => {
    const v = videoRef.current
    if (!v || !playing) return
    const onTime = () => {
      const { clips, idx } = stateRef.current
      const clip = clips[idx]
      if (!clip) return
      if (v.currentTime >= clip.end - 0.05) {
        if (idx + 1 < clips.length) setIdx(idx + 1)
        else { setPlaying(false); v.pause() }
      }
    }
    v.addEventListener('timeupdate', onTime)
    return () => v.removeEventListener('timeupdate', onTime)
  }, [playing, videoRef])

  // Seek to the active clip whenever the index or play state changes.
  useEffect(() => {
    const v = videoRef.current
    if (!v || !playing) return
    const clip = clips[idx]
    if (clip) { v.currentTime = clip.start; v.play().catch(() => {}) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx, playing])

  const selectValue = (val: string) => { setValue(val); setIdx(0); setPlaying(false) }
  const playFrom = (i: number) => {
    setIdx(i); setPlaying(true)
    const v = videoRef.current, clip = clips[i]
    if (v && clip) { v.currentTime = clip.start; v.play().catch(() => {}) }
  }
  const stop = () => { setPlaying(false); videoRef.current?.pause() }

  if (!clipable.length) {
    return (
      <div style={{ textAlign: 'center', color: '#7a7a6e', padding: '32px 0', fontSize: 13 }}>
        No plays with timestamps yet. Tag plays (or run AI detection), then build cut-ups here.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Dimension selector */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {DIMS.map(([k, label]) => (
          <button key={k} onClick={() => { setDim(k); setValue(null); setPlaying(false) }}
            style={{
              padding: '5px 9px', fontSize: 10, fontWeight: 700, cursor: 'pointer', borderRadius: 4, border: 'none',
              letterSpacing: '0.04em', textTransform: 'uppercase',
              background: dim === k ? 'rgba(201,168,76,0.2)' : 'rgba(255,255,255,0.04)',
              color: dim === k ? '#C9A84C' : '#7a7a6e',
            }}>{label}</button>
        ))}
      </div>

      {!value ? (
        // ── Group list ──
        sortedGroups.length ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {sortedGroups.map(([val, evs]) => (
              <button key={val} onClick={() => selectValue(val)}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
                  background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)',
                  borderRadius: 4, padding: '9px 12px', cursor: 'pointer', color: '#ede9df', fontSize: 13,
                }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Film size={13} style={{ color: '#C9A84C' }} />{val}</span>
                <span style={{ fontSize: 11, color: '#7a7a6e' }}>{evs.length} clip{evs.length !== 1 ? 's' : ''}</span>
              </button>
            ))}
          </div>
        ) : (
          <div style={{ fontSize: 12, color: '#7a7a6e', padding: '12px 0' }}>No plays carry this tag yet.</div>
        )
      ) : (
        // ── Playlist for the selected value ──
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button onClick={() => { setValue(null); stop() }} style={{ background: 'none', border: 'none', color: '#7a7a6e', cursor: 'pointer', fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
              <ChevronLeft size={13} /> All
            </button>
            <span style={{ fontSize: 13, fontWeight: 700, color: '#f8f6f0' }}>{value}</span>
            <span style={{ fontSize: 11, color: '#7a7a6e' }}>{clips.length} clip{clips.length !== 1 ? 's' : ''}</span>
          </div>

          {/* Transport */}
          <div style={{ display: 'flex', gap: 6 }}>
            {!playing ? (
              <button onClick={() => playFrom(0)} className="btn-primary" style={{ flex: 1, height: 34, fontSize: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                <Play size={13} /> Play all
              </button>
            ) : (
              <button onClick={stop} className="btn-secondary" style={{ flex: 1, height: 34, fontSize: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                <Pause size={13} /> Pause
              </button>
            )}
            <button onClick={() => playFrom(Math.max(0, idx - 1))} disabled={!playing && idx === 0} className="btn-secondary" style={{ width: 42, height: 34, display: 'flex', alignItems: 'center', justifyContent: 'center' }} title="Previous clip">
              <SkipBack size={13} />
            </button>
            <button onClick={() => playFrom(Math.min(clips.length - 1, idx + 1))} className="btn-secondary" style={{ width: 42, height: 34, display: 'flex', alignItems: 'center', justifyContent: 'center' }} title="Next clip">
              <SkipForward size={13} />
            </button>
          </div>

          {/* Clip list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {clips.map((c, i) => (
              <button key={c.ev.id} onClick={() => playFrom(i)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10, textAlign: 'left',
                  background: playing && i === idx ? 'rgba(201,168,76,0.15)' : 'rgba(255,255,255,0.03)',
                  border: playing && i === idx ? '1px solid rgba(201,168,76,0.4)' : '1px solid rgba(255,255,255,0.05)',
                  borderRadius: 4, padding: '7px 10px', cursor: 'pointer',
                }}>
                <span style={{ fontSize: 11, color: '#7a7a6e', width: 20, flexShrink: 0 }}>{i + 1}</span>
                <span style={{ fontSize: 12, color: '#C9A84C', fontFamily: 'var(--font-dm-mono)', flexShrink: 0 }}>{fmtTime(c.ev.time_seconds)}</span>
                <span style={{ fontSize: 12, color: '#ede9df', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{clipLabel(c.ev)}</span>
                {playing && i === idx && <span style={{ fontSize: 9, color: '#C9A84C', letterSpacing: '0.08em', flexShrink: 0 }}>NOW</span>}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Accuracy Panel ─────────────────────────────────────────────────────────
function PlayersPanel({ gameId }: { gameId: string }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    setLoading(true)
    api.get(`/games/${gameId}/players`).then(r => setData(r.data)).catch(() => setData(null)).finally(() => setLoading(false))
  }, [gameId])

  if (loading) return <div style={{ textAlign: 'center', padding: 24 }}><Loader2 size={20} style={{ color: '#C9A84C', animation: 'spin 1s linear infinite' }} /></div>
  if (!data) return <div style={{ fontSize: 12, color: '#7a7a6e', padding: 8 }}>Could not load players.</div>

  const cov = data.coverage || {}
  const players = data.by_player || []

  if (!data.tracked || !players.length) {
    return (
      <div style={{ fontSize: 12, color: '#ede9df', lineHeight: 1.6 }}>
        <div style={{ fontWeight: 700, color: '#C9A84C', marginBottom: 8 }}>Players by jersey number</div>
        <p style={{ color: '#7a7a6e' }}>{data.note || 'No readable jersey numbers on this film yet.'}</p>
        <p style={{ color: '#7a7a6e', fontSize: 11, marginTop: 8 }}>
          The AI only tags a player when it can actually read the number on the jersey. On a wide press-box angle that is often not possible. Tighter end-zone or sideline film reads far more numbers.
        </p>
      </div>
    )
  }

  return (
    <div style={{ fontSize: 12, color: '#ede9df' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 8 }}>
        <span style={{ fontWeight: 700, color: '#C9A84C' }}>Players by jersey number</span>
        <span style={{ fontSize: 11, color: '#7a7a6e', marginLeft: 'auto' }}>
          {cov.events_with_players} of {cov.total_events} plays had a readable number ({cov.pct}%)
        </span>
      </div>
      <div>
        {players.map((p: any) => (
          <div key={`${p.team}-${p.jersey}`} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 10px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ minWidth: 44, textAlign: 'center' }}>
              <div style={{ fontSize: 20, fontWeight: 800, color: '#f8f6f0', lineHeight: 1 }}>#{p.jersey}</div>
              <div style={{ fontSize: 9, color: p.team === 'defense' ? '#9aa6c9' : '#7fb88a', textTransform: 'uppercase', fontWeight: 700 }}>{p.team || ''}</div>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 11, color: '#b8b8aa' }}>
                {Object.entries(p.roles || {}).slice(0, 4).map(([r, n]: any) => `${r} ×${n}`).join(' · ') || '—'}
              </div>
            </div>
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#C9A84C' }}>{p.appearances}</div>
              <div style={{ fontSize: 9, color: '#7a7a6e' }}>plays{p.as_primary ? ` · ${p.as_primary} as main` : ''}</div>
            </div>
          </div>
        ))}
      </div>
      <p style={{ fontSize: 10, color: '#7a7a6e', marginTop: 10 }}>{data.note}</p>
    </div>
  )
}

function TendenciesPanel({ gameId }: { gameId: string }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    setLoading(true)
    api.get(`/games/${gameId}/tendencies`).then(r => setData(r.data)).catch(() => setData(null)).finally(() => setLoading(false))
  }, [gameId])

  if (loading) return <div style={{ textAlign: 'center', padding: 24 }}><Loader2 size={20} style={{ color: '#C9A84C', animation: 'spin 1s linear infinite' }} /></div>
  if (!data || !data.ready) {
    return <div style={{ fontSize: 12, color: '#7a7a6e', padding: 8 }}>{data?.reason || 'No tendencies yet. Break down the film first.'}</div>
  }

  const off = data.offense || {}
  const deff = data.defense || {}
  const st = data.special_teams || {}
  const rp = off.run_pass_ratio || {}
  const totalOff = off.total_plays || 0

  const Bars = ({ obj, total, color = '#C9A84C' }: { obj: any; total: number; color?: string }) => {
    const entries = Object.entries(obj || {}).slice(0, 6) as [string, number][]
    if (!entries.length) return <div style={{ fontSize: 11, color: '#7a7a6e' }}>—</div>
    const max = Math.max(...entries.map(([, v]) => v), 1)
    return (<div>{entries.map(([k, v]) => (
      <div key={k} style={{ marginBottom: 5 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#b8b8aa' }}>
          <span>{k}</span><span>{v}{total ? ` · ${Math.round(v / total * 100)}%` : ''}</span>
        </div>
        <div style={{ height: 4, background: 'rgba(255,255,255,0.07)', borderRadius: 2, marginTop: 2 }}>
          <div style={{ height: 4, width: `${v / max * 100}%`, background: color, borderRadius: 2 }} />
        </div>
      </div>
    ))}</div>)
  }

  const DOWN_ROWS: [string, string][] = [
    ['first_down', '1st down'], ['second_short', '2nd & short'], ['second_medium', '2nd & med'], ['second_long', '2nd & long'],
    ['third_short', '3rd & short'], ['third_medium', '3rd & med'], ['third_long', '3rd & long'], ['fourth_down', '4th down'],
  ]
  const downRows = DOWN_ROWS.map(([k, label]) => [label, off[k]] as [string, any]).filter(([, d]) => d && d.count > 0)
  const Section = ({ title, children }: { title: string; children: any }) => (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: '#C9A84C', letterSpacing: '0.04em', marginBottom: 6 }}>{title}</div>
      {children}
    </div>
  )
  const stat = (label: string, val: any, suffix = '') => (
    <div><div style={{ fontSize: 18, fontWeight: 700, color: '#f8f6f0' }}>{val}{suffix}</div><div style={{ fontSize: 10, color: '#7a7a6e' }}>{label}</div></div>
  )

  return (
    <div style={{ fontSize: 12, color: '#ede9df' }}>
      {!data.team_colors_set && (
        <div style={{ background: 'rgba(224,168,80,0.1)', border: '1px solid rgba(224,168,80,0.3)', borderRadius: 6, padding: '8px 12px', marginBottom: 12, fontSize: 11, color: '#e0c080' }}>
          Heads up: no team colors set, so these tendencies may mix both teams. Set colors above and re-run for a clean, single-team breakdown.
        </div>
      )}

      <Section title={`Offense — ${totalOff} plays`}>
        <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap' }}>
          {stat('run', rp.run_pct ?? 0, '%')}
          {stat('pass', rp.pass_pct ?? 0, '%')}
          {stat('success rate', off.overall_success_rate ?? 0, '%')}
          {stat('yds / play', off.avg_yards_per_play ?? 0)}
          {stat('yds / run', off.avg_yards_per_run ?? 0)}
          {stat('yds / pass', off.avg_yards_per_pass ?? 0)}
        </div>
      </Section>

      {downRows.length > 0 && (
        <Section title="Run / pass by down & distance">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto auto auto', gap: '3px 10px', fontSize: 11 }}>
            <div style={{ color: '#7a7a6e' }}></div><div style={{ color: '#7a7a6e' }}>plays</div><div style={{ color: '#7a7a6e' }}>run/pass</div><div style={{ color: '#7a7a6e' }}>yds</div>
            {downRows.map(([label, d]) => (
              <Fragment key={label}>
                <div style={{ color: '#e8e4d8' }}>{label}</div>
                <div>{d.count}</div>
                <div><span style={{ color: '#7fb88a' }}>{d.run_pct}%</span> / <span style={{ color: '#d8a86a' }}>{d.pass_pct}%</span></div>
                <div>{d.avg_yards}</div>
              </Fragment>
            ))}
          </div>
        </Section>
      )}

      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 150 }}><Section title="Top formations"><Bars obj={off.top_formations} total={totalOff} /></Section></div>
        <div style={{ flex: 1, minWidth: 150 }}><Section title="Play types"><Bars obj={off.play_type_mix} total={totalOff} color="#7fb88a" /></Section></div>
      </div>

      {off.red_zone && off.red_zone.total > 0 && (
        <Section title={`Red zone — ${off.red_zone.total} plays`}>
          <div style={{ fontSize: 11, color: '#b8b8aa' }}>
            run <b style={{ color: '#f0eee6' }}>{off.red_zone.run_pct}%</b> / pass <b style={{ color: '#f0eee6' }}>{off.red_zone.pass_pct}%</b>
            {off.red_zone.scoring_plays != null && <> · {off.red_zone.scoring_plays} scores</>}
          </div>
        </Section>
      )}

      {(deff.total_plays > 0) && (
        <Section title={`Defense — ${deff.total_plays} plays`}>
          <Bars obj={deff.fronts || deff.top_fronts} total={deff.total_plays} color="#9aa6c9" />
        </Section>
      )}

      {(st.total_plays > 0) && (
        <Section title={`Special teams — ${st.total_plays} plays`}>
          <Bars obj={st.units} total={st.total_plays} color="#c99a6a" />
        </Section>
      )}

      <div style={{ fontSize: 10, color: '#7a7a6e', marginTop: 6, borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 8 }}>
        Confidence: {data.data_confidence?.confidence_band || 'unknown'}. These numbers come straight from the detected plays, no AI write-up needed. Tag plays or set team colors to sharpen them.
      </div>
    </div>
  )
}

function AccuracyPanel({ gameId }: { gameId: string }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    api.get(`/games/${gameId}/accuracy`).then(r => setData(r.data)).catch(() => setData(null)).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [gameId])

  if (loading) return <div style={{ textAlign: 'center', padding: 24 }}><Loader2 size={20} style={{ color: '#C9A84C', animation: 'spin 1s linear infinite' }} /></div>

  if (!data || !data.ready) {
    return (
      <div style={{ fontSize: 12, color: '#ede9df', lineHeight: 1.6 }}>
        <div style={{ fontWeight: 700, color: '#C9A84C', marginBottom: 8 }}>Accuracy Benchmark</div>
        <p style={{ color: '#7a7a6e', marginBottom: 10 }}>{data?.reason || 'Could not load.'}</p>
        <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 6, padding: 10, marginBottom: 10 }}>
          <div>Coach-verified plays: <b style={{ color: '#f8f6f0' }}>{data?.truth_plays ?? 0}</b></div>
          <div>AI plays: <b style={{ color: '#f8f6f0' }}>{data?.ai_plays ?? 0}</b></div>
        </div>
        <p style={{ color: '#7a7a6e', fontSize: 11 }}>
          <b>How it works:</b> Tag this game yourself (the plays you tag yourself), then have the AI break down the film.
          We compare the two and score how accurate the AI is.
        </p>
        <button onClick={load} className="btn-secondary" style={{ marginTop: 10, fontSize: 11, height: 30, width: '100%' }}>Refresh</button>
      </div>
    )
  }

  const big = (label: string, pct: number, hint: string, color: string) => (
    <div style={{ flex: 1, background: 'rgba(255,255,255,0.04)', borderRadius: 6, padding: '10px 8px', textAlign: 'center' }}>
      <div style={{ fontSize: 26, fontWeight: 700, color, fontFamily: 'var(--font-bebas)' }}>{pct}%</div>
      <div style={{ fontSize: 10, color: '#f8f6f0', fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 9, color: '#7a7a6e', marginTop: 2 }}>{hint}</div>
    </div>
  )
  const attrLabel: Record<string, string> = {
    side: 'Phase (O/D/ST)', play_type: 'Play type', down: 'Down', distance: 'Distance',
    formation: 'Formation', defensive_front: 'Front', coverage: 'Coverage', result: 'Result',
  }

  return (
    <div style={{ fontSize: 12, color: '#ede9df', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontWeight: 700, color: '#C9A84C' }}>AI Accuracy vs Your Tags</div>
      <div style={{ display: 'flex', gap: 8 }}>
        {big('Plays Caught', data.recall_pct, `${data.matched}/${data.truth_plays} of yours`, '#2d8c40')}
        {big('How Many Right', data.precision_pct, 'AI plays real', '#C9A84C')}
      </div>
      <div style={{ fontSize: 11, color: '#7a7a6e', lineHeight: 1.6 }}>
        Compared against the <b style={{ color: '#ede9df' }}>{data.truth_plays}</b> plays you tagged.
        AI missed <b style={{ color: data.missed > 0 ? '#e07070' : '#2d8c40' }}>{data.missed}</b> of them
        and had <b style={{ color: data.false_positives > 0 ? '#e0a050' : '#2d8c40' }}>{data.false_positives}</b> extra plays that matched none of yours
        {data.scoped_to_tags && data.window && (
          <> · scored only over the stretch you tagged ({fmtTime(data.window.start)}–{fmtTime(data.window.end)}), so a partial sample is judged fairly</>
        )}.
      </div>
      <div>
        <div style={{ fontSize: 10, color: '#7a7a6e', letterSpacing: '0.08em', marginBottom: 6 }}>ATTRIBUTE ACCURACY (on matched plays)</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {Object.entries(data.attribute_accuracy).map(([k, v]: any) => v.total > 0 && (
            <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
              <span style={{ color: '#ede9df' }}>{attrLabel[k] || k}</span>
              <span style={{ color: v.pct >= 80 ? '#2d8c40' : v.pct >= 50 ? '#C9A84C' : '#e07070', fontWeight: 600 }}>
                {v.pct}% <span style={{ color: '#7a7a6e', fontWeight: 400 }}>({v.agree}/{v.total})</span>
              </span>
            </div>
          ))}
        </div>
      </div>
      <button onClick={load} className="btn-secondary" style={{ fontSize: 11, height: 30 }}>Refresh</button>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────
export default function GamePage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { user, isLoading, fetchMe } = useAuth()
  const videoRef = useRef<HTMLVideoElement>(null)
  const [game, setGame] = useState<GameDetail | null>(null)
  const [events, setEvents] = useState<TaggedEvent[]>([])
  const [currentTime, setCurrentTime] = useState(0)
  const [saving, setSaving] = useState(false)
  const [tab, setTab] = useState<'tag' | 'log' | 'cutups' | 'tendencies' | 'players' | 'accuracy'>('tag')
  const [side, setSide] = useState<'offense' | 'defense' | 'special_teams'>('offense')
  const [reportPending, setReportPending] = useState(false)
  const [reportType, setReportType] = useState<'opponent' | 'self_scout'>('opponent')
  const [toast, setToast] = useState<string | null>(null)
  const [detectStatus, setDetectStatus] = useState<null | {
    game_status: string
    job_status: string | null
    plays_detected: number
    needs_review?: number
    dry_run?: boolean
    error: string | null
  }>(null)
  const [agentLog, setAgentLog] = useState<AgentLogEntry[]>([])
  const [scorecard, setScorecard] = useState<any>(null)
  const [accuracy, setAccuracy] = useState<any>(null)
  const [scoutJersey, setScoutJersey] = useState('')
  const [oppJersey, setOppJersey] = useState('')
  const [jerseySaved, setJerseySaved] = useState(false)
  const detectPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])

  useEffect(() => {
    if (!user || !id) return
    api.get(`/games/${id}`).then(r => { setGame(r.data); setScoutJersey(r.data.scout_jersey || ''); setOppJersey(r.data.opponent_jersey || '') })
    api.get(`/events?game_id=${id}`).then(r => setEvents(r.data)).catch(() => {})
    // Check if there's a running detect job
    api.get(`/games/${id}/auto-detect/status`).then(r => {
      setDetectStatus(r.data)
      if (['queued', 'running'].includes(r.data.job_status) || r.data.game_status === 'analyzing') {
        startDetectPoll()
      }
    }).catch(() => {})
    fetchAgentLog()
    fetchScorecard()
  }, [user, id])

  const fetchAgentLog = async () => {
    try {
      const r = await api.get(`/games/${id}/agent-log`)
      setAgentLog(r.data.entries || [])
    } catch {}
  }

  const fetchScorecard = async () => {
    try { const r = await api.get(`/games/${id}/coverage`); setScorecard(r.data) } catch {}
    try { const r = await api.get(`/games/${id}/accuracy`); setAccuracy(r.data) } catch {}
  }

  const saveJerseys = async () => {
    try {
      await api.patch(`/games/${id}`, { scout_jersey: scoutJersey, opponent_jersey: oppJersey })
      setJerseySaved(true)
      setTimeout(() => setJerseySaved(false), 2500)
      showToast('Saved. Break down the film (or Quick Test) and the report will be on that team.')
    } catch {
      showToast('Could not save team colors')
    }
  }

  const handleRederiveDowns = async () => {
    try {
      const r = await api.post(`/games/${id}/rederive-downs`)
      const ev = await api.get(`/events?game_id=${id}`); setEvents(ev.data)
      fetchScorecard()
      showToast(`Filled ${r.data.fields_filled} down/distance values — ${r.data.down_distance_coverage_pct}% of plays now have down & distance`)
    } catch (e: any) {
      showToast(e?.response?.data?.detail ?? 'Could not fill downs')
    }
  }

  const startDetectPoll = () => {
    if (detectPollRef.current) return
    detectPollRef.current = setInterval(async () => {
      try {
        const r = await api.get(`/games/${id}/auto-detect/status`)
        setDetectStatus(r.data)
        await fetchAgentLog()
        const done = !['queued', 'running'].includes(r.data.job_status ?? '') && r.data.game_status !== 'analyzing'
        if (done) {
          clearInterval(detectPollRef.current!)
          detectPollRef.current = null
          // Reload events
          const evRes = await api.get(`/events?game_id=${id}`)
          setEvents(evRes.data)
          fetchScorecard()
          if (r.data.dry_run) {
            showToast('Preview complete — nothing was saved')
          } else if (r.data.plays_detected > 0) {
            const rv = r.data.needs_review ? ` (${r.data.needs_review} need your eyes)` : ''
            showToast(`${r.data.plays_detected} plays broken down${rv}`)
            setTab('log')
          }
        }
      } catch {}
    }, 4000)
  }

  useEffect(() => () => { if (detectPollRef.current) clearInterval(detectPollRef.current) }, [])

  const handleAutoDetect = async (dryRun = false, mode: 'fast' | 'deep' = 'fast', test = false) => {
    try {
      setAgentLog([])
      const qs = new URLSearchParams()
      if (dryRun) qs.set('dry_run', 'true')
      qs.set('mode', mode)
      if (test) qs.set('test', 'true')
      await api.post(`/games/${id}/auto-detect?${qs.toString()}`)
      const r = await api.get(`/games/${id}/auto-detect/status`)
      setDetectStatus(r.data)
      startDetectPoll()
      showToast(test ? 'Quick test started (first few minutes, pennies)…'
        : dryRun ? 'Preview started (nothing will be saved)…'
        : mode === 'deep' ? 'Deep 3-pass breakdown started…' : 'Film breakdown started…')
    } catch (e: any) {
      showToast(e?.response?.data?.detail ?? 'Could not start the film breakdown')
    }
  }

  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(null), 2500)
  }

  const handleTimeUpdate = useCallback(() => {
    if (videoRef.current) setCurrentTime(videoRef.current.currentTime)
  }, [])

  const handleSaveTag = async (data: Partial<TaggedEvent>) => {
    setSaving(true)
    try {
      const res = await api.post('/events', { game_id: id, ...data })
      const newEvent: TaggedEvent = { id: res.data.id, event_type: 'play', ...data } as TaggedEvent
      setEvents(prev => [...prev, newEvent].sort((a, b) => (a.time_seconds ?? 0) - (b.time_seconds ?? 0)))
      setTab('log')
      showToast('Play tagged')
    } catch (e: any) {
      showToast(e?.response?.data?.detail ?? 'Could not save that play — please try again.')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (eventId: string) => {
    try {
      await api.delete(`/events/${eventId}`)
      setEvents(prev => prev.filter(e => e.id !== eventId))
    } catch {
      showToast('Could not delete that play — please try again.')
    }
  }

  const [deletingFilm, setDeletingFilm] = useState(false)
  const handleDeleteFilm = async () => {
    if (!game) return
    const ok = window.confirm(
      `Delete "${game.title}"?\n\nThis permanently removes the film, every tagged and AI-detected play, and any report built from it. This cannot be undone.`
    )
    if (!ok) return
    setDeletingFilm(true)
    try {
      await api.delete(`/games/${id}`)
      router.push('/games')
    } catch {
      showToast('Could not delete this film — please try again.')
      setDeletingFilm(false)
    }
  }

  const handleUpdate = async (eventId: string, data: Partial<TaggedEvent>) => {
    try {
      const res = await api.patch(`/events/${eventId}`, data)
      setEvents(prev => prev.map(e => e.id === eventId ? { ...e, ...res.data } : e)
        .sort((a, b) => (a.time_seconds ?? 0) - (b.time_seconds ?? 0)))
      showToast('Play updated')
    } catch (e: any) {
      showToast(e?.response?.data?.detail ?? 'Could not update that play — please try again.')
    }
  }

  const handleSeek = (t: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = t
      videoRef.current.play()
    }
    setTab('log')
  }

  const handleGenerateReport = async () => {
    if (!game) return
    setReportPending(true)
    try {
      const res = await api.post('/reports', {
        title: `${game.title} ${reportType === 'self_scout' ? 'Self-Scout' : 'Tendency'} Report`,
        sport: game.sport,
        game_ids: [id],
        report_type: reportType,
      })
      router.push(`/reports/${res.data.id}`)
    } catch {
      showToast('Failed to start report generation')
      setReportPending(false)
    }
  }

  if (!game) {
    return (
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 flex items-center justify-center">
          <Loader2 size={24} style={{ color: '#C9A84C', animation: 'spin 1s linear infinite' }} />
        </main>
      </div>
    )
  }

  return (
    <div className="flex h-screen overflow-hidden" style={{ fontFamily: 'var(--font-dm-sans)' }}>
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)',
          background: '#1a5c2a', color: '#f8f6f0', padding: '10px 20px',
          borderRadius: 6, fontSize: 13, zIndex: 9999,
          display: 'flex', alignItems: 'center', gap: 8,
          boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
        }}>
          <CheckCircle size={14} /> {toast}
        </div>
      )}

      <Sidebar />

      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <div style={{
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          padding: '12px 20px',
          display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0,
        }}>
          <Link href="/games" style={{ color: '#7a7a6e', display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, textDecoration: 'none' }}>
            <ChevronLeft size={15} /> Film Library
          </Link>
          <span style={{ color: 'rgba(255,255,255,0.15)' }}>/</span>
          <span style={{ fontSize: 14, fontWeight: 600, color: '#f8f6f0' }}>{game.title}</span>
          {game.opponent && <span style={{ fontSize: 12, color: '#7a7a6e' }}>vs {game.opponent}</span>}
          {game.status === 'ready'
            ? <span style={{ marginLeft: 'auto', fontSize: 11, color: '#2d8c40', background: 'rgba(45,140,64,0.1)', padding: '3px 10px', borderRadius: 12, border: '1px solid rgba(45,140,64,0.25)' }}>
                <CheckCircle size={10} style={{ display: 'inline', marginRight: 4 }} />READY
              </span>
            : <span style={{ marginLeft: 'auto', fontSize: 11, color: '#C9A84C', background: 'rgba(201,168,76,0.1)', padding: '3px 10px', borderRadius: 12, border: '1px solid rgba(201,168,76,0.2)' }}>
                {game.status.toUpperCase()}
              </span>
          }
          <button
            onClick={handleDeleteFilm}
            disabled={deletingFilm}
            title="Delete film"
            aria-label="Delete film"
            style={{ display: 'flex', alignItems: 'center', gap: 5, background: 'none', border: '1px solid rgba(229,102,102,0.3)', color: '#e56', borderRadius: 8, padding: '4px 10px', fontSize: 12, cursor: deletingFilm ? 'default' : 'pointer', opacity: deletingFilm ? 0.5 : 1 }}
          >
            <Trash2 size={13} /> {deletingFilm ? 'Deleting…' : 'Delete'}
          </button>
        </div>

        {/* Main content: video + sidebar */}
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          {/* LEFT: setup, scorecard & status — the controls, scrollable */}
          <div style={{ width: 440, flexShrink: 0, borderRight: '1px solid rgba(255,255,255,0.06)', display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: '16px 18px' }}>
            <div style={{ flex: 1, overflowY: 'auto' }}>
            <StatusBanner status={game.status} />

            {/* Auto-detect banner */}
            {game.status === 'ready' && (() => {
              const isRunning = detectStatus && (['queued', 'running'].includes(detectStatus.job_status ?? '') || detectStatus.game_status === 'analyzing')
              const isDone = detectStatus && detectStatus.job_status === 'done'
              const isError = detectStatus?.job_status === 'error'
              const neverRun = !detectStatus?.job_status

              if (isRunning) return (
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12,
                  background: 'rgba(201,168,76,0.07)', border: '1px solid rgba(201,168,76,0.2)',
                  borderRadius: 6, padding: '10px 16px', fontSize: 13,
                }}>
                  <Loader2 size={14} style={{ color: '#C9A84C', animation: 'spin 1s linear infinite' }} />
                  <span style={{ color: '#C9A84C', fontWeight: 600 }}>Your film assistant is breaking down the film…</span>
                  {detectStatus.plays_detected > 0 && (
                    <span style={{ color: '#7a7a6e', marginLeft: 4 }}>{detectStatus.plays_detected} found so far</span>
                  )}
                </div>
              )

              if (isDone) return (
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12,
                  background: 'rgba(45,140,64,0.07)', border: '1px solid rgba(45,140,64,0.2)',
                  borderRadius: 6, padding: '10px 16px', fontSize: 13,
                }}>
                  <CheckCircle size={14} style={{ color: '#2d8c40' }} />
                  <span style={{ color: '#2d8c40', fontWeight: 600 }}>
                    {detectStatus.plays_detected} plays broken down
                  </span>
                  <span style={{ color: '#7a7a6e', marginLeft: 4 }}>— review in the Play Log, edit any you need.</span>
                  <button onClick={() => handleAutoDetect(false, 'fast', true)} title="Quick test: first few minutes only, costs pennies. Confirms the breakdown and team colors cheaply." style={{ marginLeft: 'auto', background: 'none', border: '1px solid #44443c', borderRadius: 4, color: '#a8d8b0', fontSize: 11, cursor: 'pointer', padding: '4px 10px', fontWeight: 700 }}>
                    Quick Test
                  </button>
                  <button onClick={() => handleAutoDetect(false, 'fast')} title="Quick single-pass re-run." style={{ background: 'none', border: 'none', color: '#7a7a6e', fontSize: 11, cursor: 'pointer' }}>
                    Re-run Fast
                  </button>
                  <button onClick={() => handleAutoDetect(false, 'deep')} title="Three-pass engine: pre-snap, post-snap, and a final check. Richest read, higher confidence, ~3x cost." style={{ background: '#C9A84C', color: '#1c1c1c', border: 'none', borderRadius: 4, padding: '5px 12px', fontSize: 11, fontWeight: 700, cursor: 'pointer', letterSpacing: '0.04em' }}>
                    DEEP · 3-PASS
                  </button>
                </div>
              )

              if (isError) return (
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12,
                  background: 'rgba(224,112,112,0.07)', border: '1px solid rgba(224,112,112,0.2)',
                  borderRadius: 6, padding: '10px 16px', fontSize: 13,
                }}>
                  <AlertCircle size={14} style={{ color: '#e07070' }} />
                  <span style={{ color: '#e07070' }}>The film breakdown failed. Tag plays manually or </span>
                  <button onClick={() => handleAutoDetect(false, 'fast')} style={{ background: 'none', border: 'none', color: '#C9A84C', fontSize: 13, cursor: 'pointer', padding: 0, textDecoration: 'underline' }}>
                    try again (Fast)
                  </button>
                  <button onClick={() => handleAutoDetect(false, 'deep')} style={{ background: 'none', border: 'none', color: '#C9A84C', fontSize: 13, cursor: 'pointer', padding: 0, textDecoration: 'underline' }}>
                    or Deep · 3-pass
                  </button>
                </div>
              )

              // Never run or idle — show CTA
              return (
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12,
                  background: 'rgba(201,168,76,0.07)', border: '1px solid rgba(201,168,76,0.2)',
                  borderRadius: 6, padding: '10px 16px',
                }}>
                  <Zap size={15} style={{ color: '#C9A84C', flexShrink: 0 }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#f8f6f0' }}>Break down the film with AI</div>
                    <div style={{ fontSize: 11, color: '#7a7a6e' }}>Your film assistant watches the film and tags every play. <b style={{ color: '#a8a89a' }}>Fast</b> = quick &amp; economical. <b style={{ color: '#C9A84C' }}>Deep</b> = 3-pass engine (pre-snap, post-snap, check) — richest read, ~3x the cost.</div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6, flexShrink: 0 }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button
                        onClick={() => handleAutoDetect(false, 'fast')}
                        title="Single-pass breakdown — quick and economical."
                        style={{
                          background: '#2e2e28', color: '#f0eee6', border: '1px solid #44443c', borderRadius: 4,
                          padding: '8px 14px', fontSize: 12, fontWeight: 700, cursor: 'pointer', letterSpacing: '0.06em',
                        }}
                      >
                        FAST
                      </button>
                      <button
                        onClick={() => handleAutoDetect(false, 'deep')}
                        title="Three-pass engine: pre-snap read, post-snap detail, and a final check. Richest breakdown, ~3x cost."
                        style={{
                          background: '#C9A84C', color: '#1c1c1c', border: 'none', borderRadius: 4,
                          padding: '8px 16px', fontSize: 12, fontWeight: 700, cursor: 'pointer', letterSpacing: '0.06em',
                        }}
                      >
                        DEEP · 3-PASS
                      </button>
                    </div>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                      <button
                        onClick={() => handleAutoDetect(false, 'fast', true)}
                        title="Quick test: breaks down only the first few minutes of film. Costs pennies. Use it to confirm the breakdown and team colors before a full run."
                        style={{ background: 'none', border: '1px solid #44443c', borderRadius: 4, color: '#a8d8b0', fontSize: 10, cursor: 'pointer', padding: '4px 10px', fontWeight: 700 }}
                      >
                        QUICK TEST (first 3 min, ~pennies)
                      </button>
                      <button
                        onClick={() => handleAutoDetect(true)}
                        title="Run a preview — the AI breaks down the film and shows what it would tag, without saving anything."
                        style={{ background: 'none', border: 'none', color: '#7a7a6e', fontSize: 10, cursor: 'pointer', padding: 0 }}
                      >
                        or preview (nothing saved)
                      </button>
                    </div>
                  </div>
                </div>
              )
            })()}

            {/* Team attribution — jersey colors so the AI knows which team is which */}
            <div style={{ background: 'rgba(201,168,76,0.06)', border: '1px solid rgba(201,168,76,0.25)', borderRadius: 6, padding: '12px 16px', marginBottom: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#f8f6f0', marginBottom: 2 }}>Which team do you want the breakdown on?</div>
              <div style={{ fontSize: 11, color: '#a8a89a', marginBottom: 8 }}>
                The AI needs to tell the two teams apart. Just type each team's jersey color (10 seconds), then break down the film. The first box is the team you'll get the scouting report on.
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div style={{ flex: 1, minWidth: 160 }}>
                  <label style={{ fontSize: 10, color: '#C9A84C', fontWeight: 700 }}>Team you want the report on — their jersey</label>
                  <input value={scoutJersey} onChange={e => setScoutJersey(e.target.value)} placeholder="e.g. green jerseys"
                    style={{ width: '100%', background: '#2a2a24', border: '1px solid #44443c', borderRadius: 4, padding: '6px 10px', fontSize: 12, color: '#f0eee6' }} />
                </div>
                <div style={{ flex: 1, minWidth: 160 }}>
                  <label style={{ fontSize: 10, color: '#7a7a6e' }}>The other team — their jersey</label>
                  <input value={oppJersey} onChange={e => setOppJersey(e.target.value)} placeholder="e.g. white jerseys"
                    style={{ width: '100%', background: '#2a2a24', border: '1px solid #44443c', borderRadius: 4, padding: '6px 10px', fontSize: 12, color: '#f0eee6' }} />
                </div>
                <button onClick={saveJerseys} style={{ background: '#C9A84C', color: '#1c1c1c', border: 'none', borderRadius: 4, padding: '7px 16px', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>
                  {jerseySaved ? 'Saved ✓' : 'Save'}
                </button>
              </div>
            </div>

            {/* Detection scorecard — how complete and confident the read is (+ accuracy vs tagged plays) */}
            {scorecard?.ready && (
              <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6, padding: '14px 16px', marginBottom: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <Activity size={14} style={{ color: '#C9A84C' }} />
                  <span style={{ fontSize: 13, fontWeight: 700, color: '#f8f6f0' }}>Detection Scorecard</span>
                  <span style={{ fontSize: 11, color: '#7a7a6e', marginLeft: 'auto' }}>
                    {scorecard.plays} plays · {scorecard.confident_pct}% confident
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 16, marginBottom: 12, flexWrap: 'wrap' }}>
                  <div><div style={{ fontSize: 20, fontWeight: 700, color: '#2d8c40' }}>{scorecard.confident}</div><div style={{ fontSize: 10, color: '#7a7a6e' }}>confident</div></div>
                  <div><div style={{ fontSize: 20, fontWeight: 700, color: '#e0a050' }}>{scorecard.flagged_for_review}</div><div style={{ fontSize: 10, color: '#7a7a6e' }}>need your eyes</div></div>
                  <div><div style={{ fontSize: 20, fontWeight: 700, color: '#f8f6f0' }}>{scorecard.avg_confidence}</div><div style={{ fontSize: 10, color: '#7a7a6e' }}>avg confidence</div></div>
                  <div><div style={{ fontSize: 20, fontWeight: 700, color: '#f8f6f0' }}>{scorecard.side_split?.offense}/{scorecard.side_split?.defense}/{scorecard.side_split?.special_teams}</div><div style={{ fontSize: 10, color: '#7a7a6e' }}>off / def / ST</div></div>
                </div>
                <div style={{ fontSize: 11, color: '#a8a89a', marginBottom: 6 }}>Field coverage (how often each detail was read)</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 6 }}>
                  {Object.entries(scorecard.fill_rates || {}).map(([k, v]: any) => (
                    <div key={k} style={{ fontSize: 11 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', color: '#b8b8aa' }}>
                        <span>{k.replace(/_/g, ' ')}</span><span style={{ color: v >= 70 ? '#2d8c40' : v >= 40 ? '#e0a050' : '#e07070' }}>{v}%</span>
                      </div>
                      <div style={{ height: 4, background: 'rgba(255,255,255,0.08)', borderRadius: 2, marginTop: 2 }}>
                        <div style={{ height: 4, width: `${v}%`, background: v >= 70 ? '#2d8c40' : v >= 40 ? '#e0a050' : '#e07070', borderRadius: 2 }} />
                      </div>
                    </div>
                  ))}
                </div>
                {scorecard.weakest_fields?.length > 0 && (
                  <div style={{ fontSize: 10, color: '#7a7a6e', marginTop: 8 }}>Weakest reads: {scorecard.weakest_fields.join(', ')} — verify these in the Play Log.</div>
                )}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10 }}>
                  <button onClick={handleRederiveDowns} title="Propagate down & distance across each drive from the plays you've already tagged. Tag the 1st & 10 that starts a drive, then fill the rest automatically." style={{ background: '#2e2e28', color: '#f0eee6', border: '1px solid #44443c', borderRadius: 4, padding: '6px 12px', fontSize: 11, fontWeight: 700, cursor: 'pointer' }}>
                    Auto-fill down &amp; distance
                  </button>
                  <span style={{ fontSize: 10, color: '#7a7a6e' }}>Tag the first play of a drive (e.g. 1st &amp; 10), then click to chain the rest from each play's yardage.</span>
                </div>
                {accuracy?.ready ? (
                  <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                    <div style={{ fontSize: 11, color: '#a8a89a', marginBottom: 4 }}>Accuracy vs your tagged plays</div>
                    <div style={{ display: 'flex', gap: 16, fontSize: 12, color: '#f0eee6' }}>
                      <span><b style={{ color: '#C9A84C' }}>{accuracy.recall_pct}%</b> plays caught ({accuracy.matched}/{accuracy.truth_plays} real plays caught)</span>
                      <span><b style={{ color: '#C9A84C' }}>{accuracy.precision_pct}%</b> were right</span>
                    </div>
                  </div>
                ) : (
                  <div style={{ fontSize: 10, color: '#7a7a6e', marginTop: 10, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                    Want a true accuracy score? Tag this game's plays yourself (the plays you tag yourself), then re-open this card to see plays caught and how many were right vs your tags.
                  </div>
                )}
              </div>
            )}

            {/* UATP live activity panel — coach sees the agent work in real time */}
            <AgentActivityPanel
              entries={agentLog}
              live={!!detectStatus && (['queued', 'running'].includes(detectStatus.job_status ?? '') || detectStatus.game_status === 'analyzing')}
            />

            </div>{/* end setup & status scroll */}
          </div>

          {/* Right panel */}
          <div style={{
            width: 300, flexShrink: 0,
            borderLeft: '1px solid rgba(255,255,255,0.06)',
            display: 'flex', flexDirection: 'column',
            overflow: 'hidden',
          }}>
            {/* Tabs */}
            <div style={{ display: 'flex', borderBottom: '1px solid rgba(255,255,255,0.06)', flexShrink: 0 }}>
              {(['tag', 'log', 'cutups', 'tendencies', 'players', 'accuracy'] as const).map(t => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  style={{
                    flex: 1, padding: '11px 0', fontSize: 11, fontWeight: 600,
                    letterSpacing: '0.04em', textTransform: 'uppercase',
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: tab === t ? '#C9A84C' : '#7a7a6e',
                    borderBottom: tab === t ? '2px solid #C9A84C' : '2px solid transparent',
                    marginBottom: -1,
                  }}
                >
                  {t === 'tag' ? <><Tag size={11} style={{ display: 'inline', marginRight: 4 }} />Tag</>
                    : t === 'log' ? <><FileText size={11} style={{ display: 'inline', marginRight: 4 }} />Log ({events.length})</>
                    : t === 'cutups' ? <><Film size={11} style={{ display: 'inline', marginRight: 4 }} />Cut-Ups</>
                    : t === 'tendencies' ? <><TrendingUp size={11} style={{ display: 'inline', marginRight: 4 }} />Tendencies</>
                    : t === 'players' ? <><Users size={11} style={{ display: 'inline', marginRight: 4 }} />Players</>
                    : <><Activity size={11} style={{ display: 'inline', marginRight: 4 }} />Accuracy</>}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
              {tab === 'tag'
                ? (game.sport === 'basketball'
                    ? <BasketballTagForm currentTime={currentTime} onSave={handleSaveTag} saving={saving} opponent={game.opponent} />
                    : <TagForm currentTime={currentTime} onSave={handleSaveTag} saving={saving} side={side} setSide={setSide} opponent={game.opponent} />)
                : tab === 'log'
                ? <PlayLog events={events} onDelete={handleDelete} onSeek={handleSeek} onUpdate={handleUpdate} sport={game.sport} />
                : tab === 'cutups'
                ? <CutUps events={events} videoRef={videoRef} sport={game.sport} />
                : tab === 'tendencies'
                ? <TendenciesPanel gameId={id} />
                : tab === 'players'
                ? <PlayersPanel gameId={id} />
                : <AccuracyPanel gameId={id} />
              }
            </div>

            {/* Generate Report CTA */}
            {events.length >= 3 && (
              <div style={{ padding: 16, borderTop: '1px solid rgba(255,255,255,0.06)', flexShrink: 0 }}>
                {/* Opponent vs self-scout (football only — self-scout turns the same
                    engine on your own film: what you're giving away). */}
                {(game.sport === 'football' || game.sport === 'flag_football') && (
                  <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
                    {([['opponent', 'Scout Opponent'], ['self_scout', 'Self-Scout']] as const).map(([k, label]) => (
                      <button key={k} onClick={() => setReportType(k)}
                        style={{
                          flex: 1, padding: '6px 0', fontSize: 10, fontWeight: 700, cursor: 'pointer', borderRadius: 4,
                          border: 'none', letterSpacing: '0.04em', textTransform: 'uppercase',
                          background: reportType === k ? 'rgba(201,168,76,0.2)' : 'rgba(255,255,255,0.04)',
                          color: reportType === k ? '#C9A84C' : '#7a7a6e',
                        }}>{label}</button>
                    ))}
                  </div>
                )}
                <button
                  onClick={handleGenerateReport}
                  disabled={reportPending}
                  className="btn-green"
                  style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
                >
                  {reportPending
                    ? <><Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Generating...</>
                    : <><FileText size={14} /> {reportType === 'self_scout' ? 'GENERATE SELF-SCOUT' : 'GENERATE AI REPORT'}</>
                  }
                </button>
                <div style={{ fontSize: 10, color: '#7a7a6e', textAlign: 'center', marginTop: 6 }}>
                  {reportType === 'self_scout'
                    ? `${events.length} plays · what you're giving away`
                    : `${events.length} plays · AI tendency analysis`}
                </div>
              </div>
            )}
          </div>

          {/* RIGHT: the film — the hero, takes the majority of the room. */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 16 }}>
            <div style={{
              flex: '1 1 auto', minHeight: 360, background: '#000', borderRadius: 6, overflow: 'hidden',
              border: '1px solid rgba(255,255,255,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              {game.download_url ? (
                <video ref={videoRef} src={game.download_url} controls onTimeUpdate={handleTimeUpdate}
                  style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
              ) : (
                <div style={{ textAlign: 'center', color: '#7a7a6e', padding: 40 }}>
                  {['queued', 'downloading', 'processing'].includes(game.status)
                    ? <><Loader2 size={32} style={{ color: '#C9A84C', animation: 'spin 1s linear infinite', margin: '0 auto 12px', display: 'block' }} /><div>Processing film...</div></>
                    : <><Play size={40} style={{ margin: '0 auto 12px', display: 'block' }} /><div>Video not available</div></>
                  }
                </div>
              )}
            </div>
            <div style={{ marginTop: 8, fontSize: 12, color: '#7a7a6e', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
              <Tag size={12} /> {events.length} play{events.length !== 1 ? 's' : ''} tagged
              {game.duration_seconds && <span style={{ marginLeft: 8 }}>· {fmtTime(game.duration_seconds)} total</span>}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
