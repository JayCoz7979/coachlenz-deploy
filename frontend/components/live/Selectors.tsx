'use client'
/**
 * Live Game Play Logger, touch-optimized selectors.
 * Pure presentational components that consume the existing CoachLenz CSS design
 * tokens (var(--gold), var(--bg3), ...). They do not import or alter any global
 * styles, so the live site is untouched. All tap targets are >= 44px.
 */
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { GAPS, RUSH_LANES, ROUTES, SHOT_ZONES, gapLabel, type TermSystem } from './fields'

const ZONE_LABEL: Record<string, string> = Object.fromEntries(SHOT_ZONES.map(z => [z.value, z.label]))

const GOLD = 'var(--gold)'
const sel = (on: boolean): CSSProperties => ({
  border: '1px solid ' + (on ? GOLD : 'var(--border2)'),
  background: on ? 'rgba(201,168,76,0.18)' : 'var(--bg3)',
  color: on ? GOLD : 'var(--text2)',
  borderRadius: 8, fontWeight: 700, cursor: 'pointer', minHeight: 44,
  fontSize: 14, padding: '8px 10px', transition: 'background .1s',
})

/** Reusable large-tap-target chip group, the workhorse of the logger. */
export function TapGroup({ options, value, onChange, cols }: {
  options: { value: string; label: string }[] | string[]
  value?: string | null
  onChange: (v: string) => void
  cols?: number
}) {
  const opts = options.map(o => (typeof o === 'string' ? { value: o, label: o } : o))
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols || 3}, 1fr)`, gap: 8 }}>
      {opts.map(o => (
        <button key={o.value} type="button" onClick={() => onChange(o.value)} style={sel(value === o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** 5-man offensive-line gap/hole selector. Labels adapt to the chosen system. */
export function GapSelector({ value, onChange, system }: {
  value?: string | null; onChange: (v: string) => void; system: TermSystem
}) {
  // 8 gaps across; center the line. OL boxes sit between the inner gaps.
  const W = 360, H = 150
  const gapW = W / 8
  const olY = 74, olH = 30
  // OL box x-positions (LT LG C RG RT) sit over the seams.
  const olX = [1, 2, 3.5, 5, 6].map(i => i * gapW)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', touchAction: 'manipulation' }}>
      {/* QB marker */}
      <circle cx={W / 2} cy={H - 14} r={9} fill="var(--bg3)" stroke="var(--border3)" />
      <text x={W / 2} y={H - 10} textAnchor="middle" fontSize="9" fill="var(--text3)">QB</text>
      {/* tappable gaps */}
      {GAPS.map((g, i) => {
        const x = i * gapW
        const on = value === g.value
        return (
          <g key={g.value} onClick={() => onChange(g.value)} style={{ cursor: 'pointer' }}>
            <rect x={x + 2} y={8} width={gapW - 4} height={olY - 12} rx={5}
              fill={on ? 'rgba(201,168,76,0.22)' : 'var(--bg3)'}
              stroke={on ? GOLD : 'var(--border2)'} />
            <text x={x + gapW / 2} y={40} textAnchor="middle" fontSize="12" fontWeight="700"
              fill={on ? GOLD : 'var(--text2)'}>{gapLabel(g.value, system)}</text>
          </g>
        )
      })}
      {/* OL boxes */}
      {olX.map((x, i) => (
        <rect key={i} x={x - 13} y={olY} width={26} height={olH} rx={4}
          fill="var(--bg2)" stroke="var(--border3)" />
      ))}
      <text x={W / 2} y={H - 30} textAnchor="middle" fontSize="9" fill="var(--text3)">
        ← LEFT · offensive line · RIGHT →
      </text>
    </svg>
  )
}

/** Flag-football rush-lane selector (no line). */
export function RushLaneSelector({ value, onChange }: { value?: string | null; onChange: (v: string) => void }) {
  return <TapGroup options={RUSH_LANES} value={value} onChange={onChange} cols={5} />
}

/** Pass target-area grid (depth × side + behind-LOS). Values match the report's
 *  field-heat-map classifier ("Deep Left", "Short Middle", "Behind LOS", ...). */
const TARGET_ROWS = [{ depth: 'Deep', tag: 'Deep 20+' }, { depth: 'Intermediate', tag: 'Intermediate' }, { depth: 'Short', tag: 'Short 0-9' }]
export function TargetAreaGrid({ value, onChange }: { value?: string | null; onChange: (v: string) => void }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {TARGET_ROWS.map(r => (
        <div key={r.depth} style={{ display: 'grid', gridTemplateColumns: '68px 1fr 1fr 1fr', gap: 6, alignItems: 'stretch' }}>
          <div style={{ fontSize: 10, color: 'var(--text3)', fontWeight: 700, display: 'flex', alignItems: 'center', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{r.tag}</div>
          {['Left', 'Middle', 'Right'].map(c => {
            const label = `${r.depth} ${c}`
            return <button key={c} type="button" onClick={() => onChange(label)} style={sel(value === label)}>{c}</button>
          })}
        </div>
      ))}
      <button type="button" onClick={() => onChange('Behind LOS')} style={sel(value === 'Behind LOS')}>Behind LOS / Screen</button>
    </div>
  )
}

/** Touch route tree, routes drawn as tappable endpoints around a receiver origin. */
export function RouteTree({ value, onChange, customRoutes }: {
  value?: string | null; onChange: (v: string) => void; customRoutes?: string[]
}) {
  const all = [...ROUTES, ...(customRoutes || [])]
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
        {all.map(r => (
          <button key={r} type="button" onClick={() => onChange(r)} style={sel(value === r)}>{r}</button>
        ))}
      </div>
    </div>
  )
}

/** Realistic half-court shot chart. Tap the spot the shot came from: a marker drops
 *  and it resolves to the correct zone (Corner 3, Wing 3, Top 3, Paint, FT, Mid-range),
 *  which feeds the same 10-zone stats the report reads. Looks like a court, one tap. */
export function ShotZoneCourt({ value, onChange, onPoint }: {
  value?: string | null; onChange: (v: string) => void; onPoint?: (p: { x: number; y: number }) => void
}) {
  // Real HIGH-SCHOOL half-court proportions (NFHS): 50ft wide x 42ft half, 12ft lane,
  // 19ft to the FT line, 6ft FT circle, rim 5.25ft off the baseline, 19'9" 3pt arc.
  // ~10px/ft, viewBox 500x424.
  const W = 500, H = 424, RIMX = 250, RIMY = 367.5, R3 = 197.5
  const [pt, setPt] = useState<{ x: number; y: number } | null>(null)
  const ref = useRef<SVGSVGElement | null>(null)
  // Clear the dropped marker when the play resets (parent clears `value`).
  useEffect(() => { if (!value) setPt(null) }, [value])

  const classify = (x: number, y: number): string => {
    const dist = Math.hypot(x - RIMX, y - RIMY)
    if (dist > R3) {
      if (y >= 300 && (x <= 90 || x >= 410)) return x < RIMX ? 'corner3_left' : 'corner3_right'
      if (x < 175) return 'wing3_left'
      if (x > 325) return 'wing3_right'
      return 'top3'
    }
    if (x >= 190 && x <= 310 && y >= 230) return 'paint'
    if (Math.abs(x - RIMX) <= 60 && y >= 200 && y <= 270) return 'ft'
    if (x < 215) return 'mid_left'
    if (x > 285) return 'mid_right'
    return 'mid_center'
  }

  const tap = (e: any) => {
    const svg = ref.current; if (!svg) return
    const r = svg.getBoundingClientRect()
    const x = Math.max(3, Math.min(497, ((e.clientX - r.left) / r.width) * W))
    const y = Math.max(3, Math.min(420, ((e.clientY - r.top) / r.height) * H))
    setPt({ x, y })
    onChange(classify(x, y))
    // Normalised 0-100 court coordinates for the report's true shot-location map.
    onPoint?.({ x: Math.round((x / W) * 1000) / 10, y: Math.round((y / H) * 1000) / 10 })
  }

  const line = GOLD, faint = 'rgba(201,168,76,0.30)'
  return (
    <div>
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} onClick={tap}
        style={{ width: '100%', maxWidth: 380, height: 'auto', display: 'block', margin: '0 auto', touchAction: 'manipulation', cursor: 'crosshair' }}>
        <rect x={3} y={3} width={494} height={418} rx={6} fill="var(--bg3)" stroke={faint} />
        {/* paint / lane (12ft x 19ft, HS) */}
        <rect x={190} y={230} width={120} height={190} fill="rgba(201,168,76,0.07)" stroke={faint} />
        {/* free-throw circle (6ft radius) */}
        <circle cx={250} cy={230} r={60} fill="none" stroke={faint} />
        {/* backboard + rim */}
        <line x1={220} y1={380} x2={280} y2={380} stroke={line} strokeWidth={2.5} />
        <circle cx={250} cy={367.5} r={7.5} fill="none" stroke="var(--gold-light)" strokeWidth={2.5} />
        {/* three-point line: HS 19'9" arc, baseline to baseline */}
        <path d="M59.6 420 A197.5 197.5 0 0 1 250 170 A197.5 197.5 0 0 1 440.4 420" fill="none" stroke={line} strokeWidth={2} />
        {/* dropped shot marker */}
        {pt && (
          <g>
            <circle cx={pt.x} cy={pt.y} r={14} fill="rgba(201,168,76,0.25)" stroke={line} strokeWidth={2.5} />
            <circle cx={pt.x} cy={pt.y} r={5} fill={line} />
          </g>
        )}
      </svg>
      <div style={{ textAlign: 'center', marginTop: 8, fontSize: 13, fontWeight: 700, color: value ? GOLD : 'var(--text3)' }}>
        {value ? (ZONE_LABEL[value] || value) : 'Tap the court to mark the shot'}
      </div>
    </div>
  )
}

export { SHOT_ZONES }
