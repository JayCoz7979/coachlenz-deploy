'use client'
/**
 * Live Game Play Logger, touch-optimized selectors.
 * Pure presentational components that consume the existing CoachLenz CSS design
 * tokens (var(--gold), var(--bg3), ...). They do not import or alter any global
 * styles, so the live site is untouched. All tap targets are >= 44px.
 */
import { type CSSProperties } from 'react'
import { GAPS, RUSH_LANES, ROUTES, SHOT_ZONES, gapLabel, type TermSystem } from './fields'

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

/** Half-court shot-zone selector (touch SVG). Tap a zone to log the shot. */
export function ShotZoneCourt({ value, onChange }: { value?: string | null; onChange: (v: string) => void }) {
  const W = 300, H = 280
  const fill = (v: string) => (value === v ? 'rgba(201,168,76,0.30)' : 'var(--bg3)')
  const stroke = (v: string) => (value === v ? GOLD : 'var(--border2)')
  const txt = (v: string) => (value === v ? GOLD : 'var(--text3)')
  const Z = ({ v, d, cx, cy, label }: { v: string; d: string; cx: number; cy: number; label: string }) => (
    <g onClick={() => onChange(v)} style={{ cursor: 'pointer' }}>
      <path d={d} fill={fill(v)} stroke={stroke(v)} strokeWidth={1.5} />
      <text x={cx} y={cy} textAnchor="middle" fontSize="9" fontWeight="700" fill={txt(v)}>{label}</text>
    </g>
  )
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', maxWidth: 340, height: 'auto', touchAction: 'manipulation' }}>
      {/* baseline at bottom, half-court arc toward top */}
      {/* corners */}
      <Z v="corner3_left" d="M4 120 L58 120 L58 276 L4 276 Z" cx={31} cy={210} label="Cnr 3 L" />
      <Z v="corner3_right" d="M242 120 L296 120 L296 276 L242 276 Z" cx={269} cy={210} label="Cnr 3 R" />
      {/* wings */}
      <Z v="wing3_left" d="M4 20 L58 20 L58 120 L4 120 Z" cx={31} cy={70} label="Wing 3 L" />
      <Z v="wing3_right" d="M242 20 L296 20 L296 120 L242 120 Z" cx={269} cy={70} label="Wing 3 R" />
      {/* top of key 3 */}
      <Z v="top3" d="M58 8 L242 8 L242 70 L58 70 Z" cx={150} cy={38} label="Top 3" />
      {/* mid-range left / right / center */}
      <Z v="mid_left" d="M58 70 L104 70 L104 200 L58 200 Z" cx={81} cy={140} label="Mid L" />
      <Z v="mid_right" d="M196 70 L242 70 L242 200 L196 200 Z" cx={219} cy={140} label="Mid R" />
      <Z v="mid_center" d="M104 70 L196 70 L196 118 L104 118 Z" cx={150} cy={96} label="Mid C" />
      {/* free throw */}
      <Z v="ft" d="M104 118 L196 118 L196 158 L104 158 Z" cx={150} cy={140} label="FT" />
      {/* paint */}
      <Z v="paint" d="M104 158 L196 158 L196 276 L104 276 Z" cx={150} cy={220} label="Paint" />
      {/* hoop */}
      <circle cx={150} cy={262} r={7} fill="none" stroke="var(--gold-light)" strokeWidth={2} />
    </svg>
  )
}

export { SHOT_ZONES }
