'use client'
/**
 * Stripe success return for the $7 Live Tracker. This page grants NOTHING: access is
 * recorded only by the signed Stripe webhook after a paid checkout. We poll the
 * status until the webhook lands, then send the coach into the logger.
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'
import { Loader2, CheckCircle2 } from 'lucide-react'
import logo from '../../../public/coachlenz-logo.png'

const POLL_MS = 2000
const MAX_TRIES = 20   // ~40s, then show the "still processing" note (keeps polling)

export default function LiveTrackerSuccessPage() {
  const router = useRouter()
  const [paid, setPaid] = useState(false)
  const [tries, setTries] = useState(0)
  const [signedOut, setSignedOut] = useState(false)

  useEffect(() => {
    if (!localStorage.getItem('access_token')) { setSignedOut(true); return }
    let stop = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const check = async () => {
      try {
        const r = await api.get('/billing/live-tracker/status')
        if (r.data?.live_tracker) {
          setPaid(true)
          timer = setTimeout(() => router.push('/live'), 1500)
          return
        }
      } catch { /* keep polling */ }
      if (stop) return
      setTries(t => t + 1)
      timer = setTimeout(check, POLL_MS)
    }
    check()
    return () => { stop = true; if (timer) clearTimeout(timer) }
  }, [router])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 18 }}>
      <div style={{ maxWidth: 440, width: '100%', textAlign: 'center' }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={logo.src} alt="CoachLenz" style={{ height: 30, width: 'auto', margin: '0 auto 24px', display: 'block' }} />
        <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: 22 }}>
          {signedOut ? (
            <>
              <b style={{ fontSize: 18, display: 'block', marginBottom: 8 }}>Sign in to finish</b>
              <p style={{ fontSize: 14, color: 'var(--text2)', margin: '0 0 16px' }}>Sign in to the account you bought with to open the logger.</p>
              <Link href={`/login?next=${encodeURIComponent('/live-tracker/success')}`} style={btn}>Sign in</Link>
            </>
          ) : paid ? (
            <>
              <CheckCircle2 size={40} style={{ color: 'var(--green3)', margin: '0 auto 10px', display: 'block' }} />
              <b style={{ fontSize: 20, display: 'block', marginBottom: 8 }}>You are in</b>
              <p style={{ fontSize: 14, color: 'var(--text2)', margin: '0 0 16px' }}>Your Live Tracker is unlocked. Opening the Live Game Logger…</p>
              <Link href="/live" style={btn}>Open the Live Game Logger</Link>
            </>
          ) : (
            <>
              <Loader2 size={32} className="animate-spin" style={{ color: 'var(--gold)', margin: '0 auto 12px', display: 'block' }} />
              <b style={{ fontSize: 18, display: 'block', marginBottom: 8 }}>Confirming your payment</b>
              <p style={{ fontSize: 14, color: 'var(--text2)', margin: 0 }}>
                {tries < MAX_TRIES
                  ? 'This usually takes a few seconds.'
                  : 'Still waiting on confirmation from the payment processor. Leave this page open; it will update. Access is only unlocked once the payment is confirmed.'}
              </p>
            </>
          )}
        </div>
        <p style={{ fontSize: 12, color: 'var(--text3)', marginTop: 20 }}>
          Powered by <a href="https://cosbyaisolutions.com" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--gold)' }}>Cosby AI Solutions</a>
        </p>
      </div>
    </div>
  )
}

const btn: React.CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 52, borderRadius: 10,
  background: 'var(--gold)', color: '#1c1c1c', fontWeight: 800, fontSize: 16, textDecoration: 'none',
}
