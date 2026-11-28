// Where to send a coach after login / signup. Used by the $7 Live Tracker landing page
// so a signed-out coach goes through login or signup and comes straight back to
// checkout (/live-tracker?checkout=1) instead of the dashboard.

const KEY = 'clz_post_auth_next'

/** Only same-site paths; blocks protocol-relative ("//evil") and backslash tricks. */
export function safeNext(raw: string | null | undefined): string | null {
  if (!raw) return null
  const v = String(raw).trim()
  if (!v.startsWith('/') || v.startsWith('//') || v.startsWith('/\\') || /[\r\n]/.test(v)) return null
  return v
}

/** Remember a return path across the multi-step signup (register -> verify -> sport). */
export function rememberNext(path: string): void {
  const safe = safeNext(path)
  if (!safe || typeof window === 'undefined') return
  try { window.sessionStorage.setItem(KEY, safe) } catch { /* private mode */ }
}

/** Read (and clear) the return path: the ?next= query wins, then the remembered one. */
export function takeNext(): string | null {
  if (typeof window === 'undefined') return null
  let fromQuery: string | null = null
  try { fromQuery = new URLSearchParams(window.location.search).get('next') } catch { /* ignore */ }
  let stored: string | null = null
  try { stored = window.sessionStorage.getItem(KEY); window.sessionStorage.removeItem(KEY) } catch { /* ignore */ }
  return safeNext(fromQuery) || safeNext(stored)
}
