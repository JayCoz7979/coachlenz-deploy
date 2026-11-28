// Free printable Halftime Sheet PDF: pure helpers for the double opt-in form + the
// confirm page. Kept free of React so `npm test` can cover them.
//
// The PDF is never shown or downloaded in the browser. It is emailed, as an
// attachment, only after the coach confirms their email. No SMS anywhere; the
// optional phone number is never texted.

export const CONSENT_LINE =
  'Email me the free Halftime Sheet PDF and follow-up emails from CoachLenz. I can unsubscribe at any time. Phone is optional and is never texted.'

export type LeadForm = { name: string; email: string; phone: string; consent: boolean; company: string }

// Light client-side check for instant feedback. The server is the real validator
// (format + MX/domain + disposable block).
export function clientLeadError(f: LeadForm): string {
  if (!f.name.trim()) return 'Please enter your name.'
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email.trim())) return 'Please enter a valid email address.'
  if (!f.consent) return 'Please tick the box so we can email you the PDF.'
  return ''
}

export function leadPayload(f: LeadForm) {
  return {
    name: f.name.trim(),
    email: f.email.trim(),
    phone: f.phone.trim() || null,
    consent: f.consent,
    company: f.company, // honeypot, empty for people
  }
}

export type ConfirmView =
  | { kind: 'confirmed'; message: string }
  | { kind: 'expired' | 'used' | 'invalid' | 'pdf_failed' | 'error'; message: string; canResendWithToken: boolean }

// Map a POST /leads/halftime-sheet/confirm failure to what the page shows.
export function confirmErrorView(status: number | undefined, detail: any): ConfirmView {
  const code = detail?.code
  const message = typeof detail?.message === 'string' ? detail.message : 'Something went wrong. Please try again.'
  if (code === 'token_expired') return { kind: 'expired', message, canResendWithToken: true }
  if (code === 'token_used') return { kind: 'used', message, canResendWithToken: true }
  if (code === 'pdf_send_failed') return { kind: 'pdf_failed', message, canResendWithToken: true }
  if (code === 'token_invalid') return { kind: 'invalid', message, canResendWithToken: false }
  if (status === 429) return { kind: 'error', message: 'Too many tries. Please wait a minute and try again.', canResendWithToken: true }
  return { kind: 'error', message, canResendWithToken: true }
}

export function detailMessage(e: any, fallback: string): string {
  if (e?.response?.status === 429) return 'Too many tries. Please wait a minute and try again.'
  const d = e?.response?.data?.detail
  if (typeof d === 'string') return d
  if (d && typeof d.message === 'string') return d.message
  return fallback
}
