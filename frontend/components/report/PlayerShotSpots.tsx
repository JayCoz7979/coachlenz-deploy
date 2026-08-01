'use client'
import { type CSSProperties } from 'react'

// §12 Map 2 — individual player shot spots (basketball). For each notable scorer,
// their eFG by zone with hot (red) / cold (green) zones flagged. Rendered from the
// report's summary.player_shot_zones — same zone reads as the team shot chart, no
// fabricated court coordinates.

interface Zone { zone: string; attempts: number; made: number; efg_pct: number }
interface PlayerZones { jersey: string; shots: number; zones: Zone[]; hot_zones: string[]; cold_zones: string[] }

// Player-layer eFG bands: red = strength (worry), green = weakness (send them here).
function band(efg: number): { color: string } {
  if (efg >= 55) return { color: '#c0392b' }
  if (efg >= 35) return { color: '#c9a227' }
  return { color: '#1f7a3a' }
}

export default function PlayerShotSpots({ summary }: { summary: any }) {
  const players: PlayerZones[] = summary?.player_shot_zones || []
  const card: CSSProperties = { background: '#2e2e2e', borderRadius: 6, padding: '20px 24px', border: '1px solid rgba(255,255,255,0.06)' }
  if (!players.length) return null

  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
        <h3 style={{ fontSize: 14, fontWeight: 700, color: '#f8f6f0', letterSpacing: '0.04em' }}>Player Shot Spots</h3>
        <span style={{ fontSize: 11, color: '#7a7a6e' }}>where each scorer is hot &amp; cold</span>
      </div>
      <div style={{ fontSize: 10, color: '#7a7a6e', margin: '8px 0 12px' }}>
        Chips are their zones by eFG — red = they shoot it well (take it away), green = weak (make them shoot here). Size = volume.
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {players.map(p => {
          const maxAtt = Math.max(1, ...p.zones.map(z => z.attempts))
          return (
            <div key={p.jersey} style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
              <div style={{
                width: 40, height: 40, flexShrink: 0, borderRadius: '50%', background: '#3a3a30',
                color: '#f0eee6', display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontWeight: 700, fontSize: 14,
              }}>#{p.jersey}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {p.zones.map(z => {
                    const hot = p.hot_zones.includes(z.zone)
                    const cold = p.cold_zones.includes(z.zone)
                    const scale = 0.8 + 0.4 * (z.attempts / maxAtt)   // size by volume
                    return (
                      <span key={z.zone} title={`${z.made}/${z.attempts} · ${z.efg_pct}% eFG`}
                        style={{
                          display: 'inline-flex', alignItems: 'center', gap: 5,
                          background: band(z.efg_pct).color, color: '#fff', borderRadius: 6,
                          padding: `${Math.round(3 * scale)}px ${Math.round(8 * scale)}px`,
                          fontSize: Math.round(11 * scale), fontWeight: 600,
                          border: hot ? '2px solid #f0c0b0' : cold ? '2px solid #a8d8b8' : '2px solid transparent',
                        }}>
                        {hot ? '🔥 ' : cold ? '❄ ' : ''}{z.zone} <span style={{ opacity: 0.85 }}>{z.efg_pct}%</span>
                      </span>
                    )
                  })}
                </div>
                <div style={{ fontSize: 10, color: '#7a7a6e', marginTop: 4 }}>{p.shots} shots tracked</div>
              </div>
            </div>
          )
        })}
      </div>
      <div style={{ fontSize: 10, color: '#7a7a6e', marginTop: 10 }}>Single-camera, jersey-based — only players with a legible number are mapped.</div>
    </div>
  )
}
