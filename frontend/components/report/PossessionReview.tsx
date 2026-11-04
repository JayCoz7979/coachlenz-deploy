'use client'
import { AlertTriangle, Eye, GitBranch } from 'lucide-react'

// Coach-facing possession + review panel for basketball reports.
//
// It renders ONLY when the report summary carries a possession_context blob,
// which the backend attaches only when BB_POSSESSION_CONTEXT_ENABLED is on at
// generation time. So older reports, non-basketball reports, and reports built
// with the flag off have no blob and this panel never renders. Nothing here is
// editable: review candidates are uncertain detections surfaced for a human
// look, never shown as confirmed events, and nothing is invented.

interface EventRef {
  time_seconds: number | null
  event_type: string | null
  side: string | null
  result: string | null
  player: string | null
  quarter: number | string | null
  confidence: number
}
interface Possession {
  index: number
  team: string
  quarter: number | string
  start_time: number | null
  end_time: number | null
  event_count: number
  ending: string
  mean_confidence: number | null
  low_confidence: boolean
  undetected_possession_gap_before: boolean
}
interface ReviewCandidate {
  status: string
  reason: string
  confidence: number
  band: string
  event: EventRef
}
export interface PossessionContext {
  version?: string
  deterministic?: boolean
  disclaimer?: string
  possessions?: Possession[]
  review_candidates?: ReviewCandidate[]
  summary?: {
    total_possessions?: number
    scouted?: number
    opponent?: number
    unknown_team?: number
    quarters_detected?: number[]
    undetected_possession_gaps?: number
    low_confidence_possessions?: number
  }
}

const mmss = (s: number | null | undefined): string => {
  if (s == null || isNaN(s)) return '--:--'
  const t = Math.max(0, Math.floor(s))
  const m = Math.floor(t / 60)
  return `${m}:${String(t % 60).padStart(2, '0')}`
}
const prettyTeam = (t: string) => (t === 'scouted' ? 'Scouted team' : t === 'opponent' ? 'Opponent' : 'Unknown')
const prettyEnding = (e: string) => (e || 'unknown').replace(/_/g, ' ')

const card: React.CSSProperties = {
  background: '#2e2e2e', borderRadius: 6, padding: '20px 24px',
  border: '1px solid rgba(255,255,255,0.06)',
}
const chip: React.CSSProperties = {
  background: 'rgba(201,168,76,0.08)', border: '1px solid rgba(201,168,76,0.2)',
  borderRadius: 6, padding: '8px 12px', minWidth: 92,
}

