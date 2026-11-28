'use client'
/**
 * Free printable Halftime Sheet PDF, traded for a name + a valid email (phone optional).
 *
 * The server (POST /leads/halftime-pdf) does the real validation: email format, a
 * disposable-domain blocklist, and an MX/domain lookup; rate limits; and a honeypot.
 * After a successful submit the download link is shown right here. Nothing is texted:
 * the phone field is optional and is never texted.
 */
import { useState, type CSSProperties, type FormEvent } from 'react'
import Link from 'next/link'
import { publicApi } from '@/lib/api'
import { Download, Loader2, FileText } from 'lucide-react'

// Must match CONSENT_TEXT in backend/routers/lead_magnet.py (stored with each lead).
export const HALFTIME_PDF_CONSENT =
  'I agree that CoachLenz may email me the Halftime Sheet and follow-up about CoachLenz. See the Privacy Policy.'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const label: CSSProperties = { display: 'block', fontSize: 13, fontWeight: 700, color: 'var(--text2)', margin: '0 0 6px' }
const input: CSSProperties = { width: '100%', minHeight: 48, fontSize: 16 }
// Off-screen (not display:none, which some bots skip). Hidden from people and screen readers.
const honeypot: CSSProperties = { position: 'absolute', left: '-10000px', top: 'auto', width: 1, height: 1, overflow: 'hidden' }

export default function HalftimePdfForm() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [consent, setConsent] = useState(false)
  const [website, setWebsite] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [downloadPath, setDownloadPath] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    if (!name.trim()) { setError('Enter your name.'); return }
    if (!email.trim()) { setError('Enter your email address.'); return }
    if (!consent) { setError('Please check the box to agree to email follow-up.'); return }
    setBusy(true)
    try {
      const r = await publicApi.post('/leads/halftime-pdf', {
        name: name.trim(), email: email.trim(), phone: phone.trim() || null, consent, website,
      })
      setDownloadPath(r.data?.download_path || null)
      setDone(true)
    } catch (err: any) {
      const status = err?.response?.status
      const d = err?.response?.data?.detail
      if (status === 429) setError('Too many tries. Please wait a minute and try again.')
      else if (typeof d === 'string') setError(d)
      else setError('Could not send the form. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <div role="status">
        <b style={{ display: 'block', fontSize: 16, marginBottom: 6 }}>Your Halftime Sheet is ready</b>
        {downloadPath ? (
          <>
            <p style={{ fontSize: 14, color: 'var(--text2)', lineHeight: 1.5, margin: '0 0 12px' }}>
              Print it before the game: one page for Football and Flag Football, one for Basketball.
            </p>
            <a href={`${API_BASE}${downloadPath}`} download style={{
              width: '100%', minHeight: 52, borderRadius: 12, border: '1px solid var(--gold)',
              color: 'var(--gold)', fontSize: 16, fontWeight: 800, textDecoration: 'none',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            }}>
              <Download size={18} /> Download the Halftime Sheet (PDF)
            </a>
          </>
        ) : (
          <p style={{ fontSize: 14, color: 'var(--text2)', margin: 0 }}>Thanks. Please refresh and try again if the download does not appear.</p>
        )}
      </div>
    )
  }

  return (
    <form onSubmit={onSubmit} noValidate style={{ position: 'relative' }}>
      <p style={{ fontSize: 14, color: 'var(--text2)', lineHeight: 1.5, margin: '0 0 14px' }}>
        <FileText size={15} style={{ verticalAlign: '-2px', marginRight: 6, color: 'var(--gold)' }} />
        Prefer pen and paper? Get the printable Halftime Sheet tracker free. Enter your name and email and
        the download link appears right here.
      </p>

      <div style={{ marginBottom: 12 }}>
        <label htmlFor="hs-name" style={label}>Name</label>
        <input id="hs-name" className="input" style={input} value={name} onChange={e => setName(e.target.value)}
          autoComplete="name" maxLength={120} required />
      </div>
      <div style={{ marginBottom: 12 }}>
        <label htmlFor="hs-email" style={label}>Email</label>
        <input id="hs-email" type="email" className="input" style={input} value={email}
          onChange={e => setEmail(e.target.value)} autoComplete="email" inputMode="email" maxLength={254} required />
      </div>
      <div style={{ marginBottom: 12 }}>
        <label htmlFor="hs-phone" style={label}>
          Phone <span style={{ fontWeight: 400, color: 'var(--text3)' }}>(optional)</span>
        </label>
        <input id="hs-phone" type="tel" className="input" style={input} value={phone}
          onChange={e => setPhone(e.target.value)} autoComplete="tel" inputMode="tel" maxLength={32} />
      </div>

      <div aria-hidden="true" style={honeypot}>
        <label htmlFor="hs-website">Website</label>
        <input id="hs-website" name="website" tabIndex={-1} autoComplete="off" value={website}
          onChange={e => setWebsite(e.target.value)} />
      </div>

      <label htmlFor="hs-consent" style={{ display: 'flex', gap: 10, alignItems: 'flex-start', minHeight: 44, cursor: 'pointer', margin: '4px 0 14px' }}>
        <input id="hs-consent" type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)}
          style={{ width: 22, height: 22, flexShrink: 0, marginTop: 1, accentColor: 'var(--gold)' }} />
        <span style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.5 }}>
          I agree that CoachLenz may email me the Halftime Sheet and follow-up about CoachLenz. See the{' '}
          <Link href="/privacy" target="_blank" style={{ color: 'var(--gold)', textDecoration: 'underline' }}>Privacy Policy</Link>.
        </span>
      </label>

      {error && <div role="alert" style={{ background: 'var(--redl)', color: 'var(--red)', borderRadius: 8, padding: '10px 14px', marginBottom: 12, fontSize: 14 }}>{error}</div>}

      <button type="submit" disabled={busy} style={{
        width: '100%', minHeight: 52, borderRadius: 12, cursor: 'pointer', background: 'transparent',
        border: '1px solid var(--border3)', color: 'var(--text)', fontSize: 16, fontWeight: 700,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8, opacity: busy ? 0.7 : 1,
      }}>
        {busy ? <Loader2 size={18} className="animate-spin" /> : <Download size={18} />}
        {busy ? 'Sending…' : 'Get the free printable sheet'}
      </button>
    </form>
  )
}
