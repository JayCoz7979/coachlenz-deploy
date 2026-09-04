// First-party conversion-funnel beacon + channel attribution. No third-party
// trackers, no PII: anon_id is a random id kept in localStorage only so one visitor
// is not counted many times, and source is a coarse channel label (utm_source, else
// the referrer host, else 'direct') captured once on the first visit. Every call is
// best-effort and never throws into the page.
import api from '@/lib/api'

const ID_KEY = 'cl_anon'
const SRC_KEY = 'cl_src'

export function getAnonId(): string {
  if (typeof window === 'undefined') return ''
  try {
    let id = localStorage.getItem(ID_KEY)
    if (!id) {
      id = (typeof crypto !== 'undefined' && crypto.randomUUID)
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`
      localStorage.setItem(ID_KEY, id)
    }
    return id
  } catch {
    return ''
  }
}

// The channel this visitor came from, captured once and kept for the whole journey.
export function getSource(): string {
  if (typeof window === 'undefined') return 'direct'
  try {
    const existing = localStorage.getItem(SRC_KEY)
    if (existing) return existing
    let src = 'direct'
    const utm = new URLSearchParams(window.location.search).get('utm_source')
    if (utm) {
      src = utm
    } else if (document.referrer) {
      try {
        const host = new URL(document.referrer).hostname
        if (host && host !== window.location.hostname) src = host
      } catch { /* malformed referrer */ }
    }
    src = src.toLowerCase().slice(0, 120)
    localStorage.setItem(SRC_KEY, src)
    return src
  } catch {
    return 'direct'
  }
}

export type FunnelEvent = 'landing_view' | 'cta_click' | 'signup_view'

export function track(event: FunnelEvent, meta?: Record<string, any>) {
  try {
    const path = typeof window !== 'undefined' ? window.location.pathname : undefined
    api.post('/funnel/event', { event, anon_id: getAnonId(), source: getSource(), path, meta })
      .catch(() => {})
  } catch {
    // Telemetry must never break the page.
  }
}
