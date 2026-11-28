'use client'
/**
 * $7 Live Tracker offer: the Live Game Logger plus the Halftime Sheet.
 * Public, mobile-first, one primary CTA. Uses the existing CoachLenz tokens only.
 *
 * Copy is fact-locked: Football, Flag Football, and Basketball; $7 USD, one time;
 * chart the game live, get the Halftime Sheet at the break; the full-game breakdown
 * comes from the same logged game. No other prices, claims, or testimonials.
 *
 * Flow: signed out -> /login?next=/live-tracker?buy=1 (or signup, which carries next)
 * -> back here -> Stripe Checkout (test mode on staging). Access is granted by the
 * Stripe webhook after a PAID session, never by this page or the success redirect.
 */
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Zap, Timer, ClipboardList, Loader2, CheckCircle2 } from 'lucide-react'
import logo from '../../public/coachlenz-logo.png'
import {
  LIVE_TRACKER_BUY_PATH, isSignedIn, getLiveAccess, startLiveTrackerCheckout, checkoutErrorMessage,
} from '@/lib/liveTracker'

const page: CSSProperties = { minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)', display: 'flex', flexDirection: 'column' }
const wrap: CSSProperties = { width: '100%', maxWidth: 560, margin: '0 auto', padding: '0 18px' }
const card: CSSProperties = { background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: 16, marginBottom: 12 }
const muted: CSSProperties = { color: 'var(--text3)', fontSize: 14, lineHeight: 1.55 }
const cta: CSSProperties = {
  width: '100%', minHeight: 56, borderRadius: 12, border: 'none', cursor: 'pointer',
  background: 'var(--gold)', color: '#1c1c1c', fontSize: 18, fontWeight: 800,
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 10, textDecoration: 'none',
}

const STEPS: { icon: typeof Zap; title: string; body: string }[] = [
  { icon: Zap, title: 'Start a game', body: 'Pick Football, Flag Football, or Basketball and enter the matchup.' },
  { icon: ClipboardList, title: 'Chart it live', body: 'Tap each play from the sideline as it happens. Big buttons, built for your phone.' },
  { icon: Timer, title: 'Get the Halftime Sheet at the break', body: 'Tap Halftime Sheet for a report built from the first-half plays you logged.' },
]

const ANSWERS: { q: string; a: string }[] = [
  { q: 'What does it cost?', a: '$7 USD, one time. One payment unlocks the Live Tracker on your CoachLenz account. It is not a subscription.' },
  { q: 'Which sports?', a: 'Football, Flag Football, and Basketball.' },
  { q: 'What about after the game?', a: 'The full-game breakdown comes from the same game you logged. No second price.' },
  { q: 'Do I need an account?', a: 'Yes. Sign in or create your CoachLenz account, and you go straight to checkout.' },
  { q: 'What if I change my mind at checkout?', a: 'Cancel and you are not charged. Nothing changes on your account, and you can come back any time.' },
]

type State = 'idle' | 'checking' | 'redirecting' | 'owned'

