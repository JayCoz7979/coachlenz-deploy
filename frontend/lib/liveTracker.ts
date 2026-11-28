// $7 one-time Live Tracker unlock: client helpers. The server decides access
// (GET /live/access, and every /live route 403s when locked); nothing here grants it.
import api from '@/lib/api'

export const LIVE_TRACKER_PATH = '/live-tracker'
/** Where a signed-out coach returns after login/signup: straight back into checkout. */
export const LIVE_TRACKER_BUY_PATH = '/live-tracker?buy=1'

export type LiveAccess = { has_access: boolean; reason: string | null; purchased_at: string | null; checkout_available: boolean }

export function isSignedIn(): boolean {
  return typeof window !== 'undefined' && !!localStorage.getItem('access_token')
}

export async function getLiveAccess(): Promise<LiveAccess> {
  const r = await api.get('/live/access')
  return r.data as LiveAccess
}

/** Start the test-mode Stripe Checkout and leave the page. Throws the server's
 *  coach-facing message on failure (e.g. checkout not configured yet). */
export async function startLiveTrackerCheckout(): Promise<void> {
  const origin = window.location.origin
  const r = await api.post('/billing/live-tracker/checkout', {
    // {CHECKOUT_SESSION_ID} is filled in by Stripe; the success page only reads it
    // for display. Access comes from the webhook, never from this redirect.
    success_url: `${origin}/live-tracker/success?session_id={CHECKOUT_SESSION_ID}`,
    cancel_url: `${origin}/live-tracker?checkout=cancelled`,
  })
  window.location.href = r.data.checkout_url
}

export function checkoutErrorMessage(e: any): string {
  const d = e?.response?.data?.detail
  if (typeof d === 'string' && d.length < 300) return d
  return 'Could not start checkout. Nothing was charged. Please try again.'
}
