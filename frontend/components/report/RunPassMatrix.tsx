'use client'
import { type CSSProperties } from 'react'

// §12 Map 4 — Run/Pass tendency matrix (football). Rows = down, columns = hash,
// each cell colored by run% (run-heavy red -> balanced grey -> pass-heavy purple).
// Rendered from the report's already-computed summary.offense.run_pass_matrix — no
// backend call. Thin cells (below the sample floor) show their number but stay grey.

interface Cell {
  total: number
  run: number
  pass: number
  run_pct: number | null
  low_sample: boolean
  band: string
  color: string
  band_label?: string
}
interface Matrix {
  rows: string[]
  cols: string[]
  cells: Record<string, Record<string, Cell>>
  min_sample: number
}

const LEGEND: [string, string][] = [
  ['#c0392b', 'Run heavy'],
  ['#d98c30', 'Run lean'],
  ['#8a8a80', 'Balanced'],
  ['#3b6fb0', 'Pass lean'],
  ['#7a4fb0', 'Pass heavy'],
]

// Neutral / grey fills read better with dark text; the strong bands take white.
const _isLight = (band: string) => band === 'balanced' || band === 'none'

export default function RunPassMatrix({ summary }: { summary: any }) {
  const m: Matrix | undefined = summary?.offense?.run_pass_matrix
  const card: CSSProperties = { background: '#2e2e2e', borderRadius: 6, padding: '20px 24px', border: '1px solid rgba(255,255,255,0.06)' }

  const hasCells = m && m.rows?.length && m.cols?.length
  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
        <h3 style={{ fontSize: 14, fontWeight: 700, color: '#f8f6f0', letterSpacing: '0.04em' }}>Run / Pass Matrix</h3>
        <span style={{ fontSize: 11, color: '#7a7a6e' }}>what they call, by down &amp; hash</span>
      </div>

      {!hasCells ? (
        <div style={{ fontSize: 12, color: '#7ea88a', background: '#123a1e', border: '1px solid rgba(45,140,64,0.25)', borderRadius: 6, padding: 16, lineHeight: 1.6, marginTop: 12 }}>
          Not enough down-and-hash detail on this film yet. Run a full or DEEP breakdown of the whole game and the matrix fills in.
        </div>
      ) : (
        <>
          <div style={{ fontSize: 10, color: '#7a7a6e', margin: '10px 0 8px' }}>
            Number = run share of that down &amp; hash. Grey = fewer than {m!.min_sample} plays (too thin to call).
          </div>
          <div style={{ display: 'inline-grid', gridTemplateColumns: `56px repeat(${m!.cols.length}, minmax(72px, 1fr))`, gap: 4 }}>
            <div />
            {m!.cols.map(c => (
              <div key={c} style={{ fontSize: 10, color: '#7ea88a', textAlign: 'center', textTransform: 'uppercase', letterSpacing: '0.05em', paddingBottom: 2 }}>{c}</div>
            ))}
            {m!.rows.map(row => (
              <div key={row} style={{ display: 'contents' }}>
                <div style={{ fontSize: 11, color: '#d8d8cc', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingRight: 6, fontWeight: 700 }}>{row}</div>
                {m!.cols.map(col => {
                  const c = m!.cells[row]?.[col]
                  if (!c || c.total === 0) {
                    return <div key={col} style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 4, minHeight: 46 }} />
                  }
                  const bg = c.low_sample ? 'rgba(255,255,255,0.06)' : c.color
                  const fg = c.low_sample || _isLight(c.band) ? '#e8e6dd' : '#fff'
                  return (
                    <div key={col} title={`${c.run} run / ${c.pass} pass${c.low_sample ? ' (small sample)' : ` - ${c.band_label}`}`}
                      style={{ background: bg, borderRadius: 4, minHeight: 46, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', opacity: c.low_sample ? 0.55 : 1 }}>
                      <span style={{ fontSize: 16, fontWeight: 700, color: fg, fontFamily: 'var(--font-bebas)' }}>{Math.round(c.run_pct ?? 0)}%</span>
                      <span style={{ fontSize: 8, color: fg, opacity: 0.85 }}>{c.total} plays</span>
                    </div>
                  )
                })}
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 12 }}>
            {LEGEND.map(([color, label]) => (
              <span key={label} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 10, color: '#9a9a8e' }}>
                <span style={{ width: 12, height: 12, borderRadius: 3, background: color, display: 'inline-block' }} /> {label}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
