'use client'
import { type CSSProperties } from 'react'

// Basketball shot heat map + key players, rendered from the report's already-computed
// tendency summary (shot_zone_map / shooting_overview / player_tendencies). No backend
// call — the data is already on the report. Single-camera film is honest: zones and
// players with no readable data simply don't appear.

const GOLD = '#C9A84C'

function _mix(a: string, b: string, t: number) {
  const pa = [parseInt(a.slice(1, 3), 16), parseInt(a.slice(3, 5), 16), parseInt(a.slice(5, 7), 16)]
  const pb = [parseInt(b.slice(1, 3), 16), parseInt(b.slice(3, 5), 16), parseInt(b.slice(5, 7), 16)]
  const c = pa.map((x, i) => Math.round(x + (pb[i] - x) * Math.max(0, Math.min(1, t))))
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`
}
// bad -> good ramp (red -> gold -> green) for FG%.
function _quality(t: number) {
  const c = Math.max(0, Math.min(1, t))
  return c < 0.5 ? _mix('#b45c5c', GOLD, c * 2) : _mix(GOLD, '#2d8c40', (c - 0.5) * 2)
}

function roleLabel(p: any): string {
  const t = p.shot_tendency
  if (t === 'perimeter') return 'perimeter shooter'
  if (t === 'paint_attacker') return 'paint attacker'
  if (t === 'mid_range') return 'mid-range'
  if (p.possession_role === 'initiator') return 'primary initiator'
  return 'role player'
}

export default function BasketballShotChart({ summary }: { summary: any }) {
  const szm = summary?.shot_zone_map || {}
  const zones: Record<string, any> = szm.zones || {}
  const so = summary?.shooting_overview || {}
  const pt = summary?.player_tendencies || {}

  const zoneRows = Object.entries(zones).sort((a: any, b: any) => (b[1].attempts || 0) - (a[1].attempts || 0))
  const maxAtt = Math.max(1, ...zoneRows.map(([, z]: any) => z.attempts || 0))
  const hasZones = zoneRows.length > 0

  // Top offense players by usage (by_player is already ranked; keep the offense side).
  const players: [string, any][] = Object.entries(pt.by_player || {})
    .filter(([k, v]: any) => (v.team || (k.split('#')[0])) === 'offense')
    .slice(0, 5)

  const card: CSSProperties = { background: '#2e2e2e', borderRadius: 6, padding: '20px 24px', border: '1px solid rgba(255,255,255,0.06)' }

  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
        <h3 style={{ fontSize: 14, fontWeight: 700, color: '#f8f6f0', letterSpacing: '0.04em' }}>Shot Chart</h3>
        <span style={{ fontSize: 11, color: '#7a7a6e' }}>where they score, and how well</span>
      </div>

      {hasZones ? (
        <>
          {/* Dual-encoded legend: bar length = volume, bar color = FG% (both shown at once). */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', margin: '12px 0 6px', fontSize: 10, color: '#9a9a8e' }}>
            <span><b style={{ color: '#d8d8cc' }}>Bar length</b> = shot volume</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <b style={{ color: '#d8d8cc' }}>Color</b> = FG%
              <span style={{ display: 'inline-block', width: 60, height: 8, borderRadius: 2, background: 'linear-gradient(90deg,#b45c5c,#C9A84C,#2d8c40)' }} />
              <span>cold → hot</span>
            </span>
          </div>
          <div style={{ fontSize: 10, color: '#7a7a6e', marginBottom: 14 }}>Empty zones had no readable shots on this film.</div>

          {/* Zone bars — length is volume, fill color is FG% */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {zoneRows.map(([zone, z]: any) => {
              const w = (z.attempts || 0) / maxAtt
              const color = _quality((z.fg_pct || 0) / 100)
              return (
                <div key={zone} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ width: 140, flexShrink: 0, fontSize: 11, color: '#d8d8cc', textAlign: 'right' }}>{zone}</div>
                  <div style={{ flex: 1, height: 20, background: 'rgba(255,255,255,0.04)', borderRadius: 3, position: 'relative', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${Math.max(6, w * 100)}%`, background: color, borderRadius: 3 }} />
                  </div>
                  {/* Numbers live outside the bar so they read cleanly over any fill color:
                      volume (made/attempts + share of all shots) and FG%. */}
                  <div style={{ width: 132, flexShrink: 0, display: 'flex', justifyContent: 'flex-end', gap: 8, fontSize: 11 }}>
                    <span style={{ color: '#d8d8cc' }}>{z.made}/{z.attempts}</span>
                    <span style={{ color: '#7a7a6e' }}>{z.pct_of_all_shots}%</span>
                    <span style={{ width: 42, textAlign: 'right', fontWeight: 700, color }}>{z.fg_pct}%</span>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Callouts */}
          <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', marginTop: 14, fontSize: 11, color: '#b8b8aa' }}>
            {szm.hottest_zone && <span>🔥 Hottest: <b style={{ color: '#2d8c40' }}>{szm.hottest_zone}</b></span>}
            {szm.most_frequent_zone && <span>📍 Most shots: <b style={{ color: GOLD }}>{szm.most_frequent_zone}</b></span>}
            {typeof szm.left_side_pct === 'number' && <span>Left {szm.left_side_pct}% · Right {szm.right_side_pct}%</span>}
            {typeof szm.corner_three_pct === 'number' && szm.corner_three_pct > 0 && <span>Corner 3s {szm.corner_three_pct}%</span>}
            {so.three_point && <span>3PT {so.three_point.made}/{so.three_point.attempts} ({so.three_point.fg_pct}%)</span>}
          </div>
        </>
      ) : (
        <div style={{ fontSize: 12, color: '#7ea88a', background: '#123a1e', border: '1px solid rgba(45,140,64,0.25)', borderRadius: 6, padding: 16, lineHeight: 1.6, marginTop: 12 }}>
          No shot-zone detail was readable on this film yet — usually a thin or low-confidence breakdown. Run a full or DEEP breakdown of the whole game and the shot chart fills in with real zones.
        </div>
      )}

      {/* Key players */}
      {players.length > 0 && (
        <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
            <h4 style={{ fontSize: 13, fontWeight: 700, color: '#f8f6f0', letterSpacing: '0.04em' }}>Key Players — Who to Stop</h4>
            {typeof pt?.coverage?.pct === 'number' && <span style={{ fontSize: 10, color: '#7a7a6e' }}>{pt.coverage.pct}% of possessions had a readable jersey</span>}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {players.map(([key, p], i) => (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 12, background: 'rgba(255,255,255,0.03)', borderRadius: 6, padding: '8px 12px' }}>
                <div style={{ width: 34, height: 34, flexShrink: 0, borderRadius: '50%', background: i === 0 ? GOLD : '#3a3a30', color: i === 0 ? '#1c1c1c' : '#d8d8cc', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 13 }}>
                  #{p.jersey}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, color: '#f0eee6', fontWeight: 600 }}>
                    #{p.jersey} <span style={{ color: '#9a9a8e', fontWeight: 400 }}>· {roleLabel(p)}</span>
                    {p.perimeter_dependency_flag && <span style={{ marginLeft: 8, fontSize: 10, color: '#e0a050' }}>chase off the 3</span>}
                  </div>
                  <div style={{ fontSize: 11, color: '#7a7a6e' }}>
                    {p.shot_attempts > 0 ? `${p.shot_attempts} shots · ${p.fg_pct}% FG` : 'creator'}
                    {p.three_attempts > 0 ? ` · ${p.three_attempts} 3PA (${p.three_pct}%)` : ''}
                    {p.turnovers > 0 ? ` · ${p.turnovers} TO` : ''}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 10, color: '#7a7a6e', marginTop: 8 }}>Single-camera, jersey-based — only players with a legible number are tracked.</div>
        </div>
      )}
    </div>
  )
}
