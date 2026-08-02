'use client'
// True shot-location chart for the Live Game report. Plots every logged shot on a
// half-court at the exact spot the coach tapped, colored made (green) vs missed (red).
// Data is summary.live_shot_chart = [{x, y, made, jersey}] (x/y are 0-100 court %).
// No backend call — the points ride on the report summary.
import { type CSSProperties } from 'react'

const GOLD = '#C9A84C', MADE = '#2d8c40', MISS = '#b45c5c'
const W = 300, H = 284

export default function LiveShotChart({ summary }: { summary: any }) {
  const pts: any[] = Array.isArray(summary?.live_shot_chart) ? summary.live_shot_chart : []
  if (!pts.length) return null

  const made = pts.filter(p => p.made).length
  const pct = Math.round((made / pts.length) * 100)
  const card: CSSProperties = { background: '#2e2e2e', borderRadius: 6, padding: '20px 24px', border: '1px solid rgba(255,255,255,0.06)' }
  const faint = 'rgba(201,168,76,0.30)'

  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
        <h3 style={{ fontSize: 14, fontWeight: 700, color: '#f8f6f0', letterSpacing: '0.04em', margin: 0 }}>Shot Locations</h3>
        <span style={{ fontSize: 11, color: '#7a7a6e' }}>every shot, where it came from</span>
        <span style={{ marginLeft: 'auto', fontSize: 12, color: '#d8d8cc' }}>
          <b style={{ color: MADE }}>{made}</b>/{pts.length} made · <b style={{ color: GOLD }}>{pct}%</b>
        </span>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', maxWidth: 360, height: 'auto', display: 'block', margin: '0 auto' }}>
        <rect x={14} y={14} width={272} height={258} rx={5} fill="#242018" stroke={faint} />
        <rect x={112} y={150} width={76} height={122} fill="rgba(201,168,76,0.06)" stroke={faint} />
        <circle cx={150} cy={150} r={30} fill="none" stroke={faint} />
        <line x1={132} y1={256} x2={168} y2={256} stroke={GOLD} strokeWidth={2} />
        <circle cx={150} cy={248} r={7} fill="none" stroke="#e2c06a" strokeWidth={2} />
        <path d="M34 272 L34 183 C34 90 266 90 266 183 L266 272" fill="none" stroke={GOLD} strokeWidth={1.5} />
        {pts.map((p, i) => {
          const cx = (Number(p.x) / 100) * W, cy = (Number(p.y) / 100) * H
          if (!isFinite(cx) || !isFinite(cy)) return null
          return p.made
            ? <circle key={i} cx={cx} cy={cy} r={5.5} fill="rgba(45,140,64,0.85)" stroke="#eafaee" strokeWidth={1} />
            : <g key={i} stroke={MISS} strokeWidth={2}>
                <line x1={cx - 4} y1={cy - 4} x2={cx + 4} y2={cy + 4} />
                <line x1={cx - 4} y1={cy + 4} x2={cx + 4} y2={cy - 4} />
              </g>
        })}
      </svg>

      <div style={{ display: 'flex', gap: 18, justifyContent: 'center', marginTop: 10, fontSize: 11, color: '#9a9a8e' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={{ width: 10, height: 10, borderRadius: '50%', background: MADE, display: 'inline-block' }} /> Made</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={{ color: MISS, fontWeight: 800 }}>✕</span> Missed</span>
      </div>
    </div>
  )
}
