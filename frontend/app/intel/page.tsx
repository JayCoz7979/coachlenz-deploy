'use client'
/**
 * Film Intelligence (#page-intel) - football scouting analysis wired to the
 * live tendency-engine report. Every stat here is read from a generated scout
 * report's `summary` dict; nothing is fabricated. If no finished report exists
 * the page renders its chrome with an honest activation notice.
 *
 * Layout mirrors the approved demo: Live Situation Query, Run/Pass Heatmap
 * (Down x Distance), Formation Lab, and Player Alignment Intelligence.
 */
import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import OSShell from '@/components/os/OSShell'
import api from '@/lib/api'

// ---- helpers -------------------------------------------------------------

// run_pct etc. arrive as 0-100 from the engine, but normalize defensively in
// case a caller ever hands us a 0-1 ratio.
function pct(n: any): number | null {
  if (typeof n !== 'number' || isNaN(n)) return null
  return n <= 1 ? Math.round(n * 100) : Math.round(n)
}

function firstKey(obj: any): string | null {
  if (!obj || typeof obj !== 'object') return null
  const keys = Object.keys(obj)
  return keys.length ? keys[0] : null
}

function ordinal(n: number): string {
  return ['', '1st', '2nd', '3rd', '4th'][n] || `${n}th`
}

// Which down-summary bucket in summary.offense answers a given down + distance.
function downKey(down: number, distVal: number): string {
  if (down === 1) return 'first_down'
  if (down === 4) return 'fourth_down'
  const band = distVal <= 3 ? 'short' : distVal <= 6 ? 'medium' : 'long'
  if (down === 2) return band === 'short' ? 'second_short' : band === 'medium' ? 'second_medium' : 'second_long'
  return band === 'short' ? 'third_short' : band === 'medium' ? 'third_medium' : 'third_long'
}

// hm-cell colour by run%: red = run heavy, green = pass heavy (matches demo).
function runCellStyle(runPct: number): { background: string; color: string } {
  if (runPct >= 70) return { background: 'rgba(239,68,68,.55)', color: '#fca5a5' }
  if (runPct >= 55) return { background: 'rgba(239,68,68,.3)', color: '#fca5a5' }
  if (runPct >= 45) return { background: 'rgba(34,197,94,.18)', color: 'var(--green4)' }
  if (runPct >= 30) return { background: 'rgba(45,80,22,.35)', color: 'var(--green3)' }
  return { background: 'rgba(45,80,22,.55)', color: 'var(--green3)' }
}

const BAR_BG: Record<string, string> = {
  green: 'linear-gradient(90deg,var(--green),var(--green3))',
}

// A single progress bar row (pb-wrap). kind maps to the demo pf-* fills.
function Bar({ label, value, kind = 'g' }: { label: string; value: number; kind?: 'green' | 'g' | 'o' | 'r' }) {
  const w = Math.max(0, Math.min(100, value))
  const cls = kind === 'green' ? 'pf' : `pf pf-${kind}`
  const style: any = { width: `${w}%` }
  if (kind === 'green') style.background = BAR_BG.green
  return (
    <div className="pb-wrap">
      <div className="pb-top"><span>{label}</span><b>{Math.round(value)}%</b></div>
      <div className="pb"><div className={cls} style={style}></div></div>
    </div>
  )
}

// Derive up to 4 percent bars from a player_tendencies block (football first,
// basketball fallback). Only real, present percentages are emitted.
function playerBars(b: any): { label: string; value: number; kind: 'green' | 'g' | 'o' | 'r' }[] {
  const out: { label: string; value: number; kind: 'green' | 'g' | 'o' | 'r' }[] = []
  const touches = Number(b?.touches) || 0
  // Football block
  if (typeof b?.success_rate === 'number') out.push({ label: 'Success rate', value: b.success_rate, kind: 'g' })
  if (touches > 0 && typeof b?.explosive_plays === 'number')
    out.push({ label: 'Explosive rate', value: (b.explosive_plays / touches) * 100, kind: 'o' })
  if (touches > 0 && typeof b?.as_runner === 'number')
    out.push({ label: 'Runs when primary', value: (b.as_runner / touches) * 100, kind: 'g' })
  if (touches > 0 && typeof b?.as_passer_or_receiver === 'number')
    out.push({ label: 'Pass/receive when primary', value: (b.as_passer_or_receiver / touches) * 100, kind: 'r' })
  // Basketball block fallback
  if (typeof b?.fg_pct === 'number') out.push({ label: 'FG%', value: b.fg_pct, kind: 'g' })
  if (typeof b?.three_pt_rate === 'number') out.push({ label: '3PT rate', value: b.three_pt_rate, kind: 'o' })
  return out.slice(0, 4)
}

