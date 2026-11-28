'use client'
/**
 * Stripe success return for the $7 Live Tracker. This page grants NOTHING: it asks
 * the server (GET /live/access) whether the webhook has recorded the paid session,
 * polling briefly because the webhook can land a few seconds after the redirect.
 */
import { useEffect, useState, type CSSProperties } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { CheckCircle2, Loader2 } from 'lucide-react'
import logo from '../../../public/coachlenz-logo.png'
import { getLiveAccess, isSignedIn } from '@/lib/liveTracker'

const page: CSSProperties = { minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '24px 18px' }
const card: CSSProperties = { width: '100%', maxWidth: 460, background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: 20, textAlign: 'center' }
const cta: CSSProperties = {
  width: '100%', minHeight: 56, borderRadius: 12, background: 'var(--gold)', color: '#1c1c1c', fontSize: 17, fontWeight: 800,
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', textDecoration: 'none', marginTop: 16,
}

const POLL_MS = 2000
const MAX_TRIES = 15   // ~30 seconds

type State = 'checking' | 'ready' | 'pending'

export default function LiveTrackerSuccessPage() {
  const router = useRouter()
  const [state, setState] = useState<State>('checking')

  useEffect(() => {
    if (!isSignedIn()) { router.replace(`/login?next=${encodeURIComponent('/live-tracker/success')}`); return }
    let tries = 0
    let stop = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const check = async () => {
      tries += 1
      try {
        const a = await getLiveAccess()
        if (stop) return
        if (a.has_access) { setState('ready'); return }
      } catch { /* keep polling; a blip is not a failure */ }
      if (stop) return
      if (tries >= MAX_TRIES) { setState('pending'); return }
      timer = setTimeout(check, POLL_MS)
    }
    check()
    return () => { stop = true; if (timer) clearTimeout(timer) }
  }, [router])

  return (
    <div style={page}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={logo.src} alt="CoachLenz" style={{ height: 30, width: 'auto', marginBottom: 20 }} />
      <div style={card}>
        {state === 'ready' ? (
          <>
            <CheckCircle2 size={40} style={{ color: 'var(--green3)', margin: '0 auto 10px' }} />
            <h1 style={{ fontSize: 24, fontWeight: 800, margin: '0 0 6px' }}>You&apos;re in.</h1>
            <p style={{ color: 'var(--text2)', margin: 0 }}>The Live Tracker is unlocked on your account. Start a game and chart it live.</p>
            <Link href="/live" style={cta}>Open the Live Tracker</Link>
          </>
        ) : state === 'checking' ? (
          <>
            <Loader2 size={36} className="animate-spin" style={{ color: 'var(--gold)', margin: '0 auto 10px' }} />
            <h1 style={{ fontSize: 20, fontWeight: 800, margin: '0 0 6px' }}>Confirming your payment…</h1>
            <p style={{ color: 'var(--text3)', margin: 0 }}>This usually takes a few seconds.</p>
          </>
        ) : (
          <>
            <h1 style={{ fontSize: 20, fontWeight: 800, margin: '0 0 6px' }}>Still confirming with Stripe</h1>
            <p style={{ color: 'var(--text2)', margin: 0 }}>
              We haven&apos;t received the payment confirmation yet. Your access turns on as soon as it arrives.
              Refresh this page in a minute, or open the Live Tracker then.
            </p>
            <button onClick={() => window.location.reload()} style={{ ...cta, border: 'none', cursor: 'pointer' }}>Check again</button>
            <Link href="/live-tracker" style={{ display: 'inline-flex', alignItems: 'center', minHeight: 44, marginTop: 8, color: 'var(--text3)', fontSize: 14 }}>Back to the Live Tracker page</Link>
          </>
        )}
      </div>
      <p style={{ marginTop: 18, fontSize: 13, color: 'var(--text3)' }}>
        Powered by <a href="https://cosbyaisolutions.com" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--gold)' }}>Cosby AI Solutions</a>
      </p>
    </div>
  )
}
