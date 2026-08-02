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
export function ShotZoneCourt({ value, onChange }: { value?: string | null; onChange: (v: string) => void }) {
  const W = 300, H = 284, RIMX = 150, RIMY = 246, R3 = 132
  const [pt, setPt] = useState<{ x: number; y: number } | null>(null)
  const ref = useRef<SVGSVGElement | null>(null)
  // Clear the dropped marker when the play resets (parent clears `value`).
  useEffect(() => { if (!value) setPt(null) }, [value])

  const classify = (x: number, y: number): string => {
    const dist = Math.hypot(x - RIMX, y - RIMY)
    if (y >= 183 && (x <= 34 || x >= 266)) return x < RIMX ? 'corner3_left' : 'corner3_right'
    if (dist > R3) { if (x < 112) return 'wing3_left'; if (x > 188) return 'wing3_right'; return 'top3' }
    if (x >= 112 && x <= 188 && y >= 150) return 'paint'
    if (Math.abs(x - RIMX) <= 34 && y >= 120 && y <= 172) return 'ft'
    if (x < 118) return 'mid_left'
    if (x > 182) return 'mid_right'
    return 'mid_center'
  }

  const tap = (e: any) => {
    const svg = ref.current; if (!svg) return
    const r = svg.getBoundingClientRect()
    const x = Math.max(14, Math.min(286, ((e.clientX - r.left) / r.width) * W))
    const y = Math.max(14, Math.min(272, ((e.clientY - r.top) / r.height) * H))
    setPt({ x, y })
    onChange(classify(x, y))
  }

  const line = GOLD, faint = 'rgba(201,168,76,0.30)'
  return (
    <div>
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} onClick={tap}
        style={{ width: '100%', maxWidth: 360, height: 'auto', display: 'block', margin: '0 auto', touchAction: 'manipulation', cursor: 'crosshair' }}>
        <rect x={14} y={14} width={272} height={258} rx={5} fill="var(--bg3)" stroke={faint} />
        {/* paint / lane */}
        <rect x={112} y={150} width={76} height={122} fill="rgba(201,168,76,0.07)" stroke={faint} />
        {/* free-throw circle */}
        <circle cx={150} cy={150} r={30} fill="none" stroke={faint} />
        {/* backboard + rim */}
        <line x1={132} y1={256} x2={168} y2={256} stroke={line} strokeWidth={2} />
        <circle cx={150} cy={248} r={7} fill="none" stroke="var(--gold-light)" strokeWidth={2} />
        {/* three-point line: corners straight up, then arc over the top */}
        <path d="M34 272 L34 183 C34 90 266 90 266 183 L266 272" fill="none" stroke={line} strokeWidth={1.5} />
        {/* dropped shot marker */}
        {pt && (
          <g>
            <circle cx={pt.x} cy={pt.y} r={9} fill="rgba(201,168,76,0.25)" stroke={line} strokeWidth={2} />
            <circle cx={pt.x} cy={pt.y} r={3} fill={line} />
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
