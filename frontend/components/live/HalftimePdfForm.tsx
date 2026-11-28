'use client'
/**
 * Free printable Halftime Sheet PDF, double opt-in (Jason, Nov 28).
 *
 * Name + email (+ optional phone, never texted). Submitting only sends a confirmation
 * email; the PDF is emailed after the coach clicks that link. Nothing downloads here.
 */
import { useState, type CSSProperties } from 'react'
import Link from 'next/link'
import { publicApi } from '@/lib/api'
import { Loader2, Mail } from 'lucide-react'
import { CONSENT_LINE, clientLeadError, detailMessage, leadPayload, type LeadForm } from './halftimeLead'

const input: CSSProperties = {
  width: '100%', minHeight: 48, borderRadius: 10, border: '1px solid var(--border)',
  background: 'var(--bg)', color: 'var(--text)', padding: '0 12px', fontSize: 16, boxSizing: 'border-box',
}
const label: CSSProperties = { display: 'block', fontSize: 13, fontWeight: 700, color: 'var(--text2)', margin: '12px 0 6px' }
const btn: CSSProperties = {
  width: '100%', minHeight: 48, borderRadius: 10, border: '1px solid var(--gold)', cursor: 'pointer',
  background: 'transparent', color: 'var(--gold)', fontSize: 16, fontWeight: 800,
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: 14,
}

const EMPTY: LeadForm = { name: '', email: '', phone: '', consent: false, company: '' }

export default function HalftimePdfForm() {
  const [f, setF] = useState<LeadForm>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sentTo, setSentTo] = useState('')
  const [resendMsg, setResendMsg] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const msg = clientLeadError(f)
    if (msg) { setError(msg); return }
    setBusy(true); setError('')
    try {
      await publicApi.post('/leads/halftime-sheet', leadPayload(f))
      setSentTo(f.email.trim())
    } catch (err: any) {
      setError(detailMessage(err, 'Could not send the confirmation email. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  async function resend() {
    setResendMsg('')
    try {
      const r = await publicApi.post('/leads/halftime-sheet/resend', { email: sentTo })
      setResendMsg(r.data?.message || 'A new confirmation link is on its way.')
    } catch (err: any) {
      setResendMsg(detailMessage(err, 'Could not resend right now. Please try again in a minute.'))
    }
  }

  if (sentTo) {
    return (
      <div role="status">
        <b style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}><Mail size={18} /> Check your email</b>
        <p style={{ fontSize: 14, color: 'var(--text2)', lineHeight: 1.5, margin: 0 }}>
          We sent a confirmation link to <b>{sentTo}</b>. Click it within 24 hours and we will email you the Halftime Sheet PDF.
        </p>
        <button type="button" onClick={resend} style={btn}>Resend the link</button>
        {resendMsg && <p style={{ fontSize: 13, color: 'var(--text3)', margin: '8px 0 0' }}>{resendMsg}</p>}
      </div>
    )
  }

  return (
    <form onSubmit={submit} noValidate>
      <p style={{ fontSize: 14, color: 'var(--text2)', lineHeight: 1.5, margin: '0 0 4px' }}>
        Prefer paper? Get the printable Halftime Sheet free. Confirm your email and we will email you the PDF.
      </p>
      <label style={label} htmlFor="hs-name">Name</label>
      <input id="hs-name" style={input} autoComplete="name" value={f.name} maxLength={100}
        onChange={e => setF({ ...f, name: e.target.value })} />
      <label style={label} htmlFor="hs-email">Email</label>
      <input id="hs-email" style={input} type="email" inputMode="email" autoComplete="email" value={f.email}
        onChange={e => setF({ ...f, email: e.target.value })} />
      <label style={label} htmlFor="hs-phone">Phone <span style={{ fontWeight: 400, color: 'var(--text3)' }}>(optional, never texted)</span></label>
      <input id="hs-phone" style={input} type="tel" inputMode="tel" autoComplete="tel" value={f.phone} maxLength={40}
        onChange={e => setF({ ...f, phone: e.target.value })} />
      {/* Honeypot: hidden from people and screen readers; bots fill it in. */}
      <div aria-hidden="true" style={{ position: 'absolute', left: '-10000px', width: 1, height: 1, overflow: 'hidden' }}>
        <label htmlFor="hs-company">Company</label>
        <input id="hs-company" tabIndex={-1} autoComplete="off" value={f.company}
          onChange={e => setF({ ...f, company: e.target.value })} />
      </div>
      <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginTop: 14, fontSize: 13, color: 'var(--text2)', lineHeight: 1.45, minHeight: 44, cursor: 'pointer' }}>
        <input type="checkbox" checked={f.consent} onChange={e => setF({ ...f, consent: e.target.checked })}
          style={{ width: 22, height: 22, flexShrink: 0, marginTop: 1 }} />
        <span>
          {CONSENT_LINE} See our <Link href="/privacy" style={{ color: 'var(--gold)' }}>Privacy Policy</Link>.
        </span>
      </label>
      {error && <div role="alert" style={{ background: 'var(--redl)', color: 'var(--red)', borderRadius: 8, padding: '10px 14px', marginTop: 12, fontSize: 14 }}>{error}</div>}
      <button type="submit" disabled={busy} style={{ ...btn, opacity: busy ? 0.7 : 1 }}>
        {busy ? <Loader2 size={18} className="animate-spin" /> : <Mail size={18} />}
        {busy ? 'Sending…' : 'Email me the free PDF'}
      </button>
    </form>
  )
}
