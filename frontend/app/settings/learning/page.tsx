'use client'
import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { Loader2, Brain, ChevronLeft, Check, X, RotateCcw, Download } from 'lucide-react'

// Per-account learning loop controls (Engine §14). The coach sees what the loop
// has learned from their corrections, accepts/rejects each proposed relabel, and
// can switch the whole loop to Manual Mode. Everything is their account only.

interface Adjustment {
  id: string
  sport: string
  field: string
  from_value: string
  to_value: string
  support_count: number
  status: string
  note?: string
}

interface Summary {
  manual_mode: boolean
  score: { total_corrections: number; high: number; low: number; reclass: number; systematic: number }
  adjustments: { pending: number; active: number; rejected: number }
}

export default function LearningSettingsPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [summary, setSummary] = useState<Summary | null>(null)
  const [pending, setPending] = useState<Adjustment[]>([])
  const [active, setActive] = useState<Adjustment[]>([])
  const [busy, setBusy] = useState<string>('')

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])

  const load = useCallback(async () => {
    const [s, p, a] = await Promise.all([
      api.get('/learning/summary').then(r => r.data).catch(() => null),
      api.get('/learning/adjustments?status=pending').then(r => r.data.adjustments).catch(() => []),
      api.get('/learning/adjustments?status=active').then(r => r.data.adjustments).catch(() => []),
    ])
    setSummary(s); setPending(p); setActive(a)
  }, [])

  useEffect(() => { if (user) load() }, [user, load])

  if (isLoading || !user) return null

  const act = async (id: string, action: 'accept' | 'reject' | 'reset') => {
    setBusy(id + action)
    try { await api.post(`/learning/adjustments/${id}/${action}`); await load() }
    finally { setBusy('') }
  }

  const toggleManual = async () => {
    if (!summary) return
    setBusy('manual')
    try { await api.post('/learning/manual-mode', { enabled: !summary.manual_mode }); await load() }
    finally { setBusy('') }
  }

  const exportCsv = async () => {
    try {
      const res = await api.get('/learning/corrections/export', { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }))
      const el = document.createElement('a')
      el.href = url; el.download = 'labeling-history.csv'; el.click()
      URL.revokeObjectURL(url)
    } catch { /* nothing to export yet */ }
  }

  const AdjustmentRow = ({ a, activeRow }: { a: Adjustment; activeRow?: boolean }) => (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px',
      border: '1px solid rgba(255,255,255,0.07)', borderRadius: 8, background: 'rgba(255,255,255,0.02)',
    }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, color: 'var(--text)' }}>
          <span style={{ textTransform: 'capitalize', color: 'var(--text3)' }}>{a.sport} · {a.field}:</span>{' '}
          <span style={{ textDecoration: 'line-through', color: 'var(--text3)' }}>{a.from_value}</span>{' → '}
          <strong style={{ color: 'var(--gold)' }}>{a.to_value}</strong>
        </div>
        <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 2 }}>
          Backed by {a.support_count} of your corrections
        </div>
      </div>
      {activeRow ? (
        <button onClick={() => act(a.id, 'reset')} disabled={!!busy}
          className="btn-outline" style={{ display: 'inline-flex', gap: 6, alignItems: 'center', fontSize: 12 }}>
          <RotateCcw size={13} /> Turn off
        </button>
      ) : (
        <>
          <button onClick={() => act(a.id, 'accept')} disabled={!!busy}
            className="btn-primary" style={{ display: 'inline-flex', gap: 6, alignItems: 'center', fontSize: 12, padding: '6px 12px' }}>
            <Check size={13} /> Accept
          </button>
          <button onClick={() => act(a.id, 'reject')} disabled={!!busy}
            className="btn-outline" style={{ display: 'inline-flex', gap: 6, alignItems: 'center', fontSize: 12 }}>
            <X size={13} /> Reject
          </button>
        </>
      )}
    </div>
  )

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div style={{ maxWidth: 680, margin: '0 auto' }}>
          <Link href="/settings" style={{ color: 'var(--text3)', fontSize: 13, display: 'inline-flex', alignItems: 'center', gap: 4, textDecoration: 'none', marginBottom: 14 }}>
            <ChevronLeft size={15} /> Settings
          </Link>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
            <Brain size={20} style={{ color: 'var(--gold)' }} />
            <h2 className="text-2xl font-bold">Learning Loop</h2>
          </div>
          <p style={{ color: 'var(--text3)', fontSize: 13, marginBottom: 24 }}>
            CoachLenz learns how <em>you</em> label film. When it sees the same fix again and again,
            it proposes a change you approve. Your corrections train only your account.
          </p>

          {/* Score */}
          {summary && (
            <div className="card" style={{ marginBottom: 18 }}>
              <div style={{ fontWeight: 700, marginBottom: 12 }}>What you&apos;ve taught it</div>
              <div style={{ display: 'flex', gap: 26, flexWrap: 'wrap' }}>
                {[
                  ['Corrections', summary.score.total_corrections],
                  ['Added detail', summary.score.high],
                  ['Relabels', summary.score.reclass],
                  ['Patterns found', summary.score.systematic],
                  ['Active', summary.adjustments.active],
                ].map(([label, v]) => (
                  <div key={label as string}>
                    <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)' }}>{v as number}</div>
                    <div style={{ fontSize: 11, color: 'var(--text3)' }}>{label as string}</div>
                  </div>
                ))}
              </div>
              <button onClick={exportCsv} className="btn-outline" style={{ marginTop: 14, display: 'inline-flex', gap: 6, alignItems: 'center', fontSize: 12 }}>
                <Download size={13} /> Export my labeling history (CSV)
              </button>
            </div>
          )}

          {/* Pending proposals */}
          <div className="card" style={{ marginBottom: 18 }}>
            <div style={{ fontWeight: 700, marginBottom: 12 }}>Proposed changes {pending.length > 0 && <span style={{ color: 'var(--gold)' }}>({pending.length})</span>}</div>
            {pending.length === 0 ? (
              <p style={{ fontSize: 13, color: 'var(--text3)' }}>
                No proposals yet. Keep correcting the AI&apos;s tags — once a fix repeats, it&apos;ll show up here for your approval.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {pending.map(a => <AdjustmentRow key={a.id} a={a} />)}
              </div>
            )}
          </div>

          {/* Active */}
          {active.length > 0 && (
            <div className="card" style={{ marginBottom: 18 }}>
              <div style={{ fontWeight: 700, marginBottom: 12 }}>Active in your reports</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {active.map(a => <AdjustmentRow key={a.id} a={a} activeRow />)}
              </div>
            </div>
          )}

          {/* Manual mode */}
          {summary && (
            <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700 }}>Manual Mode</div>
                <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 2 }}>
                  {summary.manual_mode
                    ? 'On — the loop records your corrections but proposes and applies nothing automatically.'
                    : 'Off — the loop proposes changes from your corrections for you to approve.'}
                </div>
              </div>
              <button onClick={toggleManual} disabled={busy === 'manual'}
                className={summary.manual_mode ? 'btn-primary' : 'btn-outline'}
                style={{ display: 'inline-flex', gap: 6, alignItems: 'center', fontSize: 12 }}>
                {busy === 'manual' ? <Loader2 size={14} className="animate-spin" /> : null}
                {summary.manual_mode ? 'Turn loop back on' : 'Switch to Manual Mode'}
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
