'use client'
/**
 * Canary-gated service-worker registration (Phase A).
 * - `?sw=1` opts THIS device in (persists via localStorage clz_sw=1) and registers /sw.js.
 * - `?sw=0` opts out: unregisters and clears CoachLenz caches on this device.
 * - Everyone else (no flag): actively unregisters any SW + clears clz- caches, so a
 *   non-canary user can never end up controlled by a stale worker. Near-zero blast radius.
 */
import { useEffect } from 'react'

export default function ServiceWorkerRegistrar() {
  useEffect(() => {
    if (typeof window === 'undefined' || !('serviceWorker' in navigator)) return

    const params = new URLSearchParams(window.location.search)
    if (params.get('sw') === '1') { try { localStorage.setItem('clz_sw', '1') } catch {} }
    if (params.get('sw') === '0') { try { localStorage.removeItem('clz_sw') } catch {} }

    let enabled = false
    try { enabled = localStorage.getItem('clz_sw') === '1' } catch {}

    const cleanup = () => {
      navigator.serviceWorker.getRegistrations().then(rs => rs.forEach(r => r.unregister())).catch(() => {})
      if (typeof caches !== 'undefined') {
        caches.keys().then(keys => keys.forEach(k => { if (k.startsWith('clz-')) caches.delete(k) })).catch(() => {})
      }
    }

    if (!enabled) { cleanup(); return }   // not a canary device → ensure fully off
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  }, [])

  return null
}
