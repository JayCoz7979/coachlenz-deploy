'use client'
import { useEffect, useState, Fragment, type CSSProperties } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import Link from 'next/link'
import { ChevronLeft, Loader2, FileText, AlertTriangle, TrendingUp, Shield, Zap, Target, Printer, Download, ChevronDown, Share2, Star, Trash2 } from 'lucide-react'
import FieldHeatMap from '@/components/report/FieldHeatMap'
import BasketballShotChart from '@/components/report/BasketballShotChart'
import PlayerShotSpots from '@/components/report/PlayerShotSpots'
import TurnoverMap from '@/components/report/TurnoverMap'
import RunPassMatrix from '@/components/report/RunPassMatrix'
import ReportChat from '@/components/report/ReportChat'

interface Section {
  heading: string
  body: string
  insight_type?: string
}

interface Report {
  id: string
  title: string
  sport: string
  report_type: string
  is_trial: boolean
  watermarked: boolean
  sections: Section[]
  summary: any
  film_min_height?: number | null
  low_res_film?: boolean
  generated_at: string | null
  status?: 'ready' | 'failed' | 'generating'
  message?: string | null
}

const menuItem: CSSProperties = {
  display: 'block', width: '100%', textAlign: 'left', background: 'transparent', border: 'none',
  color: '#ede9df', padding: '8px 8px', fontSize: 13, cursor: 'pointer', borderRadius: 6,
}
const menuHint: CSSProperties = { color: '#7a7a6e', fontSize: 11, marginLeft: 6 }
const unitChip: CSSProperties = {
  background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.25)', color: '#C9A84C',
  borderRadius: 6, padding: '4px 9px', fontSize: 12, fontWeight: 700, cursor: 'pointer',
}

// §9 FERPA governance: every report output carries this confidentiality notice.
const FERPA_NOTE = "This report is confidential. It contains performance data covered under your institution's FERPA DPA with CoachLenz."

const SECTION_ICONS: Record<string, any> = {
  run: TrendingUp,
  pass: Target,
  defense: Shield,
  red_zone: Zap,
  tendency: TrendingUp,
  coach_notes: Star,
  default: FileText,
}

// Lightweight rich text: renders **bold**, bullet lists, and paragraphs so a
// scouting report reads clean instead of showing raw markdown characters.
function inlineFmt(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**')
      ? <strong key={i} style={{ color: '#f8f6f0' }}>{part.slice(2, -2)}</strong>
      : <Fragment key={i}>{part}</Fragment>
  )
}

function RichText({ text }: { text: string }) {
  const blocks = (text || '').trim().split(/\n\s*\n/)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {blocks.map((block, bi) => {
        const lines = block.split('\n').map(l => l.trim()).filter(Boolean)
        if (!lines.length) return null
        // A block with multiple lines is a list of points — render as real bullets,
        // whether or not the writer prefixed them with a dash.
        if (lines.length >= 2) {
          return (
            <ul key={bi} style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 5 }}>
              {lines.map((l, li) => (
                <li key={li} style={{ fontSize: 13, color: '#ede9df', lineHeight: 1.6 }}>{inlineFmt(l.replace(/^\s*[-•*]\s+/, ''))}</li>
              ))}
            </ul>
          )
        }
        const one = lines[0]
        if (/^#{1,3}\s+/.test(one)) {
          return <div key={bi} style={{ fontSize: 13, fontWeight: 700, color: '#C9A84C' }}>{inlineFmt(one.replace(/^#{1,3}\s+/, ''))}</div>
        }
        return (
          <p key={bi} style={{ fontSize: 13, color: '#ede9df', lineHeight: 1.7, margin: 0 }}>
            {inlineFmt(one.replace(/^\s*[-•*]\s+/, ''))}
          </p>
        )
      })}
    </div>
  )
}

