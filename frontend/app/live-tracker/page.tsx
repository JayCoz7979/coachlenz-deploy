'use client'
/**
 * /live-tracker: the $7 one-time Live Tracker offer (Live Game Logger + Halftime Sheet).
 *
 * Fact lock: Football, Flag Football, and Basketball. $7 USD, one time. Chart the game
 * live, get the Halftime Sheet at the break. The full-game breakdown from the same logged
 * game is included. No other prices, no testimonials, no offline claims.
 *
 * Flow: signed-in coach -> POST /billing/live-tracker/checkout -> Stripe Checkout (test
 * mode on staging). Signed-out coach -> login / signup -> back here with ?checkout=1,
 * which starts checkout automatically. Stripe returns to /live-tracker/success (access is
 * granted by the signed webhook, never by the redirect) or to ?checkout=cancelled.
 *
 * Secondary offer: the free printable Halftime Sheet PDF, double opt-in. The PDF is
 * emailed only after the coach confirms (see components/live/HalftimePdfForm.tsx).
 */
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'
import { rememberNext } from '@/lib/postAuth'
import HalftimePdfForm from '@/components/live/HalftimePdfForm'
import { Loader2, Zap, ClipboardList, Timer, Check } from 'lucide-react'
// Static import so the transparent lockup is emitted to /_next/static/media
// (public/ is not bundled with output:'standalone').
import logo from '../../public/coachlenz-logo.png'

const CHECKOUT_RETURN = '/live-tracker?checkout=1'

