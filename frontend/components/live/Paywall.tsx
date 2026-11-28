'use client'
/**
 * $7 Live Tracker paywall card. Shown on /live and /live/[id] when the server says
 * this org has not unlocked the Live Tracker. The server enforces the gate on every
 * /live write route; this card only explains it and links to checkout. Past games and
 * reports stay viewable.
 */
import Link from 'next/link'
import { Lock } from 'lucide-react'

export default function LiveTrackerPaywall({ message }: { message?: string }) {
  return (
    <div data-testid="live-paywall" style={{
      background: 'var(--bg2)', border: '1px solid var(--gold)', borderRadius: 12, padding: 16, marginBottom: 14,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 800, color: 'var(--gold)', marginBottom: 8 }}>
        <Lock size={16} /> Unlock the Live Tracker ($7 one time)
      </div>
      <p style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.5, margin: '0 0 14px' }}>
        {message || 'The Live Tracker is a $7 one-time unlock. Unlock it to chart games live and get the Halftime Sheet. Your past games and reports stay viewable.'}
      </p>
      <Link href="/live-tracker" style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 48, borderRadius: 10,
        background: 'var(--gold)', color: '#1c1c1c', fontWeight: 800, fontSize: 15, textDecoration: 'none',
      }}>Unlock for $7</Link>
    </div>
  )
}