function SectionCard({ section }: { section: Section }) {
  const Icon = SECTION_ICONS[section.insight_type ?? 'default'] ?? SECTION_ICONS.default
  return (
    <div style={{
      background: '#2e2e2e', borderRadius: 6, padding: '20px 24px',
      border: '1px solid rgba(255,255,255,0.06)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <div style={{
          width: 32, height: 32, borderRadius: 6,
          background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.2)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon size={15} style={{ color: '#C9A84C' }} />
        </div>
        <h3 style={{ fontSize: 14, fontWeight: 700, color: '#f8f6f0', letterSpacing: '0.04em' }}>
          {section.heading}
        </h3>
      </div>
      <RichText text={section.body} />
    </div>
  )
}

// Recovery: if a report body is actually the raw JSON array (a past generation
// where the server couldn't parse it), parse it client-side into real sections.
function lenientJsonParse(text: string): any {
  try { return JSON.parse(text) } catch {}
  let out = '', inStr = false, esc = false
  for (const ch of text) {
    if (esc) { out += ch; esc = false; continue }
    if (ch === '\\') { out += ch; esc = true; continue }
    if (ch === '"') { inStr = !inStr; out += ch; continue }
    if (inStr && ch === '\n') { out += '\\n'; continue }
    if (inStr && ch === '\r') { out += '\\r'; continue }
    if (inStr && ch === '\t') { out += '\\t'; continue }
    out += ch
  }
  try { return JSON.parse(out) } catch { return null }
}

function recoverSections(sections: Section[]): Section[] {
  if (sections && sections.length === 1) {
    let t = (sections[0].body || '').trim()
    if ((t.startsWith('[') || t.startsWith('```')) && t.includes('"heading"')) {
      if (t.includes('```')) { const p = t.split('```'); t = (p[1] || t).replace(/^json/, '').trim() }
      if (t.includes('[') && t.includes(']')) t = t.slice(t.indexOf('['), t.lastIndexOf(']') + 1)
      const parsed = lenientJsonParse(t)
      if (Array.isArray(parsed) && parsed.length && parsed[0] && parsed[0].heading) {
        return parsed.map((p: any) => ({ heading: p.heading || 'Analysis', insight_type: p.insight_type || 'tendency', body: p.body || '' }))
      }
    }
  }
  return sections
}

export default function ReportPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { user, isLoading, fetchMe } = useAuth()
  const [report, setReport] = useState<Report | null>(null)
  const [polling, setPolling] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [retrying, setRetrying] = useState(false)
  const [deleting, setDeleting] = useState(false)
  // Still generating = explicit 'generating' status, or (older payloads) no result yet
  // and not flagged failed. A failed report must NOT keep polling.
  const stillGenerating = (r: any) => (r?.status ? r.status === 'generating' : !r?.generated_at)

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])

  useEffect(() => {
    if (!user || !id) return
    const load = () => api.get(`/reports/${id}`).then(r => {
      setReport(r.data)
      setLoadError(null)
      setPolling(stillGenerating(r.data))
    }).catch((e: any) => {
      // Without this, a failed load left the page spinning forever.
      setPolling(false)
      setLoadError(e?.response?.data?.detail ?? 'We could not load this report. Please refresh to try again.')
    })
    load()
  }, [user, id])

  // Poll every 5s while still processing
  useEffect(() => {
    if (!polling) return
    const t = setInterval(() => {
      api.get(`/reports/${id}`).then(r => {
        setReport(r.data)
        if (!stillGenerating(r.data)) { setPolling(false) }
      }).catch(() => {
        // Transient poll failure: stop the loop so it can't spin silently. A
        // still-generating report recovers on the next page load.
        setPolling(false)
      })
    }, 5000)
    return () => clearInterval(t)
  }, [polling, id])

  // Render a report body (markdown-ish: **bold** + bullet lines) into print HTML.
  const bodyToHtml = (esc: (s: string) => string, body: string) =>
    (body || '').trim().split(/\n\s*\n/).map(block => {
      const lines = block.split('\n').map(l => l.trim()).filter(Boolean)
      const fmt = (l: string) => esc(l).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      if (lines.length >= 2) {
        return `<ul>${lines.map(l => `<li>${fmt(l.replace(/^\s*[-•*]\s+/, ''))}</li>`).join('')}</ul>`
      }
      return `<p>${fmt(lines[0] || '').replace(/^\s*[-•*]\s+/, '')}</p>`
    }).join('')

  // Print-friendly field heat map (light theme) built from the report summary, so
  // the PDF export carries the same "where they attack" visual as the screen.
  const buildHeatMapHtml = (s: any): string => {
    const off = s?.offense || {}
    const byArea: Record<string, any> = (off.pass_distribution || {}).by_area || {}
    const byGap: Record<string, any> = (off.run_gap_analysis || {}).by_gap || {}
    const rda = off.run_direction_analysis || {}
    const sideDist = (off.pass_distribution || {}).field_side_distribution || {}
    const hasPass = Object.keys(byArea).length > 0
    const hasRun = Object.keys(byGap).length > 0 || (rda.total_runs || 0) > 0
    if (!hasPass && !hasRun) {
      return `<section><h2>Field Heat Maps — Where They Attack</h2><p style="color:#555;font-style:italic">No pass-target or run-gap detail was readable on this film yet — a thin or low-confidence breakdown. Run a full or DEEP breakdown of the whole game and the field maps fill in.</p></section>`
    }
    const cells: Record<string, { count: number }> = {}; let behind = 0
    const classify = (a: string) => {
      const l = a.toLowerCase()
      const bhd = l.includes('backfield') || l.includes('screen') || l.includes('behind')
      const col = l.includes('left') ? 0 : l.includes('right') ? 2 : 1
      let row = 1
      if (l.includes('flat') || l.includes('short') || l.includes('quick') || l.includes('hitch')) row = 2
      else if (l.includes('seam') || l.includes('deep') || l.includes('sideline') || l.includes('post') || l.includes('go') || l.includes('vert')) row = 0
      return { row, col, bhd }
    }
    for (const [area, d] of Object.entries<any>(byArea)) {
      const c = d.count || 0; if (!c) continue
      const b = classify(area)
      if (b.bhd) behind += c
      else { const k = `${b.row}-${b.col}`; cells[k] = cells[k] || { count: 0 }; cells[k].count += c }
    }
    const maxV = Math.max(1, ...Object.values(cells).map(c => c.count), behind)
    const grn = (c: number) => c ? `background:rgba(26,92,42,${(0.15 + 0.7 * (c / maxV)).toFixed(2)});color:#fff;font-weight:bold` : 'background:#f2f2ee;color:#bbb'
    const rows = ['Deep', 'Intermediate', 'Short'], cols = ['Left', 'Middle', 'Right']
    const cellTd = (r: number, cn: number) => { const c = cells[`${r}-${cn}`]?.count || 0; return `<td style="${grn(c)};text-align:center;padding:8px;border:2px solid #fff">${c || ''}</td>` }
    const passTable = hasPass ? `<div style="flex:1;min-width:230px">
        <div style="font-size:11px;font-weight:bold;color:#1a5c2a;text-transform:uppercase;margin-bottom:4px">Pass Targets (throws)</div>
        <table style="border-collapse:collapse;width:100%;font-size:12px">
          <tr><td></td>${cols.map(c => `<td style="text-align:center;font-size:10px;color:#666">${c}</td>`).join('')}</tr>
          ${rows.map((rl, ri) => `<tr><td style="font-size:10px;color:#666;padding-right:6px">${rl}</td>${[0, 1, 2].map(ci => cellTd(ri, ci)).join('')}</tr>`).join('')}
        </table>
        <div style="font-size:10px;color:#666;margin-top:4px">Behind LOS / screens: <b>${behind || 0}</b></div>
      </div>` : ''
    let gapTable = ''
    if (hasRun) {
      const gaps = Object.entries<any>(byGap).map(([g, d]) => [g, d.count || 0] as [string, number]).sort((a, b) => b[1] - a[1])
      const maxG = Math.max(1, ...gaps.map(([, c]) => c))
      const dirs = ([['Left', rda.left_pct], ['Right', rda.right_pct], ['Inside', rda.inside_pct], ['Outside', rda.outside_pct]] as [string, number][]).filter(([, v]) => v != null)
      gapTable = `<div style="flex:1;min-width:230px">
        <div style="font-size:11px;font-weight:bold;color:#1a5c2a;text-transform:uppercase;margin-bottom:4px">Run Gaps (carries)</div>
        <table style="border-collapse:collapse;width:100%;font-size:12px">
          <tr>${gaps.length ? gaps.map(([g]) => `<td style="text-align:center;font-size:10px;color:#666">${g}</td>`).join('') : '<td style="font-size:10px;color:#999">no gap detail</td>'}</tr>
          <tr>${gaps.map(([, c]) => `<td style="background:rgba(26,92,42,${(0.15 + 0.7 * (c / maxG)).toFixed(2)});color:#fff;font-weight:bold;text-align:center;padding:8px;border:2px solid #fff">${c}</td>`).join('')}</tr>
        </table>
        ${dirs.length ? `<div style="font-size:10px;color:#666;margin-top:4px">${dirs.map(([l, v]) => `${l} ${Math.round(v)}%`).join(' · ')}${rda.total_runs ? ` · ${rda.total_runs} runs` : ''}</div>` : ''}
      </div>`
    }
    const sideLine = (sideDist.left_pct != null) ? `<div style="font-size:11px;color:#555;margin-top:8px">Pass field side: <b>${Math.round(sideDist.left_pct || 0)}%</b> left · <b>${Math.round(sideDist.middle_pct || 0)}%</b> middle · <b>${Math.round(sideDist.right_pct || 0)}%</b> right</div>` : ''
    return `<section><h2>Field Heat Maps — Where They Attack</h2><div style="display:flex;gap:24px;flex-wrap:wrap">${passTable}${gapTable}</div>${sideLine}<div style="font-size:10px;color:#888;margin-top:6px">Darker green = more volume.</div></section>`
  }

  // Print/PDF basketball shot chart (light theme) — parity with the football
  // field map above, so the PDF carries the same "where they score, and how well"
  // visual as the screen. eFG-banded, with priority take-aways flagged.
  const buildBasketballHeatMapHtml = (s: any): string => {
    const szm = s?.shot_zone_map || {}
    const zones: Record<string, any> = szm.zones || {}
    const rows = Object.entries(zones).sort((a: any, b: any) => (b[1].attempts || 0) - (a[1].attempts || 0))
    if (!rows.length) {
      return `<section><h2>Shot Chart — Where They Score</h2><p style="color:#555;font-style:italic">No readable shot-zone detail on this film yet — usually a thin or low-confidence breakdown. Run a full or DEEP breakdown of the whole game and the shot chart fills in.</p></section>`
    }
    const maxAtt = Math.max(1, ...rows.map(([, z]: any) => z.attempts || 0))
    const anyEfg = rows.some(([, z]: any) => z.efg_pct != null)
    const pctLabel = anyEfg ? 'eFG' : 'FG'
    const body = rows.map(([zone, z]: any) => {
      const shotPct = z.efg_pct ?? z.fg_pct
      const color = z.band_color || '#888'
      const w = Math.max(6, ((z.attempts || 0) / maxAtt) * 100)
      const pri = z.priority_takeaway ? '🚨 ' : ''
      return `<tr>
        <td style="font-size:11px;color:#222;text-align:right;padding:3px 8px;white-space:nowrap;font-weight:${z.priority_takeaway ? 700 : 400}">${pri}${zone}</td>
        <td style="width:52%;padding:3px 4px"><div style="height:16px;background:#eee;border-radius:3px"><div style="height:100%;width:${w}%;background:${color};border-radius:3px"></div></div></td>
        <td style="font-size:11px;color:#333;padding:3px 6px;white-space:nowrap">${z.made}/${z.attempts} &middot; ${z.pct_of_all_shots}% &middot; <b style="color:${color}">${shotPct}% ${pctLabel}</b></td>
      </tr>`
    }).join('')
    const pri: string[] = szm.priority_takeaways || []
    const priLine = pri.length
      ? `<div style="font-size:12px;color:#b23b2b;margin-top:8px">🚨 <b>Take these away:</b> ${pri.join(', ')} — they shoot here often and well.</div>`
      : ''
    return `<section><h2>Shot Chart — Where They Score</h2><table style="border-collapse:collapse;width:100%">${body}</table>${priLine}<div style="font-size:10px;color:#888;margin-top:6px">Bar length = shot volume &middot; color = eFG% (shot quality). Red = take it away, green = make them shoot it.</div></section>`
  }

  // Print/PDF run-pass matrix (§12 Map 4) — light theme, appended to the football
  // heat maps so the PDF carries the down-and-hash tendency grid too.
  const buildRunPassMatrixHtml = (s: any): string => {
    const m = s?.offense?.run_pass_matrix
    if (!m || !m.rows?.length || !m.cols?.length) return ''
    const head = `<tr><th></th>${m.cols.map((c: string) => `<th style="font-size:10px;color:#555;padding:2px 6px;text-transform:uppercase">${c}</th>`).join('')}</tr>`
    const body = m.rows.map((row: string) => {
      const tds = m.cols.map((col: string) => {
        const c = m.cells[row]?.[col]
        if (!c || c.total === 0) return `<td style="background:#f4f4f0;border:2px solid #fff;min-width:52px"></td>`
        const bg = c.low_sample ? '#e8e8e2' : c.color
        const fg = (c.low_sample || c.band === 'balanced' || c.band === 'none') ? '#333' : '#fff'
        return `<td style="background:${bg};color:${fg};text-align:center;padding:6px 4px;border:2px solid #fff${c.low_sample ? ';opacity:0.7' : ''}"><div style="font-size:14px;font-weight:bold">${Math.round(c.run_pct ?? 0)}%</div><div style="font-size:8px">${c.total} pl</div></td>`
      }).join('')
      return `<tr><td style="font-size:11px;color:#222;font-weight:bold;text-align:right;padding-right:8px">${row}</td>${tds}</tr>`
    }).join('')
    return `<section><h2>Run / Pass Matrix — By Down &amp; Distance</h2><table style="border-collapse:collapse"><thead>${head}</thead><tbody>${body}</tbody></table><div style="font-size:10px;color:#888;margin-top:5px">Number = run share of that down &amp; distance (small number = plays). Grey = too few to call. Red = run, purple = pass.</div></section>`
  }

  // Print/PDF turnover map (§12 Map 3) — clustered bars, top flagged. Appended to
  // the basketball shot chart in the PDF.
  const buildTurnoverMapHtml = (s: any): string => {
    const esc = (v: string) => (v || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const tm = s?.turnover_map
    if (!tm || !tm.zones?.length) return ''
    const max = Math.max(1, ...tm.zones.map((z: any) => z.count))
    const rows = tm.zones.map((z: any, i: number) => {
      const top = i === 0 && !!tm.force_here
      const w = Math.max(6, (z.count / max) * 100)
      const color = top ? '#c0392b' : '#8a7a4a'
      return `<tr>
        <td style="font-size:11px;color:#222;text-align:right;padding:3px 8px;white-space:nowrap;font-weight:${top ? 700 : 400}">${top ? '🎯 ' : ''}${esc(z.zone)}</td>
        <td style="width:55%;padding:3px 4px"><div style="height:14px;background:#eee;border-radius:3px"><div style="height:100%;width:${w}%;background:${color};border-radius:3px"></div></div></td>
        <td style="font-size:11px;color:#333;padding:3px 6px;white-space:nowrap">${z.count} &middot; ${z.pct}%</td>
      </tr>`
    }).join('')
    const force = tm.force_here ? `<div style="font-size:12px;color:#b23b2b;margin-top:6px">🎯 <b>${esc(tm.force_here)}</b></div>` : ''
    return `<section><h2>Turnovers — Where They Give It Away</h2>${force}<table style="border-collapse:collapse;width:100%">${rows}</table><div style="font-size:10px;color:#888;margin-top:5px">Grouped by what they were running — single-camera film has no turnover court coordinates.</div></section>`
  }

  // One branded print/PDF renderer for every format. Blocks are {heading, body}.
  const printDoc = (opts: {
    title: string; subtitle: string; blocks: Section[]; watermarked: boolean
    counts?: [string, any][]; hint?: string; heatMapHtml?: string
  }) => {
    const esc = (s: string) => (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const date = report?.generated_at ? new Date(report.generated_at).toLocaleDateString() : ''
    const sectionsHtml = (opts.blocks || []).map(sec => `
      <section><h2>${esc(sec.heading)}</h2>${bodyToHtml(esc, sec.body)}</section>`).join('')
    const counts = (opts.counts || []).filter(([, v]) => typeof v === 'number')
    const html = `<!DOCTYPE html><html><head><meta charset="utf-8"/>
      <title>${esc(opts.title)} — ${esc(opts.subtitle)}</title>
      <style>
        @page { margin: 0.75in; }
        body { font-family: Georgia, 'Times New Roman', serif; color: #1c1c1c; line-height: 1.55; max-width: 800px; margin: 0 auto; padding: 24px; }
        .brand { font-size: 12px; letter-spacing: 0.15em; color: #1a5c2a; font-weight: bold; text-transform: uppercase; }
        h1 { font-size: 24px; margin: 4px 0 2px; }
        .sub { font-size: 13px; color: #1a5c2a; font-weight: bold; margin-bottom: 2px; }
        .meta { color: #666; font-size: 12px; margin-bottom: 18px; }
        .hint { font-size: 12px; color: #555; font-style: italic; margin-bottom: 14px; }
        .counts { display: flex; gap: 28px; border: 1px solid #1a5c2a; border-radius: 8px; padding: 14px 18px; margin-bottom: 22px; }
        .count .n { font-size: 22px; font-weight: bold; } .count .l { font-size: 11px; color: #666; text-transform: uppercase; }
        section { margin-bottom: 18px; page-break-inside: avoid; }
        h2 { font-size: 15px; color: #1a5c2a; border-bottom: 2px solid #C9A84C; padding-bottom: 4px; margin-bottom: 8px; }
        p { font-size: 13px; margin: 0 0 8px; } ul { margin: 0 0 8px; padding-left: 20px; } li { font-size: 13px; margin: 0 0 4px; }
        strong { color: #111; }
        .footer { margin-top: 24px; border-top: 1px solid #ccc; padding-top: 10px; font-size: 10px; color: #999; text-align: center; }
        .wm { color: #C9A84C; font-size: 11px; border: 1px dashed #C9A84C; padding: 6px 10px; border-radius: 6px; margin-bottom: 16px; }
        .ferpa { font-size: 10px; color: #777; border: 1px solid #ddd; background: #fafafa; border-radius: 5px; padding: 6px 10px; margin-bottom: 14px; }
      </style></head><body>
      <div class="brand">CoachLenz — AI Film Analyst</div>
      <h1>${esc(opts.title)}</h1>
      <div class="sub">${esc(opts.subtitle)}</div>
      <div class="meta">${esc(report?.sport || '')} · Opponent Scouting${date ? ' · ' + date : ''}</div>
      <div class="ferpa">${FERPA_NOTE}</div>
      ${opts.hint ? `<div class="hint">${esc(opts.hint)}</div>` : ''}
      ${opts.watermarked ? '<div class="wm">TRIAL REPORT — Upgrade at coachlenz.com to remove watermark</div>' : ''}
      ${counts.length ? `<div class="counts">${counts.map(([l, v]) => `<div class="count"><div class="n">${v}</div><div class="l">${esc(l)}</div></div>`).join('')}</div>` : ''}
      ${opts.heatMapHtml || ''}
      ${sectionsHtml}
      <div class="footer">Generated by CoachLenz · Powered by Cosby AI Solutions</div>
      </body></html>`
    const w = window.open('', '_blank', 'width=900,height=1000')
    if (!w) { alert('Please allow pop-ups to print or save the report as PDF.'); return }
    w.document.write(html); w.document.close(); w.focus()
    setTimeout(() => w.print(), 400)
  }

  const handlePrint = () => {
    if (!report) return
    const s: any = report.summary || {}
    printDoc({
      title: report.title, subtitle: 'Coordinator Report', watermarked: report.watermarked,
      blocks: report.sections || [],
      counts: [['Total Plays', s.total_plays], ['Offense', s.offense_plays],
               ['Defense', s.defense_plays], ['Special Teams', s.special_teams_plays]],
      heatMapHtml: (() => {
        const sport = String(report.sport || '').toLowerCase()
        if (sport.includes('football')) return buildHeatMapHtml(s) + buildRunPassMatrixHtml(s)
        if (sport === 'basketball') return buildBasketballHeatMapHtml(s) + buildTurnoverMapHtml(s)
        return ''
      })(),
    })
  }

  const [exporting, setExporting] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const [shareOpen, setShareOpen] = useState(false)
  const [sharing, setSharing] = useState(false)
  const [share, setShare] = useState<{ url: string; expires_at: string } | null>(null)
  const [shareCopied, setShareCopied] = useState(false)

  const downloadCsv = async () => {
    if (!report) return
    setMenuOpen(false)
    try {
      const res = await api.get(`/reports/${report.id}/export/csv`, { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }))
      const a = document.createElement('a')
      a.href = url; a.download = `report-${report.id}-plays.csv`; a.click()
      URL.revokeObjectURL(url)
    } catch { alert('Could not download the CSV.') }
  }

  const createShareLink = async () => {
    if (!report) return
    setSharing(true)
    try {
      const res = await api.post(`/reports/${report.id}/share`)
      const url = `${window.location.origin}${res.data.share_path}`
      setShare({ url, expires_at: res.data.expires_at })
      try { await navigator.clipboard.writeText(url); setShareCopied(true); setTimeout(() => setShareCopied(false), 2000) } catch { /* clipboard may be blocked */ }
    } catch { alert('Could not create a share link.') }
    finally { setSharing(false) }
  }

  const revokeShareLink = async () => {
    if (!report) return
    try { await api.delete(`/reports/${report.id}/share`); setShare(null) } catch { /* ignore */ }
  }

  const exportFormat = async (format: string, unit?: string, player?: string) => {
    if (!report) return
    setMenuOpen(false); setExporting(format + (unit || '') + (player || ''))
    try {
      const params = new URLSearchParams({ format })
      if (unit) params.set('unit', unit)
      if (player) params.set('player', player)
      const res = await api.get(`/reports/${report.id}/export?${params.toString()}`)
      const p = res.data
      printDoc({ title: p.title, subtitle: p.subtitle, blocks: p.blocks || [],
                 watermarked: p.watermarked, hint: p.unit_hint })
    } catch {
      alert('Could not build that export.')
    } finally { setExporting('') }
  }
  // §11 Player One-Pager: a single print-ready page for players (6th-grade, no
  // stats). Its payload (key/watch/run/do/heatmap) differs from the block formats,
  // so it gets a dedicated print renderer rather than the shared printDoc.
  const printOnePager = (p: any) => {
    const esc = (s: string) => (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const date = report?.generated_at ? new Date(report.generated_at).toLocaleDateString() : ''
    const watch = (p.watch || []).map((w: any) => `<li><b>#${esc(w.jersey)}</b> ${esc(w.cue)}</li>`).join('')
    const run = (p.run || []).map((r: string) => `<li>${esc(r)}</li>`).join('')
    const doList = (p.do || []).map((d: string) => `<li>${esc(d)}</li>`).join('')
    const heat = p.heatmap ? `
      <div class="heat">
        ${(p.heatmap.zones || []).map((z: any) =>
          `<span class="cell" style="background:${z.color}"><span class="zn">${esc(z.zone)}</span><span class="zl">${esc(z.label)}</span></span>`).join('')}
      </div>
      <div class="cap">${esc(p.heatmap.caption || '')}</div>` : ''
    const html = `<!DOCTYPE html><html><head><meta charset="utf-8"/>
      <title>${esc(p.title)} - Player Game Plan</title>
      <style>
        @page { margin: 0.6in; size: letter; }
        * { box-sizing: border-box; }
        body { font-family: 'Helvetica Neue', Arial, sans-serif; color: #14140f; line-height: 1.5; max-width: 760px; margin: 0 auto; padding: 20px; }
        .bar { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 3px solid #1a5c2a; padding-bottom: 8px; margin-bottom: 16px; }
        .bar .b { font-size: 13px; font-weight: 800; letter-spacing: 0.12em; color: #1a5c2a; text-transform: uppercase; }
        .bar .vs { font-size: 15px; font-weight: 700; }
        .bar .dt { font-size: 12px; color: #666; }
        .key { background: #f4efdc; border: 2px solid #C9A84C; border-radius: 10px; padding: 14px 18px; margin-bottom: 18px; }
        .key .h { font-size: 13px; font-weight: 800; color: #9a7d22; letter-spacing: 0.1em; margin-bottom: 4px; }
        .key .k { font-size: 22px; font-weight: 800; line-height: 1.3; }
        h2 { font-size: 15px; color: #1a5c2a; letter-spacing: 0.06em; text-transform: uppercase; margin: 16px 0 6px; }
        ul { margin: 0 0 8px; padding-left: 22px; } li { font-size: 15px; margin: 0 0 6px; }
        .heat { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0 4px; }
        .cell { flex: 1; min-width: 90px; color: #fff; border-radius: 8px; padding: 10px 8px; text-align: center; display: flex; flex-direction: column; gap: 2px; }
        .cell .zn { font-size: 13px; font-weight: 700; } .cell .zl { font-size: 11px; opacity: 0.95; }
        .cap { font-size: 12px; color: #555; font-style: italic; margin-bottom: 12px; }
        .ferpa { font-size: 10px; color: #888; border-top: 1px solid #ccc; padding-top: 8px; margin-top: 18px; }
        .foot { font-size: 11px; color: #999; text-align: center; margin-top: 6px; }
        .wm { color: #9a7d22; font-size: 11px; border: 1px dashed #C9A84C; padding: 5px 9px; border-radius: 6px; margin-bottom: 14px; display: inline-block; }
      </style></head><body>
      <div class="bar"><span class="b">CoachLenz &middot; Game Plan</span><span class="vs">vs ${esc(p.title)}</span><span class="dt">${esc(date)}</span></div>
      ${report?.watermarked ? '<div class="wm">TRIAL - upgrade at coachlenz.com</div>' : ''}
      ${p.key ? `<div class="key"><div class="h">&#128273; THE KEY</div><div class="k">${esc(p.key)}</div></div>` : ''}
      ${watch ? `<h2>&#128064; Who To Watch</h2><ul>${watch}</ul>` : ''}
      ${run ? `<h2>&#128203; What They Run</h2><ul>${run}</ul>` : ''}
      ${doList ? `<h2>&#9989; What We Do</h2><ul>${doList}</ul>` : ''}
      ${heat}
      <div class="ferpa">${esc(p.confidential_note || '')}</div>
      <div class="foot">CoachLenz AI &middot; coachlenz.com &middot; Ready in 5-10 min &middot; Powered by Cosby AI Solutions</div>
      </body></html>`
    const w = window.open('', '_blank', 'width=820,height=1000')
    if (!w) { alert('Please allow pop-ups to print or save the game plan as PDF.'); return }
    w.document.write(html); w.document.close(); w.focus()
    setTimeout(() => w.print(), 400)
  }

  const exportOnePager = async () => {
    if (!report) return
    setMenuOpen(false); setExporting('player_onepager')
    try {
      const res = await api.get(`/reports/${report.id}/export?format=player_onepager`)
      printOnePager(res.data)
    } catch {
      alert('Could not build the player game plan.')
    } finally { setExporting('') }
  }

  // Position-coach brief units are sport-specific: basketball groups by Guards /
  // Wings / Bigs, football by unit. Codes match backend report_export unit maps.
  const POSITION_UNITS: { code: string; label: string }[] = report?.sport === 'basketball'
    ? [{ code: 'G', label: 'Guards' }, { code: 'W', label: 'Wings' }, { code: 'B', label: 'Bigs' }]
    : ['OL', 'DL', 'WR', 'DB', 'QB', 'LB', 'RB', 'ST'].map(c => ({ code: c, label: c }))

  const retry = async () => {
    setRetrying(true)
    try {
      await api.post(`/reports/${id}/retry`)
      setReport(r => (r ? { ...r, status: 'generating', message: null } : r))
      setPolling(true)
    } catch { /* stay on the failed screen; the user can try again */ }
    finally { setRetrying(false) }
  }

  const handleDeleteReport = async () => {
    if (!window.confirm('Delete this report permanently? This cannot be undone.')) return
    setDeleting(true)
    try { await api.delete(`/reports/${id}`); router.push('/reports') }
    catch { setDeleting(false) }
  }

  if (report?.status === 'failed') {
    return (
      <div className="flex h-screen overflow-hidden">
        <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
        <Sidebar />
        <main className="flex-1 flex flex-col items-center justify-center gap-4 px-6 text-center">
          <AlertTriangle size={26} style={{ color: '#C9A84C' }} />
          <p style={{ color: '#f8f6f0', fontSize: 16, fontWeight: 700 }}>Report couldn&apos;t be generated</p>
          <p style={{ color: '#7a7a6e', maxWidth: 440 }}>{report.message || 'This report could not be generated. Please try again in a few minutes.'}</p>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 4 }}>
            <button onClick={retry} disabled={retrying}
              style={{ background: '#1B4332', color: '#fff', padding: '8px 18px', borderRadius: 8, fontWeight: 600, display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer' }}>
              {retrying && <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />} Try again
            </button>
            <Link href="/reports" style={{ color: '#7a7a6e', fontSize: 13, textDecoration: 'none' }}>Back to reports</Link>
            <button onClick={handleDeleteReport} disabled={deleting}
              style={{ background: 'transparent', color: '#e07070', border: 'none', fontSize: 13, cursor: 'pointer' }}>
              Delete report
            </button>
          </div>
        </main>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 flex flex-col items-center justify-center gap-4 px-6 text-center">
          {loadError ? (
            <>
              <p style={{ color: '#4B5563', maxWidth: 420 }}>{loadError}</p>
              <button
                onClick={() => window.location.reload()}
                style={{ background: '#1B4332', color: '#fff', padding: '8px 18px', borderRadius: 8, fontWeight: 600 }}
              >
                Refresh
              </button>
            </>
          ) : (
            <Loader2 size={24} style={{ color: '#C9A84C', animation: 'spin 1s linear infinite' }} />
          )}
        </main>
      </div>
    )
  }

  const isProcessing = !report.generated_at

  return (
    <div className="flex h-screen overflow-hidden">
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        {/* Header */}
        <div style={{
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          padding: '14px 32px', position: 'sticky', top: 0,
          background: '#1c1c1c', zIndex: 10,
          display: 'flex', alignItems: 'center', gap: 14,
        }}>
          <Link href="/reports" style={{ color: '#7a7a6e', display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, textDecoration: 'none' }}>
            <ChevronLeft size={15} /> Reports
          </Link>
          <span style={{ color: 'rgba(255,255,255,0.15)' }}>/</span>
          <span style={{ fontSize: 14, fontWeight: 600, color: '#f8f6f0' }}>{report.title}</span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 10, alignItems: 'center' }}>
            {report.watermarked && (
              <span style={{
                fontSize: 10, color: '#C9A84C', letterSpacing: '0.12em',
                background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.2)',
                padding: '3px 10px', borderRadius: 12,
              }}>TRIAL REPORT</span>
            )}
            {report.generated_at && (
              <span style={{ fontSize: 11, color: '#7a7a6e' }}>
                {new Date(report.generated_at).toLocaleDateString()}
              </span>
            )}
            {report.generated_at && (report.sections?.length ?? 0) > 0 && (
              <>
                <button
                  onClick={handlePrint}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6, background: '#C9A84C', color: '#1c1c1c',
                    border: 'none', borderRadius: 4, padding: '7px 14px', fontSize: 12, fontWeight: 700,
                    cursor: 'pointer', letterSpacing: '0.04em',
                  }}
                  title="Opens a printable full report — print or Save as PDF"
                >
                  <Printer size={14} /> Print / Save PDF
                </button>
                <div style={{ position: 'relative' }}>
                  <button
                    onClick={() => setMenuOpen(o => !o)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 6, background: 'transparent', color: '#C9A84C',
                      border: '1px solid rgba(201,168,76,0.4)', borderRadius: 4, padding: '7px 12px', fontSize: 12,
                      fontWeight: 700, cursor: 'pointer', letterSpacing: '0.04em',
                    }}
                    title="Export a specific report format"
                  >
                    {exporting ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                    Export <ChevronDown size={13} />
                  </button>
                  {menuOpen && (
                    <div style={{
                      position: 'absolute', right: 0, top: 'calc(100% + 6px)', zIndex: 20,
                      background: '#232323', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8,
                      padding: 8, width: 260, boxShadow: '0 10px 30px rgba(0,0,0,0.4)',
                    }}>
                      <button onClick={() => exportFormat('coordinator')} style={menuItem}>Coordinator Report <span style={menuHint}>full detail</span></button>
                      <button onClick={() => exportFormat('head_coach')} style={menuItem}>Head Coach Summary <span style={menuHint}>one page</span></button>
                      <button onClick={() => exportFormat('player')} style={menuItem}>Player Bulletins <span style={menuHint}>per player</span></button>
                      <button onClick={exportOnePager} style={menuItem}>Player Game Plan <span style={menuHint}>1 page, print</span></button>
                      <div style={{ fontSize: 10, color: '#7a7a6e', letterSpacing: '0.1em', padding: '8px 8px 4px' }}>POSITION COACH BRIEF</div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, padding: '0 4px 4px' }}>
                        {POSITION_UNITS.map(u => (
                          <button key={u.code} onClick={() => exportFormat('position', u.code)} style={unitChip}>{u.label}</button>
                        ))}
                      </div>
                      <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', marginTop: 6, paddingTop: 6 }}>
                        <button onClick={downloadCsv} style={menuItem}>Play data (CSV) <span style={menuHint}>every tagged play</span></button>
                      </div>
                    </div>
                  )}
                </div>
                <div style={{ position: 'relative' }}>
                  <button
                    onClick={() => { setShareOpen(o => !o); setMenuOpen(false) }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 6, background: 'transparent', color: '#C9A84C',
                      border: '1px solid rgba(201,168,76,0.4)', borderRadius: 4, padding: '7px 12px', fontSize: 12,
                      fontWeight: 700, cursor: 'pointer', letterSpacing: '0.04em',
                    }}
                    title="Create a read-only public link"
                  >
                    <Share2 size={14} /> Share
                  </button>
                  {shareOpen && (
                    <div style={{
                      position: 'absolute', right: 0, top: 'calc(100% + 6px)', zIndex: 20,
                      background: '#232323', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8,
                      padding: 8, width: 300, boxShadow: '0 10px 30px rgba(0,0,0,0.4)',
                    }}>
                      {!share ? (
                        <button onClick={createShareLink} disabled={sharing} style={menuItem}>
                          {sharing ? 'Creating…' : 'Create read-only link'} <span style={menuHint}>7-day, no login</span>
                        </button>
                      ) : (
                        <div style={{ padding: 4 }}>
                          <input readOnly value={share.url} onFocus={e => e.currentTarget.select()}
                            style={{ width: '100%', fontSize: 11, padding: '6px 8px', background: '#1c1c1c', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, color: '#f8f6f0' }} />
                          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                            <button onClick={() => { navigator.clipboard.writeText(share.url); setShareCopied(true); setTimeout(() => setShareCopied(false), 2000) }}
                              style={{ flex: 1, fontSize: 12, fontWeight: 700, background: '#C9A84C', color: '#1c1c1c', border: 'none', borderRadius: 4, padding: '6px', cursor: 'pointer' }}>
                              {shareCopied ? 'Copied!' : 'Copy link'}
                            </button>
                            <button onClick={revokeShareLink}
                              style={{ fontSize: 12, fontWeight: 700, background: 'transparent', color: '#e57373', border: '1px solid rgba(229,115,115,0.4)', borderRadius: 4, padding: '6px 10px', cursor: 'pointer' }}>
                              Revoke
                            </button>
                          </div>
                          <div style={{ fontSize: 10, color: '#7a7a6e', marginTop: 6 }}>Expires {new Date(share.expires_at).toLocaleDateString()}</div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}
            <button
              onClick={handleDeleteReport}
              disabled={deleting}
              title="Delete this report"
              style={{
                display: 'flex', alignItems: 'center', gap: 6, background: 'transparent', color: '#e07070',
                border: '1px solid rgba(224,112,112,0.35)', borderRadius: 4, padding: '7px 12px', fontSize: 12,
                fontWeight: 700, cursor: 'pointer', letterSpacing: '0.04em',
              }}
            >
              {deleting ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Trash2 size={14} />} Delete
            </button>
          </div>
        </div>

        <div style={{ maxWidth: 860, margin: '0 auto', padding: '32px 32px 64px' }}>
          {/* §9 FERPA confidentiality notice — on every report output */}
          <div style={{
            fontSize: 11, color: '#7a7a6e', background: 'rgba(255,255,255,0.02)',
            border: '1px solid rgba(255,255,255,0.06)', borderRadius: 6,
            padding: '8px 14px', marginBottom: 20,
          }}>
            🔒 {FERPA_NOTE}
          </div>

          {/* Processing state */}
          {isProcessing && (
            <div style={{
              background: 'rgba(201,168,76,0.07)', border: '1px solid rgba(201,168,76,0.2)',
              borderRadius: 8, padding: '24px 32px', textAlign: 'center', marginBottom: 32,
            }}>
              <Loader2 size={32} style={{ color: '#C9A84C', animation: 'spin 1s linear infinite', margin: '0 auto 12px', display: 'block' }} />
              <div style={{ fontSize: 15, fontWeight: 600, color: '#f8f6f0', marginBottom: 6 }}>
                AI is analyzing your film...
              </div>
              <div style={{ fontSize: 13, color: '#7a7a6e' }}>
                This can take a few minutes for a full game. The page will update automatically.
              </div>
            </div>
          )}

          {/* Summary box */}
          {report.summary && (
            <div style={{
              background: 'linear-gradient(135deg, rgba(26,92,42,0.15), rgba(26,92,42,0.05))',
              border: '1px solid rgba(45,140,64,0.25)',
              borderRadius: 8, padding: '20px 24px', marginBottom: 28,
            }}>
              <div style={{ fontSize: 11, letterSpacing: '0.15em', color: '#2d8c40', marginBottom: 10, fontWeight: 700 }}>
                PLAYS ANALYZED
              </div>
              {typeof report.summary === 'string'
                ? <RichText text={report.summary} />
                : (() => {
                    // Only show scalar count fields; skip nested objects (detailed in sections below).
                    const counts: { label: string; value: any }[] = []
                    const s: any = report.summary
                    const order = [
                      ['total_plays', 'Total Plays'],
                      ['offense_plays', 'Offense'],
                      ['defense_plays', 'Defense'],
                      ['special_teams_plays', 'Special Teams'],
                    ]
                    order.forEach(([k, label]) => {
                      if (typeof s[k] === 'number') counts.push({ label, value: s[k] })
                    })
                    // Only the curated headline counts above. We deliberately do NOT
                    // dump every remaining scalar: single-cam detection surfaces
                    // unreliable raw counts (timeouts, steals, blocks it mislabels from
                    // stoppages) that read as authoritative headline stats when they are
                    // not. Per-category detail (with its confidence) lives in the sections.
                    return (
                      <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap' }}>
                        {counts.map(c => (
                          <div key={c.label}>
                            <div style={{ fontSize: 24, fontWeight: 700, color: '#f8f6f0', fontFamily: 'var(--font-bebas)' }}>{String(c.value)}</div>
                            <div style={{ fontSize: 11, color: '#7a7a6e', textTransform: 'capitalize' }}>{c.label}</div>
                          </div>
                        ))}
                      </div>
                    )
                  })()
              }
            </div>
          )}

          {/* Field heat maps (football) — rendered from the report summary, no extra call */}
          {String(report.sport || '').toLowerCase().includes('football')
            && report.summary && typeof report.summary !== 'string' && (
            <div style={{ marginBottom: 28 }}>
              <FieldHeatMap summary={report.summary} />
            </div>
          )}

          {/* Run/Pass tendency matrix (football) — §12 Map 4 */}
          {String(report.sport || '').toLowerCase().includes('football')
            && report.summary && typeof report.summary !== 'string' && (
            <div style={{ marginBottom: 28 }}>
              <RunPassMatrix summary={report.summary} />
            </div>
          )}

          {/* Shot chart + key players (basketball) — rendered from the report summary */}
          {String(report.sport || '').toLowerCase() === 'basketball'
            && report.summary && typeof report.summary !== 'string' && (
            <div style={{ marginBottom: 28 }}>
              <BasketballShotChart summary={report.summary} />
            </div>
          )}

          {/* Individual player shot spots (basketball) — §12 Map 2 */}
          {String(report.sport || '').toLowerCase() === 'basketball'
            && report.summary && typeof report.summary !== 'string'
            && report.summary.player_shot_zones?.length > 0 && (
            <div style={{ marginBottom: 28 }}>
              <PlayerShotSpots summary={report.summary} />
            </div>
          )}

          {/* Turnover cluster map (basketball) — §12 Map 3 */}
          {String(report.sport || '').toLowerCase() === 'basketball'
            && report.summary && typeof report.summary !== 'string'
            && report.summary.turnover_map && (
            <div style={{ marginBottom: 28 }}>
              <TurnoverMap summary={report.summary} />
            </div>
          )}

          {/* Low-res film warning: the score-bug and jersey reads are capped by the
              lowest-res source game. Only shown when we actually know it's low-res. */}
          {report.low_res_film && (
            <div style={{
              background: 'rgba(224,160,80,0.08)', border: '1px dashed rgba(224,160,80,0.4)',
              borderRadius: 6, padding: '12px 20px', marginBottom: 24,
              display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: '#e0a050',
            }}>
              <AlertTriangle size={14} />
              <span>
                <b>Low-res film{report.film_min_height ? ` (${report.film_min_height}p)` : ''}.</b>{' '}
                Jersey numbers and the down &amp; distance on the scoreboard are harder to read at this resolution, so some tags may be missing. Re-ingest this game in HD for sharper detection.
              </span>
            </div>
          )}

          {/* Watermark banner */}
          {report.watermarked && (
            <div style={{
              background: 'rgba(201,168,76,0.05)', border: '1px dashed rgba(201,168,76,0.3)',
              borderRadius: 6, padding: '12px 20px', marginBottom: 24,
              display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: '#C9A84C',
            }}>
              <AlertTriangle size={14} />
              This is a trial report. <Link href="/settings/billing" style={{ color: '#C9A84C', fontWeight: 700 }}>Upgrade</Link> to unlock full reports with unlimited plays and export.
            </div>
          )}

          {/* Sections */}
          {report.sections && report.sections.length > 0 ? (() => {
            const displaySections = recoverSections(report.sections)
            return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ fontSize: 11, letterSpacing: '0.15em', color: '#7a7a6e', marginBottom: 4, fontWeight: 700 }}>
                TENDENCY ANALYSIS — {displaySections.length} SECTION{displaySections.length !== 1 ? 'S' : ''}
              </div>
              {displaySections.map((s, i) => <SectionCard key={i} section={s} />)}
            </div>
            )
          })() : !isProcessing ? (
            <div style={{ textAlign: 'center', color: '#7a7a6e', padding: '48px 0' }}>
              <FileText size={40} style={{ margin: '0 auto 12px', display: 'block', opacity: 0.3 }} />
              <div>No report content generated. The AI worker may still be starting up.</div>
            </div>
          ) : null}

          {/* Ask the Film Assistant — report-scoped chat, only on a finished report */}
          {report.generated_at && <ReportChat reportId={report.id} />}
        </div>
      </main>
    </div>
  )
}
