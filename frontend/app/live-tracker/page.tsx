'use client'
/**
 * /live-tracker: the $7 one-time Live Tracker offer (Live Game Logger + Halftime Sheet).
 *
 * Copy rules (issue #299 fact lock): Football, Flag Football and Basketball only; $7 USD
 * one time; no "free forever"; no film-breakdown price; no testimonials; no SMS; no
 * claim of offline cold start (plays only queue on the phone once a game is open).
 *
 * Flow: signed out -> signup (or login) -> back here with ?start=1 -> Stripe Checkout
 * (test mode on staging). Stripe returns to ?checkout=success (we wait for the webhook
 * grant, then link to /live) or ?checkout=cancel (nothing charged, nothing granted).
 * Access is only ever granted server-side by the webhook after a PAID session.
 *
 * Secondary offer: the free printable Halftime Sheet PDF, double opt-in. The PDF is
 * emailed only after the coach confirms (see components/live/HalftimePdfForm.tsx).
 */
import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import { rememberNext } from '@/lib/postAuth'
import HalftimePdfForm from '@/components/live/HalftimePdfForm'
import { Zap, FileBarChart, ClipboardList, CheckCircle2, Loader2 } from 'lucide-react'
import logo from '../../public/coachlenz-logo.png'

type View = 'offer' | 'success' | 'cancel'

const POINTS = [
  { icon: ClipboardList, title: 'Chart the game live', body: 'Log each play from the sideline on your phone: play type, result, yards or shots, down and distance, and the players involved.' },
  { icon: FileBarChart, title: 'Halftime Sheet at the break', body: 'One tap builds a Halftime Sheet from the plays you logged in the first half.' },
  { icon: Zap, title: 'Full-game breakdown from the same log', body: 'The same logged game also gives you a whole-game report after the final whistle. No second purchase.' },
]

