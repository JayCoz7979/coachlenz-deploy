'use client'
/**
 * Tendency Engine - ranked, situational tendencies pulled from the latest
 * finished scout report. Read-only. Wired to /reports + /reports/{id}.summary.
 * Purely defensive: if a field is missing, the cell (or whole section) drops
 * out. Never fabricates numbers.
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import api from '@/lib/api'
import OSShell from '@/components/os/OSShell'

// ── helpers ────────────────────────────────────────────────────────────────

// Percentages arrive either as 0-1 fractions or already as 0-100 values.
function pct(n: any): number | null {
  const v = Number(n)
  if (!isFinite(v)) return null
  return v <= 1 ? Math.round(v * 100) : Math.round(v)
}

// Pull a leading percentage out of a coordinator statement, if one exists.
function pctFromText(text: any): number | null {
  if (typeof text !== 'string') return null
  const m = text.match(/(\d{1,3}(?:\.\d+)?)\s*%/)
  if (!m) return null
  const v = Math.round(Number(m[1]))
  return isFinite(v) ? v : null
}

// Confidence tier (may carry a trailing "*") -> tag class + label.
function confTag(confidence: any): { cls: string; label: string } | null {
  if (typeof confidence !== 'string') return null
  const tier = confidence.replace(/\*/g, '').trim().toUpperCase()
  if (tier === 'HIGH') return { cls: 'tg', label: 'High' }
  if (tier === 'MEDIUM') return { cls: 'tgo', label: 'Medium' }
  if (tier === 'LOW') return { cls: 'tq', label: 'Low' }
  return null
}

const DOWN_SITS: { key: string; label: string }[] = [
  { key: 'first_down', label: '1st Down' },
  { key: 'third_short', label: '3rd & Short' },
  { key: 'third_long', label: '3rd & Long' },
  { key: 'red_zone', label: 'Red Zone' },
  { key: 'goal_line', label: 'Goal Line' },
  { key: 'two_minute_drill', label: '2-Minute Drill' },
]

const BLITZ_LABELS: Record<string, string> = {
  '3rd_long_6plus': '3rd & Long (6+)',
  '3rd_medium_4to5': '3rd & Medium',
  '3rd_short_1to3': '3rd & Short',
  '2nd_long_7plus': '2nd & Long',
  '1st_and_10': '1st & 10',
}

function humanizeKey(k: string): string {
  if (BLITZ_LABELS[k]) return BLITZ_LABELS[k]
  return k.replace(/_/g, ' ')
}

// ── cell model ─────────────────────────────────────────────────────────────

interface Cell {
  sit: string
  call: string
  pct: number | null
  n: string | null
  tag: { cls: string; label: string } | null
}

function TendCell({ c }: { c: Cell }) {
  return (
    <div className="tend-cell">
      <div className="tend-cell-sit">
        {c.sit}
        {c.tag && (
          <span className={'tag ' + c.tag.cls} style={{ marginLeft: 6 }}>
            {c.tag.label}
          </span>
        )}
      </div>
      <div className="tend-cell-call">{c.call}</div>
      {c.pct != null && <div className="tend-cell-pct">{c.pct}%</div>}
      {c.pct != null && (
        <div className="tend-cell-bar">
          <div
            className="tend-cell-fill"
            style={{ width: Math.min(Math.max(c.pct, 0), 100) + '%' }}
          />
        </div>
      )}
      {c.n && <div className="tend-cell-n">{c.n}</div>}
    </div>
  )
}

function Section({ title, cells }: { title: string; cells: Cell[] }) {
  if (!cells.length) return null
  return (
    <>
      <div className="sec-title" style={{ margin: '4px 0 12px' }}>
        {title}
      </div>
      <div className="tend-g">
        {cells.map((c, i) => (
          <TendCell key={title + '-' + i} c={c} />
        ))}
      </div>
    </>
  )
}

// ── builders ───────────────────────────────────────────────────────────────

function buildSituational(summary: any): Cell[] {
  const list = summary?.scouting?.situational_tendencies
  if (!Array.isArray(list)) return []
  return list
    .map((t: any): Cell | null => {
      const sit = t?.category
      const call = t?.statement
      if (!sit || !call) return null
      return {
        sit: String(sit),
        call: String(call),
        pct: pctFromText(call),
        n: t?.sample != null ? `${t.sample} instances` : null,
        tag: confTag(t?.confidence),
      }
    })
    .filter((c): c is Cell => c !== null)
}

