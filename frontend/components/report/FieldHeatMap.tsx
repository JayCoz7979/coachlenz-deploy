'use client'
import { useState, type CSSProperties } from 'react'

// Football field heat maps, rendered from the report's already-computed tendency
// summary (offense.pass_distribution / run_gap_analysis / run_direction_analysis).
// No backend call — the data is already on the report. One metric at a time is
// encoded by a single sequential ramp so the "where" and the "how well" both read
// at a glance. Single-camera film is honest: zones with no data stay empty.

type Metric = 'volume' | 'success' | 'yards'

const GOLD = '#C9A84C'

// ── color helpers ───────────────────────────────────────────────────────────
function _mix(a: string, b: string, t: number) {
  const pa = [parseInt(a.slice(1, 3), 16), parseInt(a.slice(3, 5), 16), parseInt(a.slice(5, 7), 16)]
  const pb = [parseInt(b.slice(1, 3), 16), parseInt(b.slice(3, 5), 16), parseInt(b.slice(5, 7), 16)]
  const c = pa.map((x, i) => Math.round(x + (pb[i] - x) * Math.max(0, Math.min(1, t))))
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`
}
// bad -> good ramp (red -> gold -> green), used for success% and avg yards.
function _quality(t: number) {
  const c = Math.max(0, Math.min(1, t))
  return c < 0.5 ? _mix('#b45c5c', GOLD, c * 2) : _mix(GOLD, '#2d8c40', (c - 0.5) * 2)
}

type Cell = { count: number; yards: number; succ: number }
const _val = (cell: Cell | undefined, m: Metric) => {
  if (!cell || !cell.count) return 0
  if (m === 'volume') return cell.count
  if (m === 'success') return cell.succ / cell.count
  return cell.yards / cell.count
}
function _style(cell: Cell | undefined, m: Metric, maxVol: number) {
  const c = cell?.count || 0
  if (!c) return { background: 'rgba(255,255,255,0.03)', color: '#5a5a52', border: '1px solid rgba(255,255,255,0.05)' }
  let bg: string
  if (m === 'volume') bg = `rgba(201,168,76,${(0.15 + 0.75 * (maxVol ? c / maxVol : 0)).toFixed(2)})`
  else if (m === 'success') bg = _quality(((cell!.succ / c) - 35) / 35)
  else bg = _quality((cell!.yards / c) / 6)
  const light = m === 'volume' ? (maxVol ? c / maxVol : 0) > 0.5 : true
  return { background: bg, color: light ? '#1c1c1c' : '#f8f6f0', border: '1px solid rgba(0,0,0,0.15)' }
}
const _fmt = (cell: Cell | undefined, m: Metric) => {
  const v = _val(cell, m)
  if (!cell?.count) return ''
  if (m === 'volume') return `${cell.count}`
  if (m === 'success') return `${Math.round(v)}%`
  return `${v.toFixed(1)}`
}

// Map a target-area label to a field cell (3 depth rows x 3 lateral columns),
// plus a behind-the-LOS strip for screens / backfield.
function classifyArea(area: string): { row: number; col: number; behind: boolean } {
  const a = area.toLowerCase()
  const behind = a.includes('backfield') || a.includes('screen') || a.includes('behind')
  const col = a.includes('left') ? 0 : a.includes('right') ? 2 : 1
  let row = 1
  if (a.includes('flat') || a.includes('short') || a.includes('quick') || a.includes('hitch')) row = 2
  else if (a.includes('seam') || a.includes('deep') || a.includes('sideline') || a.includes('post') || a.includes('go') || a.includes('vert')) row = 0
  else if (a.includes('slot') || a.includes('curl') || a.includes('dig') || a.includes('intermediate')) row = 1
  return { row, col, behind }
}

const toggleBtn = (active: boolean): CSSProperties => ({
  flex: 1, padding: '6px 0', fontSize: 11, fontWeight: 700, cursor: 'pointer', borderRadius: 4,
  border: 'none', letterSpacing: '0.04em', textTransform: 'uppercase',
  background: active ? GOLD : 'rgba(255,255,255,0.05)', color: active ? '#1c1c1c' : '#7a7a6e',
})

export default function FieldHeatMap({ summary }: { summary: any }) {
  const [metric, setMetric] = useState<Metric>('volume')

  const off = summary?.offense || {}
  const byArea: Record<string, any> = (off.pass_distribution || {}).by_area || {}
  const sideDist = (off.pass_distribution || {}).field_side_distribution || {}
  const byGap: Record<string, any> = (off.run_gap_analysis || {}).by_gap || {}
  const rda = off.run_direction_analysis || {}

  const hasPass = Object.keys(byArea).length > 0
  const hasRun = Object.keys(byGap).length > 0 || (rda.total_runs || 0) > 0
  if (!hasPass && !hasRun) return null

  // Aggregate pass areas into the field grid + behind-LOS strip.
  const cells: Record<string, Cell> = {}
  let behind: Cell = { count: 0, yards: 0, succ: 0 }
  for (const [area, d] of Object.entries(byArea)) {
    const cnt = d.count || 0
    if (!cnt) continue
    const bucket = classifyArea(area)
    const target = bucket.behind ? behind : (cells[`${bucket.row}-${bucket.col}`] ||= { count: 0, yards: 0, succ: 0 })
    target.count += cnt
    target.yards += (d.avg_yards || 0) * cnt
    target.succ += (d.success_rate || 0) * cnt
  }
  const maxPassVol = Math.max(1, ...Object.values(cells).map(c => c.count), behind.count)
  const rowLabels = ['Deep 20+', 'Intermediate', 'Short 0-9']
  const colLabels = ['Left', 'Middle', 'Right']

  // Run gaps -> cells (single row of gap tiles).
  const gapCells: [string, Cell][] = Object.entries(byGap).map(([g, d]) => [g, {
    count: d.count || 0, yards: (d.avg_yards || 0) * (d.count || 0), succ: (d.success_rate || 0) * (d.count || 0),
  }])
  const maxGapVol = Math.max(1, ...gapCells.map(([, c]) => c.count))

  const metricLegend = metric === 'volume' ? 'Shade = share of plays' : metric === 'success' ? 'Red = low success, green = high' : 'Red = low yards, green = high'

  const card: CSSProperties = { background: '#2e2e2e', borderRadius: 6, padding: '20px 24px', border: '1px solid rgba(255,255,255,0.06)' }

  return (
    <div style={card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
        <h3 style={{ fontSize: 14, fontWeight: 700, color: '#f8f6f0', letterSpacing: '0.04em' }}>Field Heat Maps</h3>
        <span style={{ fontSize: 11, color: '#7a7a6e' }}>where they attack, and how well</span>
      </div>

      {/* Metric toggle */}
      <div style={{ display: 'flex', gap: 4, margin: '12px 0 6px', maxWidth: 320 }}>
        <button onClick={() => setMetric('volume')} style={toggleBtn(metric === 'volume')}>Volume</button>
        <button onClick={() => setMetric('success')} style={toggleBtn(metric === 'success')}>Success %</button>
        <button onClick={() => setMetric('yards')} style={toggleBtn(metric === 'yards')}>Avg Yds</button>
      </div>
      <div style={{ fontSize: 10, color: '#7a7a6e', marginBottom: 16 }}>{metricLegend}. Empty zones had no readable plays on this film.</div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 20 }}>
        {/* ── Pass target field ── */}
        {hasPass && (
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#C9A84C', letterSpacing: '0.06em', marginBottom: 8 }}>PASS TARGETS</div>
            <div style={{ background: '#123a1e', borderRadius: 6, padding: 8, border: '1px solid rgba(45,140,64,0.25)' }}>
              {/* Column headers */}
              <div style={{ display: 'grid', gridTemplateColumns: '54px 1fr 1fr 1fr', gap: 4, marginBottom: 4 }}>
                <div />
                {colLabels.map(c => <div key={c} style={{ fontSize: 9, color: '#7ea88a', textAlign: 'center', letterSpacing: '0.05em' }}>{c.toUpperCase()}</div>)}
              </div>
              {[0, 1, 2].map(row => (
                <div key={row} style={{ display: 'grid', gridTemplateColumns: '54px 1fr 1fr 1fr', gap: 4, marginBottom: 4 }}>
                  <div style={{ fontSize: 9, color: '#7ea88a', display: 'flex', alignItems: 'center' }}>{rowLabels[row]}</div>
                  {[0, 1, 2].map(col => {
                    const cell = cells[`${row}-${col}`]
                    const st = _style(cell, metric, maxPassVol)
                    return (
                      <div key={col} style={{ ...st, borderRadius: 4, minHeight: 46, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 2 }}>
                        <span style={{ fontSize: 15, fontWeight: 700, fontFamily: 'var(--font-bebas)' }}>{_fmt(cell, metric)}</span>
                        {cell?.count ? <span style={{ fontSize: 8, opacity: 0.8 }}>{metric === 'volume' ? 'throws' : `${cell.count} thr`}</span> : null}
                      </div>
                    )
                  })}
                </div>
              ))}
              {/* LOS + behind strip */}
              <div style={{ height: 2, background: GOLD, margin: '6px 0', borderRadius: 1 }} />
              <div style={{ display: 'grid', gridTemplateColumns: '54px 1fr', gap: 4 }}>
                <div style={{ fontSize: 9, color: '#7ea88a', display: 'flex', alignItems: 'center' }}>Behind LOS</div>
                <div style={{ ..._style(behind.count ? behind : undefined, metric, maxPassVol), borderRadius: 4, minHeight: 34, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                  <span style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--font-bebas)' }}>{_fmt(behind.count ? behind : undefined, metric)}</span>
                  <span style={{ fontSize: 8, opacity: 0.8 }}>screens / checkdowns</span>
                </div>
              </div>
            </div>
            {(sideDist.left_pct != null) && (
              <div style={{ fontSize: 10, color: '#7a7a6e', marginTop: 8 }}>
                Field side: <b style={{ color: '#ede9df' }}>{Math.round(sideDist.left_pct)}%</b> left · <b style={{ color: '#ede9df' }}>{Math.round(sideDist.middle_pct || 0)}%</b> middle · <b style={{ color: '#ede9df' }}>{Math.round(sideDist.right_pct)}%</b> right
              </div>
            )}
          </div>
        )}

        {/* ── Run gaps + direction ── */}
        {hasRun && (
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#C9A84C', letterSpacing: '0.06em', marginBottom: 8 }}>RUN GAPS</div>
            <div style={{ background: '#123a1e', borderRadius: 6, padding: 10, border: '1px solid rgba(45,140,64,0.25)' }}>
              {gapCells.length > 0 ? (
                <div style={{ display: 'flex', gap: 4 }}>
                  {gapCells.sort((a, b) => b[1].count - a[1].count).map(([gap, cell]) => {
                    const st = _style(cell, metric, maxGapVol)
                    return (
                      <div key={gap} style={{ ...st, flex: 1, borderRadius: 4, minHeight: 60, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 2 }}>
                        <span style={{ fontSize: 10, opacity: 0.75, letterSpacing: '0.05em' }}>{gap}</span>
                        <span style={{ fontSize: 16, fontWeight: 700, fontFamily: 'var(--font-bebas)' }}>{_fmt(cell, metric)}</span>
                        {cell.count ? <span style={{ fontSize: 8, opacity: 0.8 }}>{metric === 'volume' ? 'runs' : `${cell.count} rn`}</span> : null}
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div style={{ fontSize: 11, color: '#7ea88a', padding: '12px 4px' }}>No gap-level detail on this film.</div>
              )}
            </div>
            {(rda.total_runs || 0) > 0 && (
              <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {([['Left', rda.left_pct], ['Right', rda.right_pct], ['Inside', rda.inside_pct], ['Outside', rda.outside_pct]] as [string, number][])
                  .filter(([, v]) => v != null).map(([label, v]) => (
                    <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 10, color: '#7a7a6e', width: 48 }}>{label}</span>
                      <div style={{ flex: 1, height: 8, background: 'rgba(255,255,255,0.05)', borderRadius: 4, overflow: 'hidden' }}>
                        <div style={{ width: `${Math.max(0, Math.min(100, v))}%`, height: '100%', background: GOLD, borderRadius: 4 }} />
                      </div>
                      <span style={{ fontSize: 10, color: '#ede9df', width: 34, textAlign: 'right' }}>{Math.round(v)}%</span>
                    </div>
                  ))}
                <div style={{ fontSize: 10, color: '#7a7a6e' }}>{rda.total_runs} runs charted</div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