export default function LiveTrackerPage() {
  const router = useRouter()
  const [view, setView] = useState<View>('offer')
  const [signedIn, setSignedIn] = useState<boolean | null>(null)
  const [hasAccess, setHasAccess] = useState<boolean | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [waitedOut, setWaitedOut] = useState(false)
  const started = useRef(false)

  async function checkAccess(): Promise<boolean | null> {
    try {
      const r = await api.get('/live/access')
      const ok = !!r.data?.has_access
      setHasAccess(ok)
      return ok
    } catch { return null }
  }

  async function startCheckout() {
    setError('')
    if (!localStorage.getItem('access_token')) {
      // Come back here after signup / login and go straight to checkout.
      rememberNext('/live-tracker?start=1')
      router.push('/onboarding')
      return
    }
    setBusy(true)
    try {
      const origin = window.location.origin
      const r = await api.post('/billing/live-tracker/checkout', {
        success_url: `${origin}/live-tracker?checkout=success`,
        cancel_url: `${origin}/live-tracker?checkout=cancel`,
      })
      window.location.href = r.data.checkout_url
    } catch (e: any) {
      const status = e?.response?.status
      if (status === 409) { setHasAccess(true); setBusy(false); return }
      const d = e?.response?.data?.detail
      setError(typeof d === 'string' ? d : 'Checkout could not start. You were not charged. Please try again.')
      setBusy(false)
    }
  }

  useEffect(() => {
    const qs = new URLSearchParams(window.location.search)
    const c = qs.get('checkout')
    const v: View = c === 'success' ? 'success' : c === 'cancel' ? 'cancel' : 'offer'
    setView(v)
    const authed = !!localStorage.getItem('access_token')
    setSignedIn(authed)
    if (!authed) return
    checkAccess().then(ok => {
      // Back from signup / login with the intent to buy: go straight to checkout.
      if (v === 'offer' && qs.get('start') === '1' && ok === false && !started.current) {
        started.current = true
        startCheckout()
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // After a successful checkout, the webhook grants access a moment later. Poll the
  // read-only access endpoint for up to ~40s, then say so honestly.
  useEffect(() => {
    if (view !== 'success' || !signedIn || hasAccess) return
    let n = 0
    const id = setInterval(async () => {
      n += 1
      const ok = await checkAccess()
      if (ok || n >= 20) { clearInterval(id); if (!ok) setWaitedOut(true) }
    }, 2000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, signedIn, hasAccess])

  const cta = (label: string) => (
    <button onClick={startCheckout} disabled={busy} data-testid="live-tracker-cta"
      className="btn-primary w-full" style={{ minHeight: 52, fontSize: 17, fontWeight: 800 }}>
      {busy ? <Loader2 size={18} className="animate-spin" /> : null} {label}
    </button>
  )

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col" style={{ color: 'var(--text)' }}>
      <header className="border-b border-gray-800 px-4 sm:px-8 py-3 flex items-center justify-between">
        <Link href="/live-tracker" style={{ display: 'inline-flex', alignItems: 'center', minHeight: 44 }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={logo.src} alt="CoachLenz" style={{ height: 28, width: 'auto' }} />
        </Link>
        {signedIn === false && (
          <Link href="/login" onClick={() => rememberNext('/live-tracker?start=1')}
            className="text-sm text-gray-400 hover:text-gray-100"
            style={{ display: 'inline-flex', alignItems: 'center', minHeight: 44, padding: '0 8px' }}>Sign in</Link>
        )}
      </header>

      <main className="flex-1 w-full" style={{ maxWidth: 560, margin: '0 auto', padding: '28px 16px 40px' }}>
        {view === 'cancel' && (
          <div className="card" style={{ marginBottom: 20, border: '1px solid var(--border2)' }} data-testid="checkout-canceled">
            <div style={{ fontWeight: 800, marginBottom: 6 }}>Checkout canceled</div>
            <p className="text-sm text-gray-400" style={{ margin: 0 }}>
              You were not charged and nothing changed on your account. You can try again whenever you are ready.
            </p>
          </div>
        )}

        {view === 'success' && (
          <div className="card" style={{ marginBottom: 20, border: '1px solid var(--gold)' }} data-testid="checkout-success">
            {hasAccess ? (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 800, fontSize: 18, marginBottom: 8, color: 'var(--gold)' }}>
                  <CheckCircle2 size={20} /> You are in
                </div>
                <p className="text-sm text-gray-400" style={{ marginTop: 0 }}>The Live Tracker is unlocked for your account.</p>
                <Link href="/live" className="btn-primary w-full" style={{ minHeight: 52, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800 }}>
                  Open the Live Tracker
                </Link>
              </>
            ) : (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 800, marginBottom: 6 }}>
                  {!waitedOut && <Loader2 size={16} className="animate-spin" />} Confirming your payment
                </div>
                <p className="text-sm text-gray-400" style={{ margin: 0 }}>
                  {waitedOut
                    ? 'Your payment has not been confirmed yet. Refresh this page in a minute. If it still does not unlock, contact support and we will sort it out.'
                    : 'This usually takes a few seconds. Access unlocks once Stripe confirms the payment.'}
                </p>
              </>
            )}
          </div>
        )}

        <p className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--gold)', marginBottom: 10 }}>
          CoachLenz Live Tracker
        </p>
        <h1 className="text-3xl sm:text-4xl font-bold" style={{ lineHeight: 1.15, marginBottom: 14 }}>
          Chart the game live. Get the Halftime Sheet at the break.
        </h1>
        <p className="text-gray-400" style={{ fontSize: 16, marginBottom: 20 }}>
          Track stats from the sideline on your phone, then tap once for a Halftime Sheet built from what
          actually happened in the first half. For Football, Flag Football, and Basketball.
        </p>

        <div className="card" style={{ marginBottom: 22 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 14 }}>
            <span style={{ fontSize: 36, fontWeight: 800 }}>$7</span>
            <span className="text-gray-400 text-sm">USD, one time</span>
          </div>
          {hasAccess && view !== 'success' ? (
            <>
              <p className="text-sm text-gray-400" style={{ marginTop: 0 }}>The Live Tracker is already unlocked for your account.</p>
              <Link href="/live" className="btn-primary w-full" style={{ minHeight: 52, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800 }}>
                Open the Live Tracker
              </Link>
            </>
          ) : view !== 'success' ? (
            <>
              {cta(view === 'cancel' ? 'Try again: $7 one time' : 'Get the Live Tracker for $7')}
              {error && <div className="text-red-400 text-sm bg-red-400/10 rounded p-3" style={{ marginTop: 12 }}>{error}</div>}
              <p className="text-xs text-gray-500" style={{ marginTop: 10, marginBottom: 0, textAlign: 'center' }}>
                {signedIn === false ? 'Create your account (or sign in), then checkout. ' : ''}Secure checkout by Stripe.
              </p>
            </>
          ) : null}
        </div>

        <div style={{ display: 'grid', gap: 12, marginBottom: 22 }}>
          {POINTS.map(({ icon: Icon, title, body }) => (
            <div key={title} className="card" style={{ display: 'flex', gap: 12 }}>
              <Icon size={20} style={{ color: 'var(--gold)', flexShrink: 0, marginTop: 2 }} />
              <div>
                <div style={{ fontWeight: 700, marginBottom: 4 }}>{title}</div>
                <div className="text-sm text-gray-400">{body}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="card" style={{ marginBottom: 22 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>Built for the sideline</div>
          <ul className="text-sm text-gray-400" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
            <li>Football, Flag Football, and Basketball.</li>
            <li>Big tap targets for one-handed logging.</li>
            <li>Each play saves as you log it. If the signal drops once a game is open, plays wait on your phone and sync when the connection returns.</li>
            <li>Your games and reports stay in your CoachLenz account.</li>
          </ul>
        </div>

        <div id="halftime-pdf" className="card" style={{ marginBottom: 22 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>Free printable Halftime Sheet (PDF)</div>
          <HalftimePdfForm />
        </div>
      </main>

      <footer className="text-center text-xs text-gray-600" style={{ padding: '0 16px 24px' }}>
        Powered by <a href="https://cosbyaisolutions.com" className="text-brand-500 hover:underline" target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
      </footer>
    </div>
  )
}