// ---- page ----------------------------------------------------------------

export default function IntelPage() {
  const [loading, setLoading] = useState(true)
  const [report, setReport] = useState<any>(null)
  const [formIdx, setFormIdx] = useState(0)
  const [sit, setSit] = useState({ down: 3, dist: 7, hash: 'mid', yard: 'mid', pers: '11', score: 'tied' })

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const list = await api.get('/reports')
        const finished = (Array.isArray(list.data) ? list.data : [])
          .filter((r: any) => r && r.generated_at)
          .sort((a: any, b: any) => String(b.generated_at).localeCompare(String(a.generated_at)))
        if (!finished.length) { if (alive) { setReport(null); setLoading(false) } return }
        const full = await api.get(`/reports/${finished[0].id}`)
        if (alive) setReport(full.data)
      } catch {
        if (alive) setReport(null)
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => { alive = false }
  }, [])

  const summary = report?.summary
  const off = summary?.offense

  // Formation list from the play matrix (richest) or top_formations fallback.
  const forms = useMemo(() => {
    const fpm = off?.formation_play_matrix
    let list: any[] = []
    if (fpm && typeof fpm === 'object' && !Array.isArray(fpm)) {
      list = Object.entries(fpm).map(([formation, v]: any) => ({ formation, ...(v || {}) }))
    } else if (off?.top_formations) {
      const tf = off.top_formations
      if (Array.isArray(tf)) list = tf.map((f: any) => ({ formation: f.formation || f.name, ...f }))
      else list = Object.entries(tf).map(([formation, count]: any) => ({ formation, count }))
    }
    return list.sort((a, b) => (Number(b.count) || 0) - (Number(a.count) || 0))
  }, [off])

  // Player cards from player_tendencies (dict keyed by player, or array).
  const playerEntries = useMemo(() => {
    const ptRaw = summary?.player_tendencies
    if (!ptRaw) return []
    const byPlayer = ptRaw.by_player || ptRaw
    let entries: any[] = []
    if (Array.isArray(byPlayer)) entries = byPlayer.map((b: any) => ({ key: b.jersey || b.key, block: b }))
    else if (typeof byPlayer === 'object') entries = Object.entries(byPlayer).map(([key, block]) => ({ key, block }))
    return entries.filter(e => e.block && typeof e.block === 'object' && (e.block.jersey || e.block.touches)).slice(0, 2)
  }, [summary])

  const preSnapTells: any[] = Array.isArray(off?.pre_snap_tells) ? off.pre_snap_tells : []

  // Live Situation Query result (pure client-side, computed from summary).
  const result = useMemo(() => {
    if (!off) return null
    const s = off[downKey(sit.down, sit.dist)]
    if (!s || !s.total) return null
    const run = pct(s.run_pct)
    const pass = pct(s.pass_pct)
    if (run === null || pass === null) return null
    const lean = run >= pass ? 'RUN' : 'PASS'
    const leanPct = Math.max(run, pass)
    const topPlay = firstKey(s.top_plays)
    const topForm = firstKey(s.top_formations)
    const persDetail = off.personnel_detail?.[sit.pers]
    return { s, run, pass, lean, leanPct, topPlay, topForm, persDetail }
  }, [off, sit])

  const DIST_LABEL: Record<number, string> = { 1: '& 1 (Sneak)', 3: '& 2-3', 5: '& 4-6', 7: '& 7-9', 10: '& 10+' }
  const HASH_LABEL: Record<string, string> = { left: 'Left Hash', mid: 'Middle', right: 'Right Hash' }
  const YARD_LABEL: Record<string, string> = { own20: 'Own 1-20', own40: 'Own 21-40', mid: 'Midfield', opp40: 'Opp 21-40', rz: 'Red Zone' }
  const PERS_LABEL: Record<string, string> = { '11': '11 Personnel', '12': '12 Personnel', '21': '21 Personnel', '22': '22 Personnel', '10': 'Empty' }
  const SCORE_LABEL: Record<string, string> = { lead: 'Leading', tied: 'Tied', trail: 'Trailing' }

  const sitLabel = `${ordinal(sit.down)} ${DIST_LABEL[sit.dist]} · ${HASH_LABEL[sit.hash]} · ${YARD_LABEL[sit.yard]} · ${PERS_LABEL[sit.pers]} · ${SCORE_LABEL[sit.score]}`

  const set = (k: string, v: any) => setSit(prev => ({ ...prev, [k]: v }))

  // Heatmap columns -> representative distance value.
  const HM_COLS = [
    { label: '&1', v: 1 }, { label: '&2-3', v: 3 }, { label: '&4-6', v: 5 }, { label: '&7-9', v: 8 }, { label: '&10+', v: 11 },
  ]
  const HM_ROWS = [1, 2, 3, 4]

  const totalPlays = off?.total_plays ?? summary?.offense_plays ?? summary?.total_plays

  // -------- empty / loading chrome ---------------------------------------
  if (loading) {
    return (
      <OSShell title="Film Intelligence">
        <div style={{ textAlign: 'center', padding: '80px 16px', color: 'var(--text3)', fontSize: 13 }}>
          Loading intelligence...
        </div>
        <div className="powered">Powered by <a href="https://cosbyaisolutions.com" target="_blank" rel="noreferrer">Cosby AI Solutions</a></div>
      </OSShell>
    )
  }

  if (!report || !summary) {
    return (
      <OSShell title="Film Intelligence">
        <div style={{ textAlign: 'center', padding: '80px 16px', maxWidth: 460, margin: '0 auto' }}>
          <div style={{ fontSize: 34, marginBottom: 12 }}>🔬</div>
          <div style={{ fontFamily: 'var(--display)', fontSize: 16, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>
            Film Intelligence activates once your first scout report is generated
          </div>
          <div style={{ fontSize: 12, color: 'var(--text2)', lineHeight: 1.7, marginBottom: 18 }}>
            Tag plays on a game film and generate a scout report. The situational query engine, heatmaps, and player alignment tells all draw from that report.
          </div>
          <Link href="/scout" className="tag tg" style={{ padding: '7px 14px', fontSize: 12, textDecoration: 'none' }}>Start a scout →</Link>
        </div>
        <div className="powered">Powered by <a href="https://cosbyaisolutions.com" target="_blank" rel="noreferrer">Cosby AI Solutions</a></div>
      </OSShell>
    )
  }

  // -------- main -----------------------------------------------------------
  return (
    <OSShell title="Film Intelligence">
      <div style={{ marginBottom: 16 }}>
        <div className="sec-title">
          🔬 {report.title || 'Film Intelligence Analysis'}
          <span style={{ fontSize: 11, color: 'var(--text2)', fontWeight: 400, marginLeft: 8 }}>
            · {report.sport || 'football'}
            {typeof totalPlays === 'number' ? ` · ${totalPlays.toLocaleString()} plays` : ''} · Live
          </span>
        </div>
      </div>

      {/* Live Situation Query */}
      <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 14, padding: 16, marginBottom: 16 }}>
        <div style={{ fontFamily: 'var(--display)', fontSize: 12, fontWeight: 700, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 10 }}>
          🎯 Live Situation Query
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
          <select value={sit.down} onChange={e => set('down', Number(e.target.value))} className="intel-select">
            <option value={1}>1st Down</option><option value={2}>2nd Down</option><option value={3}>3rd Down</option><option value={4}>4th Down</option>
          </select>
          <select value={sit.dist} onChange={e => set('dist', Number(e.target.value))} className="intel-select">
            <option value={1}>& 1 (Sneak)</option><option value={3}>& 2-3</option><option value={5}>& 4-6</option><option value={7}>& 7-9</option><option value={10}>& 10+</option>
          </select>
          <select value={sit.hash} onChange={e => set('hash', e.target.value)} className="intel-select">
            <option value="left">Left Hash</option><option value="mid">Middle</option><option value="right">Right Hash</option>
          </select>
          <select value={sit.yard} onChange={e => set('yard', e.target.value)} className="intel-select">
            <option value="own20">Own 1-20</option><option value="own40">Own 21-40</option><option value="mid">Midfield</option><option value="opp40">Opp 21-40</option><option value="rz">Red Zone</option>
          </select>
          <select value={sit.pers} onChange={e => set('pers', e.target.value)} className="intel-select">
            <option value="11">11 Personnel</option><option value="12">12 Personnel</option><option value="21">21 Personnel</option><option value="22">22 Personnel</option><option value="10">Empty</option>
          </select>
          <select value={sit.score} onChange={e => set('score', e.target.value)} className="intel-select">
            <option value="lead">Leading</option><option value="tied">Tied</option><option value="trail">Trailing</option>
          </select>
        </div>
        <div className="intel-result">
          <div style={{ fontSize: 11, color: 'var(--green3)', fontFamily: 'var(--display)', fontWeight: 700, marginBottom: 4 }}>{sitLabel}</div>
          {result ? (
            <>
              <div className="intel-result-call">
                {result.lean}{result.topPlay ? ` · ${result.topPlay}` : ''} · {result.leanPct}%
              </div>
              <div className="intel-result-detail">
                Based on {result.s.total} matching film {result.s.total === 1 ? 'instance' : 'instances'}. On {ordinal(sit.down)} {DIST_LABEL[sit.dist]}, this opponent {result.lean === 'RUN' ? 'runs' : 'throws'} {result.leanPct}% of the time.
                {result.topForm ? ` Most common formation here: ${result.topForm}.` : ''}
                {typeof result.s.success_rate === 'number' ? ` Success rate ${pct(result.s.success_rate)}%.` : ''}
                {result.persDetail && typeof result.persDetail.run_pct === 'number' ? ` Out of ${PERS_LABEL[sit.pers]} overall: run ${pct(result.persDetail.run_pct)}%.` : ''}
              </div>
              <div className="intel-result-tags">
                <span className="tag tg">Run: {result.run}%</span>
                <span className="tag tr">Pass: {result.pass}%</span>
                {result.topPlay ? <span className="tag tgo">{result.topPlay}</span> : null}
                <span className="tag tq">{result.s.total} {result.s.total === 1 ? 'instance' : 'instances'}</span>
              </div>
            </>
          ) : (
            <div className="intel-result-detail">
              No film instances match this exact situation yet. As more plays are tagged in this matchup, this situation will populate with a run/pass call and confidence.
            </div>
          )}
        </div>
      </div>

      <div className="g2" style={{ marginBottom: 16 }}>
        {/* Run/Pass Heatmap */}
        <div className="card">
          <div className="card-hdr"><div className="card-title">📊 Run/Pass Heatmap - Down x Distance</div></div>
          <div className="card-body">
            <div style={{ fontSize: 10, color: 'var(--text3)', marginBottom: 8 }}>Numbers = Run % · Red = run heavy · Green = pass heavy</div>
            {off ? (
              <div style={{ display: 'grid', gridTemplateColumns: '80px repeat(5,1fr)', gap: 3, fontSize: 10 }}>
                <div></div>
                {HM_COLS.map(c => (
                  <div key={c.label} style={{ textAlign: 'center', color: 'var(--text3)', fontWeight: 600, padding: 3 }}>{c.label}</div>
                ))}
                {HM_ROWS.map(down => (
                  <FragmentRow key={down} down={down} cols={HM_COLS} off={off} />
                ))}
              </div>
            ) : (
              <div style={{ fontSize: 11, color: 'var(--text3)' }}>Down and distance splits are not available for this report.</div>
            )}
          </div>
        </div>

        {/* Formation Lab */}
        <div className="card">
          <div className="card-hdr"><div className="card-title">🏈 Formation Lab - Click to Explore</div></div>
          <div className="card-body">
            {forms.length ? (
              <>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
                  {forms.slice(0, 8).map((f, i) => (
                    <span
                      key={f.formation + i}
                      onClick={() => setFormIdx(i)}
                      className={'tag ' + (i === formIdx ? 'tg' : 'tq')}
                      style={{ cursor: 'pointer', padding: '5px 10px' }}
                    >
                      {f.formation}
                    </span>
                  ))}
                </div>
                <FormationDetail f={forms[formIdx] || forms[0]} totalPlays={off?.total_plays} />
              </>
            ) : (
              <div style={{ fontSize: 11, color: 'var(--text3)' }}>No formation data has been tagged in this report yet.</div>
            )}
          </div>
        </div>
      </div>

      {/* Player Alignment Intelligence */}
      {(playerEntries.length || preSnapTells.length) ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-hdr"><div className="card-title">👤 Player Alignment Intelligence</div></div>
          <div className="card-body">
            <div className="g3" style={{ marginBottom: 0 }}>
              {playerEntries.map(({ key, block }) => {
                const bars = playerBars(block)
                const role = firstKey(block.roles) || 'Player'
                return (
                  <div key={key} style={{ background: 'var(--bg3)', border: '1px solid var(--border)', borderRadius: 9, padding: 13 }}>
                    <div style={{ fontFamily: 'var(--display)', fontSize: 12, fontWeight: 700, marginBottom: 2 }}>
                      {role} #{block.jersey ?? '-'}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--green3)', marginBottom: 8, fontWeight: 600 }}>
                      {block.team ? `${block.team} · ` : ''}{typeof block.touches === 'number' ? `${block.touches} primary touches` : 'jersey-tracked'}
                    </div>
                    {bars.length ? bars.map((b, i) => <Bar key={i} label={b.label} value={b.value} kind={b.kind} />)
                      : <div style={{ fontSize: 10, color: 'var(--text3)' }}>Not enough tagged touches for tells yet.</div>}
                    {typeof block.avg_id_confidence === 'number' ? (
                      <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 4 }}>Jersey ID confidence: {Math.round(block.avg_id_confidence * 100)}%</div>
                    ) : null}
                  </div>
                )
              })}

              {preSnapTells.length ? (
                <div style={{ background: 'var(--bg3)', border: '1px solid var(--border)', borderRadius: 9, padding: 13 }}>
                  <div style={{ fontFamily: 'var(--display)', fontSize: 12, fontWeight: 700, marginBottom: 2 }}>Pre-Snap Tells</div>
                  <div style={{ fontSize: 10, color: 'var(--green3)', marginBottom: 8, fontWeight: 600 }}>Formation + down tell matrix</div>
                  {preSnapTells.slice(0, 4).map((t, i) => {
                    const run = pct(t.run_pct) ?? 0
                    const pass = pct(t.pass_pct) ?? 0
                    const lean = run >= pass ? 'Run' : 'Pass'
                    const leanPct = Math.max(run, pass)
                    const label = `${t.formation}${t.motion ? ' + Motion' : ''} ${ordinal(t.down)} → ${lean}`
                    return <Bar key={i} label={label} value={leanPct} kind={lean === 'Run' ? 'g' : 'r'} />
                  })}
                  <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 4 }}>Ranked by film frequency (count ≥ 3).</div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {/* Supporting detail - run direction + top pass zone (optional) */}
      <SupportingDetail off={off} />

      <div className="powered">Powered by <a href="https://cosbyaisolutions.com" target="_blank" rel="noreferrer">Cosby AI Solutions</a></div>
    </OSShell>
  )
}

