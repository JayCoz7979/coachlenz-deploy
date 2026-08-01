'use client'
import { type CSSProperties } from 'react'

// §12 Map 5 — field-zone run-direction map (football). Weighted directional arrows
// on a half-field: bold = dominant (≥55%), thin = secondary, faint = rare. Rendered
// from summary.offense.run_direction_analysis — aggregate direction %, not tracked
// player paths, so no fabricated coordinates.

const GOLD = '#C9A84C'

export default function RunDirectionArrows({ summary }: { summary: any }) {
  const rda = summary?.offense?.run_direction_analysis || {}
  const card: CSSProperties = { background: '#2e2e2e', borderRadius: 6, padding: '20px 24px', border: '1px solid rgba(255,255,255,0.06)' }
  if ((rda.total_runs || 0) < 6) return null

  // Ball at bottom-center; four arrows fan upfield. Angle in degrees from vertical.
  const ball = { x: 160, y: 158 }
  const arrows: { label: string; pct: number; angle: number }[] = [
    { label: 'Left', pct: rda.left_pct ?? 0, angle: -52 },
    { label: 'Inside', pct: rda.inside_pct ?? 0, angle: -16 },
    { label: 'Outside', pct: rda.outside_pct ?? 0, angle: 16 },
    { label: 'Right', pct: rda.right_pct ?? 0, angle: 52 },
  ].filter(a => a.pct != null)

  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
        <h3 style={{ fontSize: 14, fontWeight: 700, color: '#f8f6f0', letterSpacing: '0.04em' }}>Run Direction</h3>
        <span style={{ fontSize: 11, color: '#7a7a6e' }}>where they run, weighted by volume</span>
      </div>
      <div style={{ fontSize: 10, color: '#7a7a6e', margin: '8px 0 10px' }}>
        Bold gold arrow = dominant (55%+). {rda.total_runs} runs charted.
      </div>
      <svg viewBox="0 0 320 180" style={{ width: '100%', maxWidth: 360, display: 'block' }}>
        {/* field */}
        <rect x="0" y="0" width="320" height="180" rx="6" fill="#123a1e" stroke="rgba(45,140,64,0.3)" />
        {[40, 80, 120].map(y => <line key={y} x1="0" y1={y} x2="320" y2={y} stroke="rgba(255,255,255,0.06)" />)}
        {arrows.map(a => {
          const dominant = a.pct >= 55
          const w = Math.max(0, Math.min(1, a.pct / 100))
          const len = 40 + 78 * w
          const rad = (a.angle - 90) * Math.PI / 180   // -90 so 0° points up
          const ex = ball.x + len * Math.cos(rad)
          const ey = ball.y + len * Math.sin(rad)
          const color = dominant ? GOLD : '#7ea88a'
          const sw = 2 + 7 * w
          return (
            <g key={a.label} opacity={0.35 + 0.65 * w}>
              <line x1={ball.x} y1={ball.y} x2={ex} y2={ey} stroke={color} strokeWidth={sw} strokeLinecap="round" />
              {/* arrowhead */}
              <polygon
                points={`0,-${5 + sw},${9 + sw},0,0,${5 + sw}`}
                fill={color}
                transform={`translate(${ex},${ey}) rotate(${a.angle - 90})`}
              />
              <text x={ex} y={ey - 8} fill={color} fontSize="11" fontWeight={dominant ? 700 : 400}
                textAnchor="middle">{a.label} {Math.round(a.pct)}%</text>
            </g>
          )
        })}
        <circle cx={ball.x} cy={ball.y} r="5" fill="#f8f6f0" />
      </svg>
    </div>
  )
}
