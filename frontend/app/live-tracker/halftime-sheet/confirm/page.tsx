'use client'
/**
 * /live-tracker/halftime-sheet/confirm?token=...  (double opt-in, step 2)
 *
 * The coach clicks "Confirm my email" here; that POST is what confirms the lead and
 * emails the PDF. Using a click (not an automatic GET) means a mail scanner that
 * prefetches the link cannot burn the single-use token. Expired, used, or invalid
 * links get a clear message and a way to request a fresh one.
 */
import { useEffect, useState, type CSSProperties } from 'react'
import Link from 'next/link'
import { publicApi } from '@/lib/api'
import { CheckCircle2, Loader2, Mail } from 'lucide-react'
import { confirmErrorView, detailMessage, type ConfirmView } from '@/components/live/halftimeLead'
import logo from '../../../../public/coachlenz-logo.png'

const card: CSSProperties = { background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: 18, marginTop: 18 }
const btn: CSSProperties = {
  width: '100%', minHeight: 52, borderRadius: 12, border: 'none', cursor: 'pointer',
  background: 'var(--gold)', color: '#1c1c1c', fontSize: 16, fontWeight: 800,
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: 14,
}
const input: CSSProperties = {
  width: '100%', minHeight: 48, borderRadius: 10, border: '1px solid var(--border)',
  background: 'var(--bg)', color: 'var(--text)', padding: '0 12px', fontSize: 16, boxSizing: 'border-box', marginTop: 10,
}

export default function ConfirmHalftimeSheetPage() {
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [view, setView] = useState<ConfirmView | null>(null)
  const [email, setEmail] = useState('')
  const [resendMsg, setResendMsg] = useState('')

  useEffect(() => {
    setToken(new URLSearchParams(window.location.search).get('token') || '')
  }, [])

  async function confirm() {
    setBusy(true); setResendMsg('')
    try {
      const r = await publicApi.post('/leads/halftime-sheet/confirm', { token })
      setView({ kind: 'confirmed', message: r.data?.message || 'You are confirmed. Check your email for the PDF.' })
    } catch (e: any) {
      setView(confirmErrorView(e?.response?.status, e?.response?.data?.detail))
    } finally {
      setBusy(false)
    }
  }

  async function resend(useToken: boolean) {
    setResendMsg('')
    try {
      const body = useToken ? { token } : { email: email.trim() }
      const r = await publicApi.post('/leads/halftime-sheet/resend', body)
      setResendMsg(r.data?.message || 'A new confirmation link is on its way.')
    } catch (e: any) {
      setResendMsg(detailMessage(e, 'Could not resend right now. Please try again in a minute.'))
    }
  }

  const failed = view && view.kind !== 'confirmed' ? view : null

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}>
      <main style={{ maxWidth: 520, margin: '0 auto', padding: '24px 18px 48px' }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={logo.src} alt="CoachLenz" style={{ height: 28, width: 'auto' }} />
        <div style={card}>
          <h1 style={{ fontSize: 22, fontWeight: 800, margin: '0 0 8px' }}>Your free Halftime Sheet PDF</h1>

          {!view && (
            <>
              <p style={{ fontSize: 15, color: 'var(--text2)', lineHeight: 1.5, margin: 0 }}>
                Confirm your email and we will email you the printable Halftime Sheet.
              </p>
              <button onClick={confirm} disabled={busy || !token} style={{ ...btn, opacity: (busy || !token) ? 0.7 : 1 }}>
                {busy ? <Loader2 size={18} className="animate-spin" /> : <CheckCircle2 size={18} />}
                {busy ? 'Confirming…' : 'Confirm my email'}
              </button>
              {!token && <p style={{ fontSize: 13, color: 'var(--text3)', marginTop: 10 }}>This link is missing its code. Open the link from your email again.</p>}
            </>
          )}

          {view?.kind === 'confirmed' && (
            <div role="status">
              <p style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 15, margin: 0 }}>
                <CheckCircle2 size={18} style={{ color: 'var(--green3)' }} /> {view.message}
              </p>
              <p style={{ fontSize: 13, color: 'var(--text3)', marginTop: 10 }}>Not there in a few minutes? Check your spam folder.</p>
            </div>
          )}

          {failed && (
            <div role="alert">
              <p style={{ fontSize: 15, color: 'var(--text2)', lineHeight: 1.5, margin: 0 }}>{failed.message}</p>
              {failed.canResendWithToken ? (
                <button onClick={() => resend(true)} style={btn}><Mail size={18} /> Send me a new link</button>
              ) : (
                <form onSubmit={e => { e.preventDefault(); resend(false) }}>
                  <input style={input} type="email" inputMode="email" autoComplete="email" placeholder="you@school.org"
                    aria-label="Email" value={email} onChange={e => setEmail(e.target.value)} />
                  <button type="submit" disabled={!email.trim()} style={{ ...btn, opacity: email.trim() ? 1 : 0.7 }}><Mail size={18} /> Send me a new link</button>
                </form>
              )}
              {resendMsg && <p style={{ fontSize: 13, color: 'var(--text3)', marginTop: 10 }}>{resendMsg}</p>}
            </div>
          )}
        </div>

        <p style={{ fontSize: 14, marginTop: 18 }}>
          <Link href="/live-tracker" style={{ color: 'var(--gold)', display: 'inline-flex', alignItems: 'center', minHeight: 44 }}>Back to the Live Tracker</Link>
        </p>
        <p style={{ textAlign: 'center', fontSize: 12, color: 'var(--text3)', marginTop: 24 }}>
          Powered by <a href="https://cosbyaisolutions.com" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--gold)' }}>Cosby AI Solutions</a>
        </p>
      </main>
    </div>
  )
}