// One heatmap row. Kept as a component so the grid cells flatten correctly.
function FragmentRow({ down, cols, off }: { down: number; cols: { label: string; v: number }[]; off: any }) {
  return (
    <>
      <div style={{ color: 'var(--text2)', fontWeight: 600, display: 'flex', alignItems: 'center', fontSize: 10 }}>{ordinal(down)} Down</div>
      {cols.map(c => {
        const s = off?.[downKey(down, c.v)]
        const run = s && s.total ? pct(s.run_pct) : null
        if (run === null) {
          return <div key={c.label} className="hm-cell" style={{ background: 'var(--bg4)', color: 'var(--text3)' }}>-</div>
        }
        const st = runCellStyle(run)
        return <div key={c.label} className="hm-cell" style={{ background: st.background, color: st.color }}>{run}%</div>
      })}
    </>
  )
}

function FormationDetail({ f, totalPlays }: { f: any; totalPlays: any }) {
  if (!f) return null
  const pass = pct(f.pass_pct)
  const run = pct(f.run_pct)
  const success = pct(f.success_rate)
  const topPlay = firstKey(f.top_plays)
  const topPlayCount = topPlay && f.top_plays ? Number(f.top_plays[topPlay]) : null
  const topPlayPct = topPlayCount && f.count ? Math.round((topPlayCount / Number(f.count)) * 100) : null
  const snapPct = typeof totalPlays === 'number' && totalPlays > 0 && f.count ? Math.round((Number(f.count) / totalPlays) * 100) : null
  return (
    <div>
      {pass !== null ? <Bar label="Pass Play" value={pass} kind="green" /> : null}
      {run !== null ? <Bar label="Run Play" value={run} kind="g" /> : null}
      {success !== null ? <Bar label="Success Rate" value={success} kind="o" /> : null}
      {topPlay && topPlayPct !== null ? <Bar label={`Top: ${topPlay}`} value={topPlayPct} kind="o" /> : null}
      <div style={{ marginTop: 10, padding: 10, background: 'var(--bg3)', borderRadius: 8, fontSize: 11, color: 'var(--text2)', lineHeight: 1.65 }}>
        <strong style={{ color: 'var(--text)' }}>
          {f.formation}{snapPct !== null ? ` (${snapPct}% of snaps)` : ''}:
        </strong>{' '}
        {typeof f.count === 'number' ? `${f.count} tagged plays. ` : ''}
        {pass !== null && run !== null ? `Pass ${pass}% / Run ${run}%. ` : ''}
        {typeof f.avg_yards === 'number' ? `Averaging ${f.avg_yards} yds. ` : ''}
        {success !== null ? `${success}% success rate.` : ''}
      </div>
    </div>
  )
}

