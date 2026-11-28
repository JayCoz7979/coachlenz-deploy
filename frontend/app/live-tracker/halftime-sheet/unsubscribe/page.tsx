'use client'
/**
 * /live-tracker/halftime-sheet/unsubscribe?token=...
 *
 * One-click unsubscribe from the Halftime Sheet PDF emails (the footer link in every
 * lead email). Opening the page sends the signed token to the API, which marks the
 * lead unsubscribed. Mail apps that support one-click use the List-Unsubscribe header
 * instead and never open this page. Idempotent: a second visit says the same thing.
 */
import { useEffect, useState, type CSSProperties } from 'react'
import Link from 'next/link'
import { publicApi } from '@/lib/api'
import logo from '../../../../public/coachlenz-logo.png'

const card: CSSProperties = { background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: 18, marginTop: 18 }
const link: CSSProperties = { display: 'inline-flex', alignItems: 'center', minHeight: 44, color: 'var(--gold)', fontWeight: 700 }

type View = 'working' | 'done' | 'invalid' | 'error' | 'missing'

export default function HalftimeSheetUnsubscribePage() {
  const [view, setView] = useState<View>('working')
  const [message, setMessage] = useState('')

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token') || ''
    if (!token) { setView('missing'); return }
    let cancelled = false
    publicApi.post('/leads/halftime-sheet/unsubscribe', { token })
      .then((r) => { if (!cancelled) { setMessage(r.data?.message || ''); setView('done') } })
      .catch((e) => {
        if (cancelled) return
        const d = e?.response?.data?.detail
        if (e?.response?.status === 400) { setMessage(d?.message || ''); setView('invalid') }
        else setView('error')
      })
    return () => { cancelled = true }
  }, [])

  return (
    <main style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)', padding: '24px 16px' }}>
      <div style={{ maxWidth: 480, margin: '0 auto' }}>
        <Link href="/live-tracker" style={{ display: 'inline-flex', minHeight: 44, alignItems: 'center' }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={logo.src} alt="CoachLenz" style={{ height: 28, width: 'auto' }} />
        </Link>
        <div style={card}>
          {view === 'working' && <><h1 style={{ fontSize: 22, fontWeight: 800 }}>One moment</h1><p>Updating your email preferences.</p></>}
          {view === 'done' && (
            <>
              <h1 style={{ fontSize: 22, fontWeight: 800 }}>You are unsubscribed</h1>
              <p>{message || 'CoachLenz will not send you more Halftime Sheet emails.'}</p>
            </>
          )}
          {view === 'invalid' && (
            <>
              <h1 style={{ fontSize: 22, fontWeight: 800 }}>This link is not valid</h1>
              <p>{message || 'Open the unsubscribe link straight from the email.'}</p>
            </>
          )}
          {view === 'missing' && (
            <>
              <h1 style={{ fontSize: 22, fontWeight: 800 }}>Link incomplete</h1>
              <p>This unsubscribe link is missing its code. Open it straight from the email.</p>
            </>
          )}
          {view === 'error' && (
            <>
              <h1 style={{ fontSize: 22, fontWeight: 800 }}>Something went wrong</h1>
              <p>We could not update your preferences just now. Please reload this page to try again.</p>
            </>
          )}
          <p style={{ marginTop: 12 }}><Link href="/live-tracker" style={link}>Back to CoachLenz</Link></p>
        </div>
        <p style={{ marginTop: 18, fontSize: 12, opacity: 0.7, textAlign: 'center' }}>
          Powered by <a href="https://cosbyaisolutions.com" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--gold)' }}>Cosby AI Solutions</a>
        </p>
      </div>
    </main>
  )
}
