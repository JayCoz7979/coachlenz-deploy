'use client'
// True shot-location chart for the Live Game report. Plots every logged shot on a
// half-court at the exact spot the coach tapped, colored made (green) vs missed (red).
// Us (summary.live_shot_chart) are circles; opponent (summary.live_shot_chart_opp)
// are diamonds. Toggle Us / Opponent / Both. x/y are 0-100 court %.
import { useState, type CSSProperties } from 'react'

const GOLD = '#C9A84C', MADE = '#2d8c40', MISS = '#b45c5c'
// High-school half-court proportions (NFHS), ~10px/ft. Matches the logger court.
const W = 500, H = 424

function stat(pts: any[]) {
  const made = pts.filter(p => p.made).length
  return { made, att: pts.length, pct: pts.length ? Math.round((made / pts.length) * 100) : 0 }
}

export default function LiveShotChart({ summary }: { summary: any }) {
  const us: any[] = Array.isArray(summary?.live_shot_chart) ? summary.live_shot_chart : []
  const opp: any[] = Array.isArray(summary?.live_shot_chart_opp) ? summary.live_shot_chart_opp : []
  const hasUs = us.length > 0, hasOpp = opp.length > 0
  const [view, setView] = useState<'us' | 'opp' | 'both'>(hasUs && hasOpp ? 'both' : hasOpp ? 'opp' : 'us')
  if (!hasUs && !hasOpp) return null

  const u = stat(us), o = stat(opp)
  const card: CSSProperties = { background: '#2e2e2e', borderRadius: 6, padding: '20px 24px', border: '1px solid rgba(255,255,255,0.06)' }
  const faint = 'rgba(201,168,76,0.30)'
  const tbtn = (v: string, on: boolean): CSSProperties => ({
    padding: '5px 12px', fontSize: 11, fontWeight: 700, cursor: 'pointer', borderRadius: 4, border: 'none',
    letterSpacing: '.03em', background: on ? GOLD : 'rgba(255,255,255,.06)', color: on ? '#1c1c1c' : '#9a9a8e',
  })

  const dot = (p: any, team: 'us' | 'opp', i: number) => {
    const cx = (Number(p.x) / 100) * W, cy = (Number(p.y) / 100) * H
    if (!isFinite(cx) || !isFinite(cy)) return null
    // A gold ring marks a shot that drew a foul (and-1 or fouled attempt).
    const ring = p.fouled ? <circle cx={cx} cy={cy} r={12.5} fill="none" stroke={GOLD} strokeWidth={1.5} /> : null
    const mark = team === 'us'
      ? (p.made
          ? <circle cx={cx} cy={cy} r={8} fill="rgba(45,140,64,0.85)" stroke="#eafaee" strokeWidth={1.5} />
          : <g stroke={MISS} strokeWidth={3}>
              <line x1={cx - 6} y1={cy - 6} x2={cx + 6} y2={cy + 6} /><line x1={cx - 6} y1={cy + 6} x2={cx + 6} y2={cy - 6} />
            </g>)
      : (() => { const d = 9, path = `M${cx} ${cy - d} L${cx + d} ${cy} L${cx} ${cy + d} L${cx - d} ${cy} Z`
          return p.made
            ? <path d={path} fill="rgba(45,140,64,0.8)" stroke="#eafaee" strokeWidth={1.5} />
            : <path d={path} fill="none" stroke={MISS} strokeWidth={2.5} /> })()
    return <g key={team + i}>{ring}{mark}</g>
  }

  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
        <h3 style={{ fontSize: 14, fontWeight: 700, color: '#f8f6f0', letterSpacing: '0.04em', margin: 0 }}>Shot Locations</h3>
        <span style={{ fontSize: 11, color: '#7a7a6e' }}>every shot, where it came from</span>
        {hasUs && hasOpp && (
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
            <button onClick={() => setView('us')} style={tbtn('us', view === 'us')}>Us</button>
            <button onClick={() => setView('opp')} style={tbtn('opp', view === 'opp')}>Opponent</button>
            <button onClick={() => setView('both')} style={tbtn('both', view === 'both')}>Both</button>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', gap: 16, marginBottom: 8, fontSize: 12 }}>
        {(view === 'us' || view === 'both') && hasUs && <span style={{ color: '#d8d8cc' }}>Us <b style={{ color: MADE }}>{u.made}</b>/{u.att} · <b style={{ color: GOLD }}>{u.pct}%</b></span>}
        {(view === 'opp' || view === 'both') && hasOpp && <span style={{ color: '#d8d8cc' }}>Opponent <b style={{ color: MADE }}>{o.made}</b>/{o.att} · <b style={{ color: GOLD }}>{o.pct}%</b></span>}
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', maxWidth: 400, height: 'auto', display: 'block', margin: '0 auto' }}>
        <rect x={3} y={3} width={494} height={418} rx={6} fill="#242018" stroke={faint} />
        <rect x={190} y={230} width={120} height={190} fill="rgba(201,168,76,0.06)" stroke={faint} />
        <circle cx={250} cy={230} r={60} fill="none" stroke={faint} />
        <line x1={220} y1={380} x2={280} y2={380} stroke={GOLD} strokeWidth={2.5} />
        <circle cx={250} cy={367.5} r={7.5} fill="none" stroke="#e2c06a" strokeWidth={2.5} />
        <path d="M59.6 420 A197.5 197.5 0 0 1 250 170 A197.5 197.5 0 0 1 440.4 420" fill="none" stroke={GOLD} strokeWidth={2} />
        {(view === 'us' || view === 'both') && us.map((p, i) => dot(p, 'us', i))}
        {(view === 'opp' || view === 'both') && opp.map((p, i) => dot(p, 'opp', i))}
      </svg>

      <div style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 10, fontSize: 11, color: '#9a9a8e', flexWrap: 'wrap' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={{ width: 10, height: 10, borderRadius: '50%', background: MADE, display: 'inline-block' }} /> Made</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={{ color: MISS, fontWeight: 800 }}>✕</span> Missed</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={{ display: 'inline-block', width: 11, height: 11, borderRadius: '50%', border: '1.5px solid ' + GOLD }} /> Drew foul</span>
        {hasUs && hasOpp && <span style={{ color: '#7a7a6e' }}>● circle = us · ◆ diamond = opponent</span>}
      </div>
    </div>
  )
}
