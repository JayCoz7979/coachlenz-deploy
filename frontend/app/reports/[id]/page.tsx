'use client'
import { useEffect, useState, Fragment, type CSSProperties } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import Link from 'next/link'
import { ChevronLeft, Loader2, FileText, AlertTriangle, TrendingUp, Shield, Zap, Target, Printer, Download, ChevronDown } from 'lucide-react'
import FieldHeatMap from '@/components/report/FieldHeatMap'

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
  generated_at: string | null
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

const SECTION_ICONS: Record<string, any> = {
  run: TrendingUp,
  pass: Target,
  defense: Shield,
  red_zone: Zap,
  tendency: TrendingUp,
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

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])

  useEffect(() => {
    if (!user || !id) return
    const load = () => api.get(`/reports/${id}`).then(r => {
      setReport(r.data)
      if (!r.data.generated_at) setPolling(true)
      else setPolling(false)
    })
    load()
  }, [user, id])

  // Poll every 5s while still processing
  useEffect(() => {
    if (!polling) return
    const t = setInterval(() => {
      api.get(`/reports/${id}`).then(r => {
        setReport(r.data)
        if (r.data.generated_at) { setPolling(false) }
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

  // One branded print/PDF renderer for every format. Blocks are {heading, body}.
  const printDoc = (opts: {
    title: string; subtitle: string; blocks: Section[]; watermarked: boolean
    counts?: [string, any][]; hint?: string
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
      </style></head><body>
      <div class="brand">CoachLenz — AI Film Analyst</div>
      <h1>${esc(opts.title)}</h1>
      <div class="sub">${esc(opts.subtitle)}</div>
      <div class="meta">${esc(report?.sport || '')} · Opponent Scouting${date ? ' · ' + date : ''}</div>
      ${opts.hint ? `<div class="hint">${esc(opts.hint)}</div>` : ''}
      ${opts.watermarked ? '<div class="wm">TRIAL REPORT — Upgrade at coachlenz.com to remove watermark</div>' : ''}
      ${counts.length ? `<div class="counts">${counts.map(([l, v]) => `<div class="count"><div class="n">${v}</div><div class="l">${esc(l)}</div></div>`).join('')}</div>` : ''}
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
    })
  }

  const [exporting, setExporting] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
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
  const POSITION_UNITS = ['OL', 'DL', 'WR', 'DB', 'QB', 'LB', 'RB', 'ST']

  if (!report) {
    return (
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 flex items-center justify-center">
          <Loader2 size={24} style={{ color: '#C9A84C', animation: 'spin 1s linear infinite' }} />
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
                      <div style={{ fontSize: 10, color: '#7a7a6e', letterSpacing: '0.1em', padding: '8px 8px 4px' }}>POSITION COACH BRIEF</div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, padding: '0 4px 4px' }}>
                        {POSITION_UNITS.map(u => (
                          <button key={u} onClick={() => exportFormat('position', u)} style={unitChip}>{u}</button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>

        <div style={{ maxWidth: 860, margin: '0 auto', padding: '32px 32px 64px' }}>
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
                This usually takes 30–90 seconds. The page will update automatically.
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
                    // Fallback: any other scalar fields
                    Object.entries(s).forEach(([k, v]) => {
                      if (typeof v !== 'object' && !order.find(o => o[0] === k)) {
                        counts.push({ label: k.replace(/_/g, ' '), value: v })
                      }
                    })
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
          {(report.sport === 'football' || report.sport === 'flag_football')
            && report.summary && typeof report.summary !== 'string' && (
            <div style={{ marginBottom: 28 }}>
              <FieldHeatMap summary={report.summary} />
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
        </div>
      </main>
    </div>
  )
}
