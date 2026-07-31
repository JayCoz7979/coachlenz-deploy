'use client'
import { type CSSProperties } from 'react'

// §12 Map 3 — Turnover map (basketball). Single-camera film has no court
// coordinates for turnovers, so instead of a fake half-court plot we cluster by
// the real how/where signal (transition vs the half-court action they ran) and
// flag the biggest cluster: force them into it. Rendered from summary.turnover_map.

interface Zone { zone: string; count: number; pct: number }
interface TurnoverMap { total: number; zones: Zone[]; top_cluster: string | null; force_here: string | null }

export default function TurnoverMap({ summary }: { summary: any }) {
  const tm: TurnoverMap | undefined = summary?.turnover_map
  const card: CSSProperties = { background: '#2e2e2e', borderRadius: 6, padding: '20px 24px', border: '1px solid rgba(255,255,255,0.06)' }

  const zones = tm?.zones || []
  const maxCount = Math.max(1, ...zones.map(z => z.count))

  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
        <h3 style={{ fontSize: 14, fontWeight: 700, color: '#f8f6f0', letterSpacing: '0.04em' }}>Turnovers</h3>
        <span style={{ fontSize: 11, color: '#7a7a6e' }}>where they give it away</span>
      </div>

      {zones.length === 0 ? (
        <div style={{ fontSize: 12, color: '#7ea88a', background: '#123a1e', border: '1px solid rgba(45,140,64,0.25)', borderRadius: 6, padding: 16, lineHeight: 1.6, marginTop: 12 }}>
          No turnovers were tracked on this film yet. Run a full or DEEP breakdown of the whole game and this fills in.
        </div>
      ) : (
        <>
          {tm!.force_here && (
            <div style={{ margin: '12px 0', fontSize: 13, color: '#f0c0b0', background: 'rgba(192,57,43,0.12)', border: '1px solid rgba(192,57,43,0.35)', borderRadius: 6, padding: '10px 14px' }}>
              🎯 <b>{tm!.force_here}</b>
            </div>
          )}
          <div style={{ fontSize: 10, color: '#7a7a6e', margin: '10px 0 8px' }}>{tm!.total} turnovers, grouped by what they were running.</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {zones.map((z, i) => {
              const top = i === 0 && !!tm!.force_here
              return (
                <div key={z.zone} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ width: 140, flexShrink: 0, fontSize: 11, color: top ? '#f0c0b0' : '#d8d8cc', textAlign: 'right', fontWeight: top ? 700 : 400 }}>
                    {top ? '🎯 ' : ''}{z.zone}
                  </div>
                  <div style={{ flex: 1, height: 20, background: 'rgba(255,255,255,0.04)', borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${Math.max(6, (z.count / maxCount) * 100)}%`, background: top ? '#c0392b' : '#8a7a4a', borderRadius: 3 }} />
                  </div>
                  <div style={{ width: 84, flexShrink: 0, display: 'flex', justifyContent: 'flex-end', gap: 8, fontSize: 11 }}>
                    <span style={{ color: '#d8d8cc' }}>{z.count}</span>
                    <span style={{ color: '#7a7a6e', width: 42, textAlign: 'right' }}>{z.pct}%</span>
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
