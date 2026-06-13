'use client'
import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { ChevronLeft, Tag, Play, Trash2, Clock, FileText, Loader2, CheckCircle, AlertCircle } from 'lucide-react'
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
  time_seconds: number | null
  down: number | null
  distance: number | null
  formation: string | null
  play_type: string | null
  result: string | null
  yards_gained: number | null
  personnel: string | null
  motion: boolean
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

// ── Status Banner ─────────────────────────────────────────────────────────
function StatusBanner({ status }: { status: string }) {
  if (status === 'ready') return null
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
}: {
  currentTime: number
  onSave: (data: Partial<TaggedEvent>) => Promise<void>
  saving: boolean
}) {
  const [down, setDown] = useState<number | ''>('')
  const [distance, setDistance] = useState<number | ''>('')
  const [formation, setFormation] = useState('')
  const [playType, setPlayType] = useState('')
  const [result, setResult] = useState('')
  const [yards, setYards] = useState<number | ''>('')
  const [personnel, setPersonnel] = useState('')
  const [motion, setMotion] = useState(false)

  const handleSave = async () => {
    await onSave({
      event_type: 'play',
      time_seconds: currentTime,
      down: down === '' ? undefined : Number(down),
      distance: distance === '' ? undefined : Number(distance),
      formation: formation || undefined,
      play_type: playType || undefined,
      result: result || undefined,
      yards_gained: yards === '' ? undefined : Number(yards),
      personnel: personnel || undefined,
      motion,
    })
    // reset
    setDown('')
    setDistance('')
    setFormation('')
    setPlayType('')
    setResult('')
    setYards('')
    setPersonnel('')
    setMotion(false)
  }

  const sel = (val: string, set: (v: string) => void, options: string[]) => (
    <select
      value={val}
      onChange={e => set(e.target.value)}
      className="input"
      style={{ fontSize: 12, padding: '6px 10px', height: 36 }}
    >
      <option value="">—</option>
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Time stamp */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        background: 'rgba(201,168,76,0.08)', border: '1px solid rgba(201,168,76,0.2)',
        borderRadius: 4, padding: '6px 12px',
      }}>
        <Clock size={13} style={{ color: '#C9A84C' }} />
        <span style={{ fontFamily: 'var(--font-dm-mono)', fontSize: 13, color: '#C9A84C' }}>
          {fmtTime(currentTime)}
        </span>
        <span style={{ fontSize: 11, color: '#7a7a6e', marginLeft: 4 }}>current timestamp</span>
      </div>

      {/* Down & Distance */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <div>
          <div style={{ fontSize: 10, color: '#7a7a6e', marginBottom: 4, letterSpacing: '0.08em' }}>DOWN</div>
          <div style={{ display: 'flex', gap: 4 }}>
            {[1, 2, 3, 4].map(d => (
              <button
                key={d}
                onClick={() => setDown(down === d ? '' : d)}
                style={{
                  flex: 1, height: 32, borderRadius: 3, fontSize: 13, fontWeight: 600, cursor: 'pointer',
                  background: down === d ? '#C9A84C' : 'rgba(255,255,255,0.05)',
                  color: down === d ? '#1c1c1c' : '#f8f6f0',
                  border: down === d ? 'none' : '1px solid rgba(255,255,255,0.1)',
                  transition: 'all 0.12s',
                }}
              >{d}</button>
            ))}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: '#7a7a6e', marginBottom: 4, letterSpacing: '0.08em' }}>DISTANCE</div>
          <input
            type="number"
            min={0} max={99}
            placeholder="yds"
            value={distance}
            onChange={e => setDistance(e.target.value === '' ? '' : Number(e.target.value))}
            className="input"
            style={{ fontSize: 13, padding: '6px 10px', height: 36, width: '100%' }}
          />
        </div>
      </div>

      {/* Formation */}
      <div>
        <div style={{ fontSize: 10, color: '#7a7a6e', marginBottom: 4, letterSpacing: '0.08em' }}>FORMATION</div>
        {sel(formation, setFormation, FORMATIONS)}
      </div>

      {/* Play type */}
      <div>
        <div style={{ fontSize: 10, color: '#7a7a6e', marginBottom: 4, letterSpacing: '0.08em' }}>PLAY TYPE</div>
        {sel(playType, setPlayType, PLAY_TYPES)}
      </div>

      {/* Result & Yards */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px', gap: 8 }}>
        <div>
          <div style={{ fontSize: 10, color: '#7a7a6e', marginBottom: 4, letterSpacing: '0.08em' }}>RESULT</div>
          {sel(result, setResult, RESULTS)}
        </div>
        <div>
          <div style={{ fontSize: 10, color: '#7a7a6e', marginBottom: 4, letterSpacing: '0.08em' }}>YDS</div>
          <input
            type="number"
            placeholder="0"
            value={yards}
            onChange={e => setYards(e.target.value === '' ? '' : Number(e.target.value))}
            className="input"
            style={{ fontSize: 13, padding: '6px 10px', height: 36, width: '100%' }}
          />
        </div>
      </div>

      {/* Personnel */}
      <div>
        <div style={{ fontSize: 10, color: '#7a7a6e', marginBottom: 4, letterSpacing: '0.08em' }}>PERSONNEL</div>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {PERSONNEL.map(p => (
            <button
              key={p}
              onClick={() => setPersonnel(personnel === p ? '' : p)}
              style={{
                padding: '4px 10px', borderRadius: 3, fontSize: 12, cursor: 'pointer',
                background: personnel === p ? 'rgba(26,92,42,0.5)' : 'rgba(255,255,255,0.05)',
                color: personnel === p ? '#2d8c40' : '#ede9df',
                border: personnel === p ? '1px solid #2d8c40' : '1px solid rgba(255,255,255,0.08)',
                fontFamily: 'var(--font-dm-mono)',
              }}
            >{p}</button>
          ))}
        </div>
      </div>

      {/* Motion toggle */}
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
        <div
          onClick={() => setMotion(!motion)}
          style={{
            width: 36, height: 20, borderRadius: 10, position: 'relative', cursor: 'pointer',
            background: motion ? '#1a5c2a' : 'rgba(255,255,255,0.1)',
            transition: 'background 0.2s',
            border: motion ? '1px solid #2d8c40' : '1px solid rgba(255,255,255,0.15)',
          }}
        >
          <div style={{
            position: 'absolute', top: 2, left: motion ? 16 : 2, width: 14, height: 14,
            borderRadius: '50%', background: motion ? '#C9A84C' : '#7a7a6e',
            transition: 'left 0.15s, background 0.15s',
          }} />
        </div>
        <span style={{ color: motion ? '#f8f6f0' : '#7a7a6e' }}>Motion</span>
      </label>

      {/* Tag button */}
      <button
        onClick={handleSave}
        disabled={saving}
        className="btn-primary"
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: 4 }}
      >
        {saving
          ? <><Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Saving...</>
          : <><Tag size={14} /> TAG PLAY</>
        }
      </button>
    </div>
  )
}

