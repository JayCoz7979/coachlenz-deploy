// Safe post-login / post-signup return path. Only same-site absolute paths are
// allowed ("/live-tracker?buy=1"); anything that could leave the site
// ("//evil.example", "https://...", "/\\evil", "javascript:") falls back to null.
export function safeNext(raw: string | null | undefined): string | null {
  if (!raw) return null
  let v = raw
  try { v = decodeURIComponent(raw) } catch { return null }
  if (!v.startsWith('/') || v.startsWith('//') || v.includes('\\')) return null
  if (/[\u0000-\u001f]/.test(v)) return null
  return v
}

/** Read ?next= from the current URL (client only). */
export function nextFromLocation(): string | null {
  if (typeof window === 'undefined') return null
  return safeNext(new URLSearchParams(window.location.search).get('next'))
}
