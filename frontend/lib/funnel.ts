// First-party conversion-funnel beacon. No third-party trackers, no PII: anon_id is
// a random id kept in localStorage only so one visitor is not counted many times
// across page views. Every call is best-effort and never throws into the page.
import api from '@/lib/api'

const KEY = 'cl_anon'

export function getAnonId(): string {
  if (typeof window === 'undefined') return ''
  try {
    let id = localStorage.getItem(KEY)
    if (!id) {
      id = (typeof crypto !== 'undefined' && crypto.randomUUID)
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`
      localStorage.setItem(KEY, id)
    }
    return id
  } catch {
    return ''
  }
}

export type FunnelEvent = 'landing_view' | 'cta_click' | 'signup_view'

export function track(event: FunnelEvent, meta?: Record<string, any>) {
  try {
    const path = typeof window !== 'undefined' ? window.location.pathname : undefined
    api.post('/funnel/event', { event, anon_id: getAnonId(), path, meta }).catch(() => {})
  } catch {
    // Telemetry must never break the page.
  }
}