// ── Play Log ──────────────────────────────────────────────────────────────
function PlayLog({
  events,
  onDelete,
  onSeek,
}: {
  events: TaggedEvent[]
  onDelete: (id: string) => void
  onSeek: (t: number) => void
}) {
  if (events.length === 0) {
    return (
      <div style={{ textAlign: 'center', color: '#7a7a6e', padding: '32px 0', fontSize: 13 }}>
        No plays tagged yet. Pause the video and click TAG PLAY.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {events.map((ev, i) => (
        <div
          key={ev.id}
          style={{
            display: 'flex', alignItems: 'center', gap: 10,
            background: 'rgba(255,255,255,0.03)', borderRadius: 4,
            padding: '8px 12px', border: '1px solid rgba(255,255,255,0.05)',
          }}
        >
          <span style={{ fontSize: 11, color: '#7a7a6e', width: 24, textAlign: 'right', flexShrink: 0 }}>
            {i + 1}
          </span>
          <button
            onClick={() => ev.time_seconds != null && onSeek(ev.time_seconds)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer', color: '#C9A84C',
              padding: 0, fontFamily: 'var(--font-dm-mono)', fontSize: 12, flexShrink: 0,
            }}
          >
            {fmtTime(ev.time_seconds)}
          </button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, color: '#f8f6f0', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {ev.down && <span style={{ color: '#C9A84C', fontWeight: 600 }}>{ev.down}&amp;{ev.distance}</span>}
              {ev.formation && <span>{ev.formation}</span>}
              {ev.play_type && <span style={{ color: '#ede9df' }}>{ev.play_type}</span>}
              {ev.result && <span style={{ color: ev.result === 'Touchdown' ? '#2d8c40' : ev.result === 'Interception' || ev.result === 'Fumble' ? '#e07070' : '#7a7a6e' }}>{ev.result}</span>}
              {ev.yards_gained != null && <span style={{ color: '#7a7a6e' }}>{ev.yards_gained > 0 ? '+' : ''}{ev.yards_gained} yds</span>}
              {ev.motion && <span style={{ fontSize: 10, color: '#7a7a6e', fontStyle: 'italic' }}>motion</span>}
            </div>
          </div>
          <button
            onClick={() => onDelete(ev.id)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#7a7a6e', padding: 4, flexShrink: 0 }}
            title="Delete"
          >
            <Trash2 size={13} />
          </button>
        </div>
      ))}
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
  const [tab, setTab] = useState<'tag' | 'log'>('tag')
  const [reportPending, setReportPending] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])

  useEffect(() => {
    if (!user || !id) return
    api.get(`/games/${id}`).then(r => setGame(r.data))
    api.get(`/events?game_id=${id}`).then(r => setEvents(r.data)).catch(() => {})
  }, [user, id])

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

  const handleSeek = (t: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = t
      videoRef.current.play()
    }
    setTab('log')
  }

  const handleGenerateReport = async () => {
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
              {(['tag', 'log'] as const).map(t => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  style={{
                    flex: 1, padding: '11px 0', fontSize: 12, fontWeight: 600,
                    letterSpacing: '0.08em', textTransform: 'uppercase',
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: tab === t ? '#C9A84C' : '#7a7a6e',
                    borderBottom: tab === t ? '2px solid #C9A84C' : '2px solid transparent',
                    marginBottom: -1,
                  }}
                >
                  {t === 'tag' ? <><Tag size={12} style={{ display: 'inline', marginRight: 5 }} />Tag Play</> : <><FileText size={12} style={{ display: 'inline', marginRight: 5 }} />Play Log ({events.length})</>}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
              {tab === 'tag'
                ? <TagForm currentTime={currentTime} onSave={handleSaveTag} saving={saving} />
                : <PlayLog events={events} onDelete={handleDelete} onSeek={handleSeek} />
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