// Optional supporting card - only renders when real run-direction or pass-zone
// data exists in the summary.
function SupportingDetail({ off }: { off: any }) {
  const rd = off?.run_direction_analysis
  const pd = off?.pass_distribution
  const hasRun = rd && (typeof rd.inside_pct === 'number' || typeof rd.left_pct === 'number') && rd.total_runs
  const areas = pd?.by_area && typeof pd.by_area === 'object' ? Object.entries(pd.by_area) : []
  const hasPass = areas.length > 0
  if (!hasRun && !hasPass) return null
  return (
    <div className="g2" style={{ marginBottom: 16 }}>
      {hasRun ? (
        <div className="card">
          <div className="card-hdr"><div className="card-title">🧭 Run Direction</div></div>
          <div className="card-body">
            {typeof rd.inside_pct === 'number' ? <Bar label="Inside" value={pct(rd.inside_pct) ?? 0} kind="g" /> : null}
            {typeof rd.outside_pct === 'number' ? <Bar label="Outside" value={pct(rd.outside_pct) ?? 0} kind="o" /> : null}
            {typeof rd.left_pct === 'number' ? <Bar label="Left" value={pct(rd.left_pct) ?? 0} kind="g" /> : null}
            {typeof rd.right_pct === 'number' ? <Bar label="Right" value={pct(rd.right_pct) ?? 0} kind="g" /> : null}
            <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 4 }}>{rd.total_runs} tagged runs.</div>
          </div>
        </div>
      ) : <div />}
      {hasPass ? (
        <div className="card">
          <div className="card-hdr"><div className="card-title">🎯 Pass Distribution by Area</div></div>
          <div className="card-body">
            {areas.slice(0, 5).map(([area, v]: any) => (
              <Bar key={area} label={area} value={pct(v?.pct_of_passes) ?? 0} kind="o" />
            ))}
            {pd.hottest_area ? <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 4 }}>Hottest zone: {pd.hottest_area}.</div> : null}
          </div>
        </div>
      ) : <div />}
    </div>
  )
}
