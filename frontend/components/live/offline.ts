// Offline persistence for the Live Game logger. Plays are written to localStorage the
// instant they're logged, so a crash / reload / dead zone never loses them, and an
// unsynced queue flushes to the server on reconnect. Each play carries a client_uid so
// the server dedupes re-sends (idempotent). No service worker — this covers "log offline
// once the session is loaded, sync when back online", not cold-loading the app offline.

export type StoredPlay = { client_uid?: string; synced?: boolean; event_id?: string; [k: string]: any }

const PKEY = (sid: string) => `clz_live_plays_${sid}`
const CKEY = (sid: string) => `clz_live_cfg_${sid}`

export function newUid(): string {
  try {
    if (typeof crypto !== 'undefined' && (crypto as any).randomUUID) return (crypto as any).randomUUID()
  } catch { /* fall through */ }
  return 'uid_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10)
}

export function loadPlays(sid: string): StoredPlay[] {
  if (typeof window === 'undefined') return []
  try { const raw = window.localStorage.getItem(PKEY(sid)); const a = raw ? JSON.parse(raw) : []; return Array.isArray(a) ? a : [] }
  catch { return [] }
}

export function savePlays(sid: string, plays: StoredPlay[]): void {
  if (typeof window === 'undefined') return
  try { window.localStorage.setItem(PKEY(sid), JSON.stringify(plays)) } catch { /* quota / private mode */ }
}

// Cache the session config so a transient session-load failure still renders the logger
// (the app JS must already be loaded — a true cold offline load needs a service worker).
export function loadCfg(sid: string): any | null {
  if (typeof window === 'undefined') return null
  try { const raw = window.localStorage.getItem(CKEY(sid)); return raw ? JSON.parse(raw) : null } catch { return null }
}

export function saveCfg(sid: string, cfg: any): void {
  if (typeof window === 'undefined') return
  try { window.localStorage.setItem(CKEY(sid), JSON.stringify(cfg)) } catch { /* ignore */ }
}