const wrap: CSSProperties = { maxWidth: 560, margin: '0 auto', padding: '20px 18px 48px' }
const card: CSSProperties = { background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: 18, marginBottom: 14 }
const h2: CSSProperties = { fontSize: 13, fontWeight: 800, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 12px' }
const cta: CSSProperties = {
  width: '100%', minHeight: 56, borderRadius: 12, border: 'none', cursor: 'pointer',
  background: 'var(--gold)', color: '#1c1c1c', fontSize: 17, fontWeight: 800,
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
}

type State = 'loading' | 'signed_out' | 'unpaid' | 'paid'

export default function LiveTrackerPage() {
  const router = useRouter()
  const [state, setState] = useState<State>('loading')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [cancelled, setCancelled] = useState(false)
  const autoStarted = useRef(false)

  async function startCheckout() {
    setBusy(true); setError('')
    try {
      const r = await api.post('/billing/live-tracker/checkout', { origin: window.location.origin })
      window.location.href = r.data.checkout_url
    } catch (e: any) {
      const status = e?.response?.status
      if (status === 409) { router.push('/live'); return }
      if (status === 401) { setState('signed_out'); setBusy(false); return }
      const d = e?.response?.data?.detail
      setError(typeof d === 'string' ? d : 'Could not open checkout. Please try again.')
      setBusy(false)
    }
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const wantsCheckout = params.get('checkout') === '1'
    setCancelled(params.get('checkout') === 'cancelled')
    if (!localStorage.getItem('access_token')) { setState('signed_out'); return }
    api.get('/billing/live-tracker/status').then(r => {
      const paid = !!r.data?.live_tracker
      setState(paid ? 'paid' : 'unpaid')
      // Back from login / signup (or the in-app paywall): go straight to checkout.
      if (wantsCheckout && !paid && !autoStarted.current) {
        autoStarted.current = true
        startCheckout()
      }
    }).catch(() => setState('signed_out'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function onPrimary() {
    if (state === 'paid') { router.push('/live'); return }
    if (state === 'signed_out') {
      rememberNext(CHECKOUT_RETURN)
      router.push(`/login?next=${encodeURIComponent(CHECKOUT_RETURN)}`)
      return
    }
    startCheckout()
  }

  const ctaLabel = state === 'paid' ? 'Open the Live Game Logger' : 'Get the Live Tracker for $7'

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}>
      <header style={{ borderBottom: '1px solid var(--border2)' }}>
        <div style={{ maxWidth: 560, margin: '0 auto', padding: '12px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={logo.src} alt="CoachLenz" style={{ height: 28, width: 'auto' }} />
          {state === 'signed_out' && (
            <Link href={`/login?next=${encodeURIComponent('/live-tracker')}`} style={{
              display: 'inline-flex', alignItems: 'center', minHeight: 44, padding: '0 6px', fontSize: 14, color: 'var(--text3)',
            }}>Sign in</Link>
          )}
        </div>
      </header>

      <main style={wrap}>
        {cancelled && (
          <div role="status" style={{ ...card, border: '1px solid var(--border3)' }}>
            <b style={{ display: 'block', marginBottom: 6 }}>Checkout cancelled</b>
            <span style={{ fontSize: 14, color: 'var(--text2)', lineHeight: 1.5 }}>
              You were not charged and nothing changed on your account. You can try again whenever you are ready.
            </span>
          </div>
        )}

        <section style={{ textAlign: 'center', padding: '18px 0 8px' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 800, letterSpacing: '0.08em', color: 'var(--gold)', textTransform: 'uppercase', marginBottom: 10 }}>
            <Zap size={14} /> Live Tracker
          </div>
          <h1 style={{ fontSize: 30, lineHeight: 1.15, fontWeight: 800, margin: '0 0 12px' }}>
            Chart the game live. Get the Halftime Sheet at the break.
          </h1>
          <p style={{ fontSize: 16, color: 'var(--text2)', lineHeight: 1.5, margin: '0 0 18px' }}>
            Track your stats from the sideline, one tap per play. When the half ends, your Halftime Sheet is ready.
          </p>
          <div style={{ fontSize: 15, color: 'var(--text2)', marginBottom: 6 }}>Football · Flag Football · Basketball</div>
          <div style={{ margin: '14px 0 18px' }}>
            <span style={{ fontSize: 44, fontWeight: 800 }}>$7</span>
            <span style={{ fontSize: 15, color: 'var(--text3)', marginLeft: 8 }}>USD, one time</span>
          </div>

          {error && <div role="alert" style={{ background: 'var(--redl)', color: 'var(--red)', borderRadius: 8, padding: '10px 14px', marginBottom: 12, fontSize: 14 }}>{error}</div>}

          <button onClick={onPrimary} disabled={busy || state === 'loading'} style={{ ...cta, opacity: (busy || state === 'loading') ? 0.7 : 1 }}>
            {(busy || state === 'loading') ? <Loader2 size={18} className="animate-spin" /> : <Zap size={18} />}
            {busy ? 'Opening checkout…' : ctaLabel}
          </button>
          {state === 'signed_out' && (
            <p style={{ fontSize: 13, color: 'var(--text3)', margin: '10px 0 0' }}>
              You will sign in first, then go straight to checkout.{' '}
              <Link href={`/onboarding?next=${encodeURIComponent(CHECKOUT_RETURN)}`}
                onClick={() => rememberNext(CHECKOUT_RETURN)}
                style={{ color: 'var(--gold)', display: 'inline-flex', alignItems: 'center', minHeight: 44 }}>
                New to CoachLenz? Create an account
              </Link>
            </p>
          )}
          {state === 'paid' && (
            <p style={{ fontSize: 13, color: 'var(--green3)', margin: '10px 0 0' }}>You already have the Live Tracker.</p>
          )}
        </section>

        <section style={{ ...card, marginTop: 18 }}>
          <h2 style={h2}>What you get for $7</h2>
          {[
            'The Live Game Logger for Football, Flag Football, and Basketball',
            'A Halftime Sheet built from the plays you logged in the first half',
            'The full-game breakdown from the same logged game',
            'Your games and reports saved to your CoachLenz account',
          ].map(t => (
            <div key={t} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 10, fontSize: 15, lineHeight: 1.45 }}>
              <Check size={18} style={{ color: 'var(--green3)', flexShrink: 0, marginTop: 2 }} /> <span>{t}</span>
            </div>
          ))}
        </section>

        <section style={card}>
          <h2 style={h2}>How it works</h2>
          {[
            { icon: <Zap size={18} />, t: 'Start a game', d: 'Pick your sport and enter the matchup.' },
            { icon: <ClipboardList size={18} />, t: 'Log each play', d: 'Big tap buttons built for a phone on the sideline.' },
            { icon: <Timer size={18} />, t: 'Tap Halftime Sheet', d: 'Get your first-half breakdown at the break.' },
          ].map((s, i) => (
            <div key={s.t} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', marginBottom: i < 2 ? 14 : 0 }}>
              <span style={{ color: 'var(--gold)', marginTop: 2 }}>{s.icon}</span>
              <span><b style={{ display: 'block', fontSize: 15 }}>{i + 1}. {s.t}</b><span style={{ fontSize: 14, color: 'var(--text3)' }}>{s.d}</span></span>
            </div>
          ))}
        </section>

        <section id="halftime-pdf" style={card}>
          <h2 style={h2}>Free printable Halftime Sheet (PDF)</h2>
          <HalftimePdfForm />
        </section>

        <section style={card}>
          <h2 style={h2}>Already have a CoachLenz account?</h2>
          <p style={{ fontSize: 14, color: 'var(--text2)', lineHeight: 1.5, margin: 0 }}>
            The Live Tracker is a $7 one-time unlock for every account, including existing ones.
            Games and reports you already made stay viewable.
          </p>
        </section>

        <p style={{ textAlign: 'center', fontSize: 12, color: 'var(--text3)', marginTop: 24 }}>
          Powered by <a href="https://cosbyaisolutions.com" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--gold)' }}>Cosby AI Solutions</a>
        </p>
      </main>
    </div>
  )
}
