'use client'
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { MessageSquare, Send, Loader2, Film, AlertTriangle } from 'lucide-react'
import api from '@/lib/api'

// Report-scoped AI Coach Chat (Engine §13). Asks the Film Assistant questions
// about THIS report; answers come only from the report's film. Identity is
// disclosed, confidence is surfaced, and low-confidence answers are flagged —
// the coach always knows how much to trust a reply (UATP).

interface Cutup {
  id: number
  clip_id: string | null
  time_seconds: number
  event_type?: string | null
  player?: string | null
  label: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  confidence?: number | null
  answered?: boolean | null
  cutups?: Cutup[]
  created_at?: string | null
}

function mmss(seconds: number): string {
  const s = Math.max(0, Math.round(seconds || 0))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

// Confidence band -> label + color (mirrors services.agent_log bands).
function band(c?: number | null): { label: string; color: string } | null {
  if (c === null || c === undefined) return { label: 'Unverified', color: '#7a7a6e' }
  if (c >= 0.8) return { label: 'High confidence', color: '#2d8c40' }
  if (c >= 0.65) return { label: 'Medium confidence', color: '#C9A84C' }
  return { label: 'Low — verify on film', color: '#e0a070' }
}

const chip: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, fontWeight: 600,
  background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.25)',
  color: '#C9A84C', borderRadius: 6, padding: '3px 8px',
}

export default function ReportChat({ reportId }: { reportId: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    api.get(`/reports/${reportId}/chat`)
      .then(r => setMessages(r.data.messages || []))
      .catch(() => { /* empty thread is fine */ })
  }, [reportId])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending])

  const send = async () => {
    const q = input.trim()
    if (!q || sending) return
    setError(null)
    setSending(true)
    // Optimistic: show the question immediately.
    const optimistic: ChatMessage = { id: `tmp-${Date.now()}`, role: 'user', content: q }
    setMessages(m => [...m, optimistic])
    setInput('')
    try {
      const res = await api.post(`/reports/${reportId}/chat`, { question: q })
      setMessages(m => [...m, res.data.answer])
    } catch (e: any) {
      // Drop the optimistic question back into the box so nothing is lost.
      setMessages(m => m.filter(x => x.id !== optimistic.id))
      setInput(q)
      setError(e?.response?.data?.detail ?? 'The film assistant is unavailable right now. Try again in a moment.')
    } finally {
      setSending(false)
    }
  }

  return (
    <div style={{ marginTop: 32 }}>
      <div style={{
        background: '#2e2e2e', borderRadius: 8, border: '1px solid rgba(255,255,255,0.06)',
        overflow: 'hidden',
      }}>
        {/* Identity disclosure — the assistant says who it is and its one rule. */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, padding: '14px 20px',
          borderBottom: '1px solid rgba(255,255,255,0.06)', background: 'rgba(201,168,76,0.04)',
        }}>
          <div style={{
            width: 32, height: 32, borderRadius: 6, background: 'rgba(201,168,76,0.1)',
            border: '1px solid rgba(201,168,76,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <MessageSquare size={15} style={{ color: '#C9A84C' }} />
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#f8f6f0' }}>Ask the Film Assistant</div>
            <div style={{ fontSize: 12, color: '#7a7a6e' }}>Answers come only from this game&apos;s film. Included with your report.</div>
          </div>
        </div>

        {/* Thread */}
        <div ref={scrollRef} style={{ maxHeight: 420, overflowY: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
          {messages.length === 0 && !sending && (
            <div style={{ color: '#7a7a6e', fontSize: 13, textAlign: 'center', padding: '18px 0' }}>
              Try: &ldquo;What do they run on 3rd and long?&rdquo; or &ldquo;Who do I have to stop?&rdquo;
            </div>
          )}

          {messages.map(m => (
            <div key={m.id} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
              <div style={{
                maxWidth: '82%',
                background: m.role === 'user' ? 'rgba(27,67,50,0.5)' : '#252525',
                border: `1px solid ${m.role === 'user' ? 'rgba(45,140,64,0.3)' : 'rgba(255,255,255,0.07)'}`,
                borderRadius: 10, padding: '10px 14px',
              }}>
                <div style={{ fontSize: 13, color: '#ede9df', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{m.content}</div>

                {/* Assistant footer: confidence band, verify flag, cited cutups.
                    Skipped on an ungrounded answer — the message already says so. */}
                {m.role === 'assistant' && m.answered !== false && (
                  <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
                    {(() => { const b = band(m.confidence); return b ? (
                      <span style={{ fontSize: 11, fontWeight: 600, color: b.color }}>● {b.label}</span>
                    ) : null })()}
                    {m.answered === true && (m.confidence ?? 1) < 0.65 && (
                      <span style={{ ...chip, background: 'rgba(224,160,112,0.1)', border: '1px solid rgba(224,160,112,0.3)', color: '#e0a070' }}>
                        <AlertTriangle size={11} /> Double-check this
                      </span>
                    )}
                    {(m.cutups || []).map(c => (
                      <span key={c.id} style={chip} title={c.label}>
                        <Film size={11} /> {mmss(c.time_seconds)}{c.player ? ` · #${c.player}` : ''}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}

          {sending && (
            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <div style={{ background: '#252525', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 10, padding: '10px 14px' }}>
                <Loader2 size={15} style={{ color: '#C9A84C', animation: 'spin 1s linear infinite' }} />
              </div>
            </div>
          )}
        </div>

        {/* Composer */}
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', padding: 14 }}>
          {error && <div style={{ fontSize: 12, color: '#e07070', marginBottom: 8 }}>{error}</div>}
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              placeholder="Ask about this opponent…"
              maxLength={1000}
              disabled={sending}
              style={{
                flex: 1, background: '#1c1c1c', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8,
                color: '#f8f6f0', fontSize: 13, padding: '10px 12px', outline: 'none',
              }}
            />
            <button
              onClick={send}
              disabled={sending || !input.trim()}
              style={{
                display: 'flex', alignItems: 'center', gap: 6, background: '#C9A84C', color: '#1c1c1c',
                border: 'none', borderRadius: 8, padding: '0 16px', fontSize: 13, fontWeight: 700,
                cursor: sending || !input.trim() ? 'default' : 'pointer', opacity: sending || !input.trim() ? 0.5 : 1,
              }}
            >
              <Send size={14} /> Ask
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