export default function LiveTrackerOfferPage() {
  const router = useRouter()
  const [state, setState] = useState<State>('idle')
  const [error, setError] = useState('')
  const [cancelled, setCancelled] = useState(false)
  // Read after mount (localStorage is browser-only) so server and client render match.
  const [signedIn, setSignedIn] = useState(false)
  const autoStarted = useRef(false)

  async function buy() {
    setError('')
    if (!isSignedIn()) {
      router.push(`/login?next=${encodeURIComponent(LIVE_TRACKER_BUY_PATH)}`)
      return
    }
    setState('redirecting')
    try {
      await startLiveTrackerCheckout()
    } catch (e: any) {
      if (e?.response?.status === 409) { setState('owned'); return }
      setError(checkoutErrorMessage(e))
      setState('idle')
    }
  }

  useEffect(() => {
    const qs = new URLSearchParams(window.location.search)
    if (qs.get('checkout') === 'cancelled') setCancelled(true)
    const wantsBuy = qs.get('buy') === '1'
    // Drop ?buy=1 so the browser Back button from Stripe can't bounce the coach
    // straight into checkout again.
    if (wantsBuy) window.history.replaceState(null, '', window.location.pathname)
    if (!isSignedIn()) return
    setSignedIn(true)
    setState('checking')
    getLiveAccess().then(a => {
      if (a.has_access) { setState('owned'); return }
      setState('idle')
      // Back from login/signup with the intent to buy: continue to checkout.
      if (wantsBuy && !autoStarted.current) { autoStarted.current = true; buy() }
    }).catch(() => setState('idle'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div style={page}>
      <header style={{ borderBottom: '1px solid var(--border2)' }}>
        <div style={{ ...wrap, display: 'flex', alignItems: 'center', justifyContent: 'space-between', minHeight: 60 }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={logo.src} alt="CoachLenz" style={{ height: 28, width: 'auto' }} />
          {!signedIn && (
            <Link href={`/login?next=${encodeURIComponent('/live-tracker')}`} style={{ color: 'var(--text3)', fontSize: 14, minHeight: 44, display: 'inline-flex', alignItems: 'center', padding: '0 4px' }}>
              Sign in
            </Link>
          )}
        </div>
      </header>

      <main style={{ flex: 1, paddingTop: 28, paddingBottom: 32 }}>
        <div style={wrap}>
          {cancelled && (
            <div role="status" style={{ ...card, borderColor: 'var(--border2)' }}>
              <div style={{ fontWeight: 800, marginBottom: 4 }}>Checkout cancelled</div>
              <div style={muted}>You were not charged and nothing changed on your account. Whenever you are ready, you can try again below.</div>
            </div>
          )}

          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: 'var(--gold)', fontWeight: 800, fontSize: 13, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 10 }}>
            <Zap size={16} /> Live Tracker
          </div>
          <h1 style={{ fontSize: 30, lineHeight: 1.15, fontWeight: 800, margin: '0 0 12px' }}>
            Chart the game live. Get the Halftime Sheet at the break.
          </h1>
          <p style={{ ...muted, fontSize: 16, color: 'var(--text2)', marginBottom: 20 }}>
            Track your team&apos;s plays from the sideline on your phone. When the half ends, tap Halftime Sheet
            and take a report built from your first-half plays into the locker room.
            For Football, Flag Football, and Basketball.
          </p>

          <div style={{ ...card, border: '1px solid var(--gold)', padding: 18 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
              <span style={{ fontSize: 38, fontWeight: 800 }}>$7</span>
              <span style={{ color: 'var(--text2)', fontWeight: 700 }}>USD, one time</span>
            </div>
            <div style={{ ...muted, marginBottom: 14 }}>Live Game Logger + Halftime Sheet. The full-game breakdown from the same game is included.</div>

            {state === 'owned' ? (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--green3)', fontWeight: 800, marginBottom: 12 }}>
                  <CheckCircle2 size={18} /> You already have the Live Tracker.
                </div>
                <Link href="/live" style={cta}>Open the Live Tracker</Link>
              </>
            ) : (
              <button data-cta="live-tracker-buy" onClick={buy} disabled={state === 'redirecting' || state === 'checking'} style={{ ...cta, opacity: state === 'redirecting' || state === 'checking' ? 0.7 : 1 }}>
                {state === 'redirecting' || state === 'checking' ? <Loader2 size={20} className="animate-spin" /> : <Zap size={20} />}
                {state === 'redirecting' ? 'Taking you to secure checkout…' : 'Unlock the Live Tracker for $7'}
              </button>
            )}
            {error && <div role="alert" style={{ marginTop: 12, background: 'var(--redl)', color: 'var(--red)', borderRadius: 8, padding: '10px 12px', fontSize: 14 }}>{error}</div>}
            <div style={{ ...muted, fontSize: 12.5, marginTop: 10, textAlign: 'center' }}>
              Secure checkout by Stripe. Sign in or create an account first.
            </div>
          </div>

          <h2 style={{ fontSize: 18, fontWeight: 800, margin: '26px 0 12px' }}>How it works</h2>
          {STEPS.map((s, i) => (
            <div key={s.title} style={{ ...card, display: 'flex', gap: 12, alignItems: 'flex-start' }}>
              <div style={{ flex: '0 0 36px', height: 36, borderRadius: 10, background: 'rgba(201,168,76,0.16)', color: 'var(--gold)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <s.icon size={18} />
              </div>
              <div>
                <div style={{ fontWeight: 800, marginBottom: 2 }}>{i + 1}. {s.title}</div>
                <div style={muted}>{s.body}</div>
              </div>
            </div>
          ))}

          <h2 style={{ fontSize: 18, fontWeight: 800, margin: '26px 0 12px' }}>Straight answers</h2>
          {ANSWERS.map(a => (
            <div key={a.q} style={card}>
              <div style={{ fontWeight: 700, marginBottom: 4 }}>{a.q}</div>
              <div style={muted}>{a.a}</div>
            </div>
          ))}
        </div>
      </main>

      <footer style={{ borderTop: '1px solid var(--border2)', padding: '16px 18px', textAlign: 'center', fontSize: 13, color: 'var(--text3)' }}>
        Powered by <a href="https://cosbyaisolutions.com" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--gold)' }}>Cosby AI Solutions</a>
      </footer>
    </div>
  )
}
