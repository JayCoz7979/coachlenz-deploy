'use client'
/**
 * $7 Live Tracker paywall, shown on /live and /live/[id] when the server reports the
 * org has not bought it (access.live_tracker === false, or a 402 from a /live route).
 * Everyone pays $7, including existing accounts. Past games stay viewable read-only.
 * The real gate is server-side (backend/services/live_tracker.py); this is the UI.
 */
import Link from 'next/link'
import { Lock } from 'lucide-react'

export const DEFAULT_PAYWALL_MESSAGE =
  'The Live Game Logger and Halftime Sheet are a $7 one-time purchase. ' +
  'Unlock it to start or keep logging games. Your past games and reports stay viewable.'

/** True when an axios error is the server's Live Tracker paywall (402). */
export function isPaywallError(e: any): boolean {
  return e?.response?.status === 402
}

/** Server-provided paywall message from an access payload or a 402 detail. */
export function paywallMessage(src: any): string {
  const m = src?.message ?? src?.response?.data?.detail?.message
  return typeof m === 'string' && m.trim() ? m : DEFAULT_PAYWALL_MESSAGE
}

export default function Paywall({ message, compact }: { message?: string; compact?: boolean }) {
  return (
    <div role="region" aria-label="Unlock the Live Tracker" style={{
      background: 'var(--bg2)', border: '1px solid var(--gold)', borderRadius: 12,
      padding: compact ? 14 : 18, marginBottom: 14,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Lock size={18} style={{ color: 'var(--gold)' }} />
        <b style={{ fontSize: 16, color: 'var(--gold)' }}>Unlock the Live Tracker: $7, one time</b>
      </div>
      <p style={{ fontSize: 13.5, color: 'var(--text2)', lineHeight: 1.5, margin: '0 0 14px' }}>
        {message || DEFAULT_PAYWALL_MESSAGE}
      </p>
      <Link href="/live-tracker?checkout=1" style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%',
        minHeight: 52, borderRadius: 10, background: 'var(--gold)', color: '#1c1c1c',
        fontSize: 16, fontWeight: 800, textDecoration: 'none',
      }}>Get the Live Tracker for $7</Link>
      <div style={{ textAlign: 'center', marginTop: 8 }}>
        <Link href="/live-tracker" style={{
          display: 'inline-flex', alignItems: 'center', minHeight: 44, padding: '0 8px',
          fontSize: 13, color: 'var(--text3)',
        }}>What&apos;s included</Link>
      </div>
    </div>
  )
}
