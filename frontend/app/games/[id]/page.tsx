'use client'
import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { ChevronLeft, Tag, Play, Trash2, Clock, FileText, Loader2, CheckCircle, AlertCircle, Zap, Pencil, Check, X, Activity } from 'lucide-react'
import Link from 'next/link'

// ── Types ──────────────────────────────────────────────────────────────────
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
  extra_data?: { auto_detected?: boolean; confidence?: number }
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
          <div>{lbl('FORMATION')}{sel(formation, setFormation, FORMATIONS)}</div>
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
          <div>{lbl('FRONT')}{sel(front, setFront, FRONTS)}</div>
          <div>{lbl('COVERAGE')}{sel(coverage, setCoverage, COVERAGES)}</div>
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

// ── Play Log ──────────────────────────────────────────────────────────────
function PlayLog({
  events,
  onDelete,
  onSeek,
  onUpdate,
}: {
  events: TaggedEvent[]
  onDelete: (id: string) => void
  onSeek: (t: number) => void
  onUpdate: (id: string, data: Partial<TaggedEvent>) => Promise<void>
}) {
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
        {([['all', 'All'], ['offense', 'Off'], ['defense', 'Def'], ['special_teams', 'ST']] as const).map(([k, label]) => (
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
          <div style={{ fontSize: 10, color: '#C9A84C', fontWeight: 700, letterSpacing: '0.06em' }}>EDITING {fmtTime(ev.time_seconds)} · {(ev.side || 'offense').replace('_', ' ').toUpperCase()}</div>
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
              {esel('defensive_front', FRONTS)}{esel('coverage', COVERAGES)}{esel('blitz', BLITZES)}
            </div>
          ) : draft.side === 'special_teams' ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
              {esel('play_type', ST_UNITS)}{esel('formation', FORMATIONS)}
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
              {esel('formation', FORMATIONS)}{esel('play_type', PLAY_TYPES)}{esel('personnel', PERSONNEL)}
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 70px', gap: 6 }}>
            {esel('result', draft.side === 'special_teams' ? ST_RESULTS : RESULTS)}
            <input type="number" placeholder="yds" value={(draft.yards_gained as number) ?? ''} onChange={e => set('yards_gained', e.target.value === '' ? null : Number(e.target.value))} className="input" style={{ fontSize: 11, padding: '4px 6px', height: 30 }} />
          </div>
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

// ── Accuracy Panel ─────────────────────────────────────────────────────────
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
          <div>AI-detected plays: <b style={{ color: '#f8f6f0' }}>{data?.ai_plays ?? 0}</b></div>
        </div>
        <p style={{ color: '#7a7a6e', fontSize: 11 }}>
          <b>How it works:</b> Manually tag this game (your tags = ground truth), then run AI auto-detect.
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
        {big('Recall', data.recall_pct, 'plays caught', '#2d8c40')}
        {big('Precision', data.precision_pct, 'tags real', '#C9A84C')}
      </div>
      <div style={{ fontSize: 11, color: '#7a7a6e' }}>
        Matched {data.matched} of {data.truth_plays} your plays · AI tagged {data.ai_plays} (±{data.match_window_s}s window)
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
  const [tab, setTab] = useState<'tag' | 'log' | 'accuracy'>('tag')
  const [side, setSide] = useState<'offense' | 'defense' | 'special_teams'>('offense')
  const [reportPending, setReportPending] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [detectStatus, setDetectStatus] = useState<null | {
    game_status: string
    job_status: string | null
    plays_detected: number
    error: string | null
  }>(null)
  const detectPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])

  useEffect(() => {
    if (!user || !id) return
    api.get(`/games/${id}`).then(r => setGame(r.data))
    api.get(`/events?game_id=${id}`).then(r => setEvents(r.data)).catch(() => {})
    // Check if there's a running detect job
    api.get(`/games/${id}/auto-detect/status`).then(r => {
      setDetectStatus(r.data)
      if (['queued', 'running'].includes(r.data.job_status) || r.data.game_status === 'analyzing') {
        startDetectPoll()
      }
    }).catch(() => {})
  }, [user, id])

  const startDetectPoll = () => {
    if (detectPollRef.current) return
    detectPollRef.current = setInterval(async () => {
      try {
        const r = await api.get(`/games/${id}/auto-detect/status`)
        setDetectStatus(r.data)
        const done = !['queued', 'running'].includes(r.data.job_status ?? '') && r.data.game_status !== 'analyzing'
        if (done) {
          clearInterval(detectPollRef.current!)
          detectPollRef.current = null
          // Reload events
          const evRes = await api.get(`/events?game_id=${id}`)
          setEvents(evRes.data)
          if (r.data.plays_detected > 0) {
            showToast(`${r.data.plays_detected} plays auto-detected`)
            setTab('log')
          }
        }
      } catch {}
    }, 4000)
  }

  useEffect(() => () => { if (detectPollRef.current) clearInterval(detectPollRef.current) }, [])

  const handleAutoDetect = async () => {
    try {
      await api.post(`/games/${id}/auto-detect`)
      const r = await api.get(`/games/${id}/auto-detect/status`)
      setDetectStatus(r.data)
      startDetectPoll()
      showToast('AI play detection started…')
    } catch (e: any) {
      showToast(e?.response?.data?.detail ?? 'Failed to start detection')
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
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (eventId: string) => {
    await api.delete(`/events/${eventId}`)
    setEvents(prev => prev.filter(e => e.id !== eventId))
  }

  const handleUpdate = async (eventId: string, data: Partial<TaggedEvent>) => {
    const res = await api.patch(`/events/${eventId}`, data)
    setEvents(prev => prev.map(e => e.id === eventId ? { ...e, ...res.data } : e)
      .sort((a, b) => (a.time_seconds ?? 0) - (b.time_seconds ?? 0)))
    showToast('Play updated')
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
        title: `${game.title} Tendency Report`,
        sport: game.sport,
        game_ids: [id],
        report_type: 'opponent',
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
        </div>

        {/* Main content: video + sidebar */}
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          {/* Video column */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: '16px 16px 16px 20px' }}>
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
                  <span style={{ color: '#C9A84C', fontWeight: 600 }}>AI is scanning your film for plays…</span>
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
                    {detectStatus.plays_detected} plays auto-detected
                  </span>
                  <span style={{ color: '#7a7a6e', marginLeft: 4 }}>— review in the Play Log, edit any you need.</span>
                  <button onClick={handleAutoDetect} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#7a7a6e', fontSize: 11, cursor: 'pointer' }}>
                    Re-run
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
                  <span style={{ color: '#e07070' }}>Auto-detection failed. Tag plays manually or </span>
                  <button onClick={handleAutoDetect} style={{ background: 'none', border: 'none', color: '#C9A84C', fontSize: 13, cursor: 'pointer', padding: 0, textDecoration: 'underline' }}>
                    try again
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
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#f8f6f0' }}>Auto-detect plays with AI</div>
                    <div style={{ fontSize: 11, color: '#7a7a6e' }}>Claude Vision scans the film and tags every play automatically — usually under 5 minutes.</div>
                  </div>
                  <button
                    onClick={handleAutoDetect}
                    style={{
                      background: '#C9A84C', color: '#1c1c1c', border: 'none', borderRadius: 4,
                      padding: '8px 16px', fontSize: 12, fontWeight: 700, cursor: 'pointer',
                      letterSpacing: '0.06em', flexShrink: 0,
                    }}
                  >
                    AUTO-DETECT
                  </button>
                </div>
              )
            })()}

            <div style={{
              flex: 1, background: '#000', borderRadius: 6, overflow: 'hidden',
              border: '1px solid rgba(255,255,255,0.08)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              minHeight: 0,
            }}>
              {game.download_url ? (
                <video
                  ref={videoRef}
                  src={game.download_url}
                  controls
                  onTimeUpdate={handleTimeUpdate}
                  style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                />
              ) : (
                <div style={{ textAlign: 'center', color: '#7a7a6e', padding: 40 }}>
                  {['queued', 'downloading', 'processing'].includes(game.status)
                    ? <><Loader2 size={32} style={{ color: '#C9A84C', animation: 'spin 1s linear infinite', margin: '0 auto 12px', display: 'block' }} /><div>Processing film...</div></>
                    : <><Play size={40} style={{ margin: '0 auto 12px', display: 'block' }} /><div>Video not available</div></>
                  }
                </div>
              )}
            </div>

            {/* Play count */}
            <div style={{ marginTop: 10, fontSize: 12, color: '#7a7a6e', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Tag size={12} /> {events.length} play{events.length !== 1 ? 's' : ''} tagged
              {game.duration_seconds && (
                <span style={{ marginLeft: 8 }}>· {fmtTime(game.duration_seconds)} total</span>
              )}
            </div>
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
              {(['tag', 'log', 'accuracy'] as const).map(t => (
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
                    : <><Activity size={11} style={{ display: 'inline', marginRight: 4 }} />Accuracy</>}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
              {tab === 'tag'
                ? <TagForm currentTime={currentTime} onSave={handleSaveTag} saving={saving} side={side} setSide={setSide} opponent={game.opponent} />
                : tab === 'log'
                ? <PlayLog events={events} onDelete={handleDelete} onSeek={handleSeek} onUpdate={handleUpdate} />
                : <AccuracyPanel gameId={id} />
              }
            </div>

            {/* Generate Report CTA */}
            {events.length >= 3 && (
              <div style={{ padding: 16, borderTop: '1px solid rgba(255,255,255,0.06)', flexShrink: 0 }}>
                <button
                  onClick={handleGenerateReport}
                  disabled={reportPending}
                  className="btn-green"
                  style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
                >
                  {reportPending
                    ? <><Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Generating...</>
                    : <><FileText size={14} /> GENERATE AI REPORT</>
                  }
                </button>
                <div style={{ fontSize: 10, color: '#7a7a6e', textAlign: 'center', marginTop: 6 }}>
                  {events.length} plays · AI tendency analysis
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
