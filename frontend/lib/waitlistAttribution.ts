// First-load attribution for the waitlist. Later pages in the same tab reuse it.
// Kept in sessionStorage so a refresh of the form does not drop the original UTMs.

const KEY = 'cl_wl_attr'

export type WaitlistAttr = {
  utm_source: string
  utm_medium: string
  utm_campaign: string
  utm_content: string
  utm_term: string
  referrer: string
  landing_path: string
  lead_magnet: string
  ref_code: string
}

const EMPTY: WaitlistAttr = {
  utm_source: '',
  utm_medium: '',
  utm_campaign: '',
  utm_content: '',
  utm_term: '',
  referrer: '',
  landing_path: '',
  lead_magnet: '',
  ref_code: '',
}

function clip(value: string): string {
  return value.trim().slice(0, 120)
}

function read(): WaitlistAttr {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return { ...EMPTY }
    return { ...EMPTY, ...JSON.parse(raw) }
  } catch {
    return { ...EMPTY }
  }
}

function write(data: WaitlistAttr) {
  try { sessionStorage.setItem(KEY, JSON.stringify(data)) } catch { /* private mode */ }
}

/** Call once per tab. The first page that runs this wins. */
export function captureWaitlistAttribution() {
  if (typeof window === 'undefined') return
  try {
    if (sessionStorage.getItem(KEY)) return
  } catch {
    return
  }
  const q = new URLSearchParams(window.location.search)
  let referrer = ''
  try {
    if (document.referrer) referrer = new URL(document.referrer).hostname
  } catch { /* bad referrer */ }
  write({
    utm_source: clip(q.get('utm_source') || ''),
    utm_medium: clip(q.get('utm_medium') || ''),
    utm_campaign: clip(q.get('utm_campaign') || ''),
    utm_content: clip(q.get('utm_content') || ''),
    utm_term: clip(q.get('utm_term') || ''),
    referrer: clip(referrer),
    landing_path: clip(window.location.pathname),
    lead_magnet: clip(q.get('lead_magnet') || q.get('magnet') || ''),
    ref_code: clip(q.get('ref') || ''),
  })
}

/** A /refer/[code] visit. Fills ref_code only when it is still empty. */
export function rememberRefCode(code: string) {
  captureWaitlistAttribution()
  const data = read()
  if (!data.ref_code && code.trim()) {
    data.ref_code = clip(code)
    write(data)
  }
}

export function readWaitlistAttribution(): Partial<WaitlistAttr> {
  if (typeof window === 'undefined') return {}
  captureWaitlistAttribution()
  const data = read()
  const out: Partial<WaitlistAttr> = {}
  ;(Object.keys(data) as (keyof WaitlistAttr)[]).forEach((key) => {
    if (data[key]) out[key] = data[key]
  })
  return out
}
