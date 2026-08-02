/*
 * CoachLenz service worker — PHASE A (canary).
 *
 * Scope: cache-first for IMMUTABLE, content-hashed static assets; network for
 * everything else (documents, RSC, API) with NO offline fallback yet. Cross-origin
 * (the API) is never touched. This validates registration / update / kill-switch
 * mechanics live with near-zero risk. Phase B adds the /live offline document fallback.
 *
 * Only registered on devices opted into the canary (see ServiceWorkerRegistrar:
 * ?sw=1 / localStorage clz_sw=1). Served no-cache (next.config headers) so updates
 * and the kill switch always reach devices.
 *
 * GLOBAL KILL SWITCH (rollback): replace this file's body with the self-destruct SW:
 *   self.addEventListener('install', () => self.skipWaiting());
 *   self.addEventListener('activate', (e) => e.waitUntil((async () => {
 *     for (const k of await caches.keys()) await caches.delete(k);
 *     await self.registration.unregister();
 *     for (const c of await self.clients.matchAll()) c.navigate(c.url);
 *   })()));
 * Deploy it and every device unregisters + clears caches on its next load.
 */
const VERSION = 'clz-swA-v1';
const STATIC = VERSION + '-static';

self.addEventListener('install', () => {
  // Deliberately NO skipWaiting: an updated SW activates on the NEXT load, never
  // mid-session, so we can't serve an old document against new chunks.
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key.startsWith('clz-') && key !== STATIC) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  let url;
  try { url = new URL(req.url); } catch { return; }
  if (url.origin !== self.location.origin) return;   // never intercept the API / cross-origin

  // Immutable, content-hashed assets → cache-first (safe forever).
  if (url.pathname.startsWith('/_next/static/') || url.pathname === '/coachlenz-logo.png') {
    event.respondWith((async () => {
      const cache = await caches.open(STATIC);
      const hit = await cache.match(req);
      if (hit) return hit;
      const res = await fetch(req);
      if (res && res.ok && res.type === 'basic') cache.put(req, res.clone());
      return res;
    })());
    return;
  }
  // Everything else: let the browser hit the network (no offline fallback in Phase A).
});
