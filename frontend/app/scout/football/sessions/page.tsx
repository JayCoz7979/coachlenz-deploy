'use client'
import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { ClipboardCheck, Loader2, ShieldCheck, CheckCircle2, XCircle, Plus } from 'lucide-react'

type Session = {
  session_id: string
  opponent: string
  game_date: string | null
  analyst: string | null
  reviewer: string | null
  status: string
  is_mine: boolean
  can_review: boolean
}

const STATUS_STYLE: Record<string, { bg: string; fg: string; label: string }> = {
  draft: { bg: 'var(--bg3)', fg: 'var(--text3)', label: 'Draft' },
  reviewed: { bg: 'rgba(201,168,76,0.15)', fg: 'var(--gold)', label: 'Reviewed' },
  final: { bg: 'rgba(46,125,50,0.18)', fg: 'var(--green3)', label: 'Final' },
}

export default function ScoutFootballSessionsPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [sessions, setSessions] = useState<Session[]>([])
  const [canReview, setCanReview] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState('')
  const [error, setError] = useState('')

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])

  const load = useCallback(async () => {
    try {
      const res = await api.get('/scout/football/sessions')
      setSessions(res.data.sessions || [])
      setCanReview(!!res.data.you_can_review)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Could not load sessions.')
    } finally { setLoading(false) }
  }, [])
  useEffect(() => { if (user) load() }, [user, load])

  async function review(sessionId: string, decision: 'reviewed' | 'final' | 'changes_requested') {
    setBusyId(sessionId); setError('')
    try {
      await api.post('/scout/football/review', { session_id: sessionId, decision })
      await load()
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Sign-off failed.')
    } finally { setBusyId('') }
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div style={{ maxWidth: 1000, margin: '0 auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <ClipboardCheck size={22} style={{ color: 'var(--gold)' }} />
              <h2 className="text-2xl font-bold" style={{ margin: 0 }}>Football Scout Sessions</h2>
            </div>
            <Link href="/scout/football" className="btn-green" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <Plus size={14} /> New Scout
            </Link>
          </div>
          <p style={{ color: 'var(--text3)', fontSize: 13, marginBottom: 20 }}>
            {canReview
              ? 'You have review authority. Sign off a peer’s scout to satisfy Gate 2 (dual review).'
              : 'Your drafts. A head coach, coordinator, reviewer, or owner must sign off before a report can be FINAL.'}
          </p>

          {error && (
            <div style={{ background: 'var(--redl)', border: '1px solid rgba(224,112,112,0.3)', color: 'var(--red)', borderRadius: 8, padding: '10px 14px', marginBottom: 14, fontSize: 13 }}>{error}</div>
          )}

          {loading ? (
            <div style={{ color: 'var(--text3)', display: 'flex', alignItems: 'center', gap: 8 }}><Loader2 size={16} className="animate-spin" /> Loading…</div>
          ) : sessions.length === 0 ? (
            <div className="card" style={{ color: 'var(--text3)' }}>No football scouting sessions yet. Start one from “New Scout”.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {sessions.map(s => {
                const st = STATUS_STYLE[s.status] || STATUS_STYLE.draft
                const busy = busyId === s.session_id
                return (
                  <div key={s.session_id} className="card" style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: 200 }}>
                      <div style={{ fontWeight: 700, fontSize: 15 }}>{s.opponent || 'Opponent'}</div>
                      <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 2 }}>
                        {s.game_date || 'no date'} · analyst {s.analyst || '-'}
                        {s.reviewer ? ` · reviewed by ${s.reviewer}` : ''}
                        {s.is_mine ? ' · yours' : ''}
                      </div>
                    </div>
                    <span style={{ background: st.bg, color: st.fg, fontSize: 11, fontWeight: 800, borderRadius: 6, padding: '3px 10px' }}>{st.label}</span>

                    {s.can_review && s.status !== 'final' && (
                      <div style={{ display: 'flex', gap: 6 }}>
                        {busy ? <Loader2 size={16} className="animate-spin" style={{ color: 'var(--text3)' }} /> : (
                          <>
                            {s.status === 'draft' && (
                              <button onClick={() => review(s.session_id, 'reviewed')} className="btn-green" style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12 }}>
                                <ShieldCheck size={13} /> Sign off
                              </button>
                            )}
                            <button onClick={() => review(s.session_id, 'final')} className="btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12 }}>
                              <CheckCircle2 size={13} /> Mark Final
                            </button>
                            <button onClick={() => review(s.session_id, 'changes_requested')} style={{ background: 'transparent', border: '1px solid var(--border2)', borderRadius: 8, color: 'var(--text3)', padding: '6px 10px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12 }}>
                              <XCircle size={13} /> Changes
                            </button>
                          </>
                        )}
                      </div>
                    )}
                    <Link href={`/scout/football?session=${s.session_id}`} style={{ fontSize: 12, color: 'var(--green3)' }}>open</Link>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