export default function PossessionReview({ context }: { context?: PossessionContext | null }) {
  if (!context || !context.deterministic) return null
  const s = context.summary || {}
  const possessions = context.possessions || []
  const candidates = context.review_candidates || []

  const chips: { label: string; value: string | number; warn?: boolean }[] = [
    { label: 'Possessions', value: s.total_possessions ?? possessions.length },
    { label: 'Scouted', value: s.scouted ?? 0 },
    { label: 'Opponent', value: s.opponent ?? 0 },
    { label: 'Undetected gaps', value: s.undetected_possession_gaps ?? 0, warn: (s.undetected_possession_gaps ?? 0) > 0 },
    { label: 'Low confidence', value: s.low_confidence_possessions ?? 0, warn: (s.low_confidence_possessions ?? 0) > 0 },
  ]
  const quarters = s.quarters_detected || []

  return (
    <div style={{ marginBottom: 28, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ fontSize: 11, letterSpacing: '0.15em', color: '#7a7a6e', fontWeight: 700 }}>
          POSSESSION REVIEW
        </div>
        <span style={{
          fontSize: 10, color: '#C9A84C', letterSpacing: '0.12em', fontWeight: 700,
          background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.2)',
          padding: '2px 8px', borderRadius: 10,
        }}>BETA</span>
      </div>

      {/* Summary chips */}
      <div style={card}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {chips.map(c => (
            <div key={c.label} style={{ ...chip, ...(c.warn ? { borderColor: 'rgba(201,168,76,0.5)' } : {}) }}>
              <div style={{ fontSize: 22, fontWeight: 700, color: c.warn ? '#C9A84C' : '#f8f6f0', fontFamily: 'var(--font-bebas)' }}>
                {String(c.value)}
              </div>
              <div style={{ fontSize: 10, color: '#7a7a6e', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{c.label}</div>
            </div>
          ))}
          <div style={{ ...chip }}>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#f8f6f0', fontFamily: 'var(--font-bebas)' }}>
              {quarters.length ? quarters.join(', ') : '-'}
            </div>
            <div style={{ fontSize: 10, color: '#7a7a6e', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Quarters</div>
          </div>
        </div>
        {context.disclaimer && (
          <div style={{ display: 'flex', gap: 8, marginTop: 14, fontSize: 12, color: '#9a9a8e', lineHeight: 1.6 }}>
            <GitBranch size={14} style={{ color: '#7a7a6e', flexShrink: 0, marginTop: 2 }} />
            <span>{context.disclaimer}</span>
          </div>
        )}
      </div>

      {/* Needs-review candidates (never confirmed) */}
      <div style={card}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <Eye size={15} style={{ color: '#C9A84C' }} />
          <h3 style={{ fontSize: 14, fontWeight: 700, color: '#f8f6f0', letterSpacing: '0.04em' }}>
            Needs review ({candidates.length})
          </h3>
        </div>
        {candidates.length === 0 ? (
          <div style={{ fontSize: 13, color: '#7a7a6e' }}>
            No uncertain calls were flagged. Every detected action cleared the review threshold.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {candidates.map((c, i) => {
              const e = c.event || ({} as EventRef)
              const label = [e.event_type, e.result].filter(Boolean).join(' · ') || 'detection'
              return (
                <div key={i} style={{
                  padding: '10px 12px', background: '#272727', borderRadius: 6,
                  border: '1px solid rgba(255,255,255,0.05)',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                    <span style={{
                      fontFamily: 'var(--font-bebas)', fontSize: 16, color: '#C9A84C', minWidth: 48,
                    }}>{mmss(e.time_seconds)}</span>
                    <div style={{ flex: 1, minWidth: 120, fontSize: 13, color: '#ede9df', textTransform: 'capitalize' }}>
                      {label}
                      <span style={{ color: '#7a7a6e' }}>
                        {' '}· #{e.player ?? 'unknown'}{e.quarter != null && e.quarter !== 'unknown' ? ` · Q${e.quarter}` : ''}
                      </span>
                    </div>
                    <span style={{
                      fontSize: 10, letterSpacing: '0.08em', color: '#d89a3c', fontWeight: 700,
                      background: 'rgba(216,154,60,0.1)', border: '1px solid rgba(216,154,60,0.3)',
                      padding: '3px 9px', borderRadius: 10, whiteSpace: 'nowrap',
                    }}>PENDING REVIEW</span>
                  </div>
                  <div style={{ fontSize: 11, color: '#8a8a7e', marginTop: 4 }}>
                    Confidence {Math.round((c.confidence ?? 0) * 100)}% · below review threshold
                  </div>
                </div>
              )
            })}
            <div style={{ display: 'flex', gap: 8, marginTop: 4, fontSize: 11, color: '#8a8a7e', lineHeight: 1.6 }}>
              <AlertTriangle size={13} style={{ color: '#d89a3c', flexShrink: 0, marginTop: 1 }} />
              <span>These are uncertain detections surfaced for a coach to confirm against the film. They are not counted as confirmed events. Timestamps are film-relative.</span>
            </div>
          </div>
        )}
      </div>

      {/* Possession timeline */}
      {possessions.length > 0 && (
        <div style={card}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: '#f8f6f0', letterSpacing: '0.04em', marginBottom: 12 }}>
            Possession sequence
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {possessions.map(p => (
              <div key={p.index} style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
                background: '#272727', borderRadius: 6, fontSize: 12.5, flexWrap: 'wrap',
              }}>
                <span style={{ fontFamily: 'var(--font-bebas)', fontSize: 15, color: '#7a7a6e', minWidth: 20 }}>
                  {p.index + 1}
                </span>
                <span style={{
                  color: p.team === 'opponent' ? '#d89a3c' : p.team === 'scouted' ? '#2d8c40' : '#7a7a6e',
                  fontWeight: 700, minWidth: 92,
                }}>{prettyTeam(p.team)}</span>
                <span style={{ color: '#9a9a8e', whiteSpace: 'nowrap' }}>{mmss(p.start_time)} – {mmss(p.end_time)}</span>
                <span style={{ color: '#ede9df', textTransform: 'capitalize', flex: '1 1 72px', minWidth: 72 }}>{prettyEnding(p.ending)}</span>
                {p.undetected_possession_gap_before && (
                  <span title="The opponent possession before this was not detected; it is flagged, not invented." style={{
                    fontSize: 10, color: '#d89a3c', background: 'rgba(216,154,60,0.1)',
                    border: '1px solid rgba(216,154,60,0.25)', padding: '2px 7px', borderRadius: 9, whiteSpace: 'nowrap',
                  }}>gap before</span>
                )}
                {p.low_confidence && (
                  <span style={{
                    fontSize: 10, color: '#c98a8a', background: 'rgba(201,138,138,0.1)',
                    border: '1px solid rgba(201,138,138,0.25)', padding: '2px 7px', borderRadius: 9, whiteSpace: 'nowrap',
                  }}>low conf</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