function buildDownDistance(summary: any): Cell[] {
  const off = summary?.offense
  if (!off) return []
  const cells: Cell[] = []
  for (const { key, label } of DOWN_SITS) {
    const d = off[key]
    if (!d) continue
    const total = Number(d.total)
    if (!isFinite(total) || total <= 0) continue
    const runP = pct(d.run_pct)
    const passP = pct(d.pass_pct)
    if (runP == null && passP == null) continue
    const isRun = (runP ?? 0) >= (passP ?? 0)
    const dominant = isRun ? runP : passP
    const nParts = [`${total} plays`]
    const avg = Number(d.avg_yards)
    if (isFinite(avg) && avg) nParts.push(`${avg} ypp`)
    cells.push({
      sit: label,
      call: isRun ? 'Run' : 'Pass',
      pct: dominant,
      n: nParts.join(' · '),
      tag: null,
    })
  }
  return cells
}

function buildDefense(summary: any): Cell[] {
  const bbs = summary?.defense?.blitz_by_situation
  if (!bbs || typeof bbs !== 'object') return []
  const cells: Cell[] = []
  for (const key of Object.keys(bbs)) {
    const d = bbs[key]
    if (!d) continue
    const total = Number(d.total)
    if (!isFinite(total) || total <= 0) continue
    const bp = pct(d.blitz_pct)
    if (bp == null) continue
    cells.push({
      sit: humanizeKey(key),
      call: 'Blitz',
      pct: bp,
      n: `${total} plays`,
      tag: { cls: 'tr', label: 'Pressure' },
    })
  }
  return cells
}

function scoutingKeyText(k: any): string | null {
  if (typeof k === 'string') return k
  if (k && typeof k === 'object' && typeof k.statement === 'string') return k.statement
  return null
}

// ── page ───────────────────────────────────────────────────────────────────

export default function TendenciesPage() {
  const [loading, setLoading] = useState(true)
  const [summary, setSummary] = useState<any>(null)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const res = await api.get('/reports')
        const reports: any[] = Array.isArray(res.data) ? res.data : []
        const finished = reports
          .filter((r) => r && r.generated_at)
          .sort(
            (a, b) =>
              new Date(b.generated_at).getTime() - new Date(a.generated_at).getTime()
          )
        const latest = finished[0]
        if (!latest?.id) {
          if (alive) setSummary(null)
          return
        }
        const detail = await api.get(`/reports/${latest.id}`)
        if (alive) setSummary(detail.data?.summary ?? null)
      } catch {
        if (alive) setSummary(null)
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  const situational = summary ? buildSituational(summary) : []
  const downDistance = summary ? buildDownDistance(summary) : []
  const defense = summary ? buildDefense(summary) : []

  const scoutingKeys: string[] = Array.isArray(summary?.scouting?.scouting_keys)
    ? summary.scouting.scouting_keys
        .map(scoutingKeyText)
        .filter((s: string | null): s is string => !!s)
    : []

  const hasAny =
    situational.length > 0 || downDistance.length > 0 || defense.length > 0

  return (
    <OSShell title="Tendency Engine">
      <div className="sec-title" style={{ marginBottom: 16 }}>
        🧠 AI Tendency Engine
      </div>

      {loading && (
        <div className="card">
          <div className="card-body" style={{ color: 'var(--text3)', fontSize: 13 }}>
            Loading the latest scout report...
          </div>
        </div>
      )}

      {!loading && !hasAny && (
        <div className="card">
          <div className="card-hdr">
            <div className="card-title">🧠 Tendency Engine</div>
          </div>
          <div
            className="card-body"
            style={{ color: 'var(--text2)', fontSize: 13, lineHeight: 1.7 }}
          >
            <p style={{ margin: '0 0 12px' }}>
              The Tendency Engine activates once your first scout report is
              generated.
            </p>
            <Link href="/scout" style={{ color: 'var(--green3)', fontWeight: 600 }}>
              Start a scout →
            </Link>
          </div>
        </div>
      )}

      {!loading && hasAny && (
        <div>
          <Section title="Situational Tendencies" cells={situational} />
          <Section title="Down & Distance" cells={downDistance} />
          <Section title="Defensive Pressure" cells={defense} />

          {scoutingKeys.length > 0 && (
            <div className="ai-box">
              <strong>Auto Scouting Keys:</strong>
              <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
                {scoutingKeys.map((k, i) => (
                  <li key={i} style={{ marginBottom: 4 }}>
                    {k}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div className="powered">
        Powered by{' '}
        <a href="https://cosbyaisolutions.com" target="_blank" rel="noreferrer">
          Cosby AI Solutions
        </a>
      </div>
    </OSShell>
  )
}
