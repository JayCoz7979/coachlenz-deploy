// Where to send a coach after login / signup finishes. Used by the $7 Live Tracker
// page so a signed-out coach who taps "Get the Live Tracker" comes back to checkout.
// Only same-site paths are accepted (no open redirect).
const KEY = 'cl_post_auth_next'

export function safeNextPath(p: string | null | undefined): string | null {
  if (!p || typeof p !== 'string') return null
  if (!p.startsWith('/') || p.startsWith('//') || p.includes('\\')) return null
  return p
}

export function rememberNext(path: string) {
  const safe = safeNextPath(path)
  if (safe && typeof window !== 'undefined') localStorage.setItem(KEY, safe)
}

/** The remembered path (cleared once read), or the fallback. */
export function consumeNext(fallback: string): string {
  if (typeof window === 'undefined') return fallback
  const v = safeNextPath(localStorage.getItem(KEY))
  localStorage.removeItem(KEY)
  return v || fallback
}
