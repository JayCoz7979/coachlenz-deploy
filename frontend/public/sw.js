/*
 * CoachLenz service worker — PHASE B (canary): cold offline load for /live.
 *
 * Strategy:
 *   - Immutable /_next/static assets → cache-first (safe forever).
 *   - /live NAVIGATIONS → network-first: online it's always fresh AND cached; offline
 *     it serves the cached document for that exact URL so the SPA boots and the client
 *     offline layer (localStorage session + play queue) takes over. A /live URL you
 *     never opened online has no cached document → normal offline error.
 *   - Everything else (other routes, RSC, the cross-origin API) → network, untouched.
 *
 * Only registered on canary devices (?sw=1 / localStorage clz_sw=1; see
 * ServiceWorkerRegistrar). No skipWaiting: an update activates on the NEXT load, never
 * mid-session. Served no-cache so updates + the kill switch always reach devices.
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
const VERSION = 'clz-swB-v1';
const STATIC = VERSION + '-static';
const DOCS = VERSION + '-docs';

self.addEventListener('install', () => {
  // No skipWaiting on purpose (see header).
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key.startsWith('clz-') && key !== STATIC && key !== DOCS) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

async function cacheFirst(req) {
  const cache = await caches.open(STATIC);
  const hit = await cache.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res && res.ok && res.type === 'basic') cache.put(req, res.clone());
  return res;
}

async function networkFirstDoc(req) {
  const cache = await caches.open(DOCS);
  try {
    const res = await fetch(req);
    if (res && res.ok && res.type === 'basic') cache.put(req, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(req);   // exact-URL cached document
    if (hit) return hit;
    return new Response(
      '<!doctype html><meta charset="utf-8"><title>Offline</title>' +
      '<body style="font-family:system-ui;background:#1c1c1c;color:#f8f6f0;display:flex;' +
      'align-items:center;justify-content:center;height:100vh;margin:0;text-align:center">' +
      '<div><h1 style="color:#C9A84C">Offline</h1><p>Reconnect to open this session for the first time. ' +
      'Sessions you have already opened work offline.</p></div>',
      { headers: { 'Content-Type': 'text/html' }, status: 503 }
    );
  }
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  let url;
  try { url = new URL(req.url); } catch { return; }
  if (url.origin !== self.location.origin) return;   // never intercept the API / cross-origin

  if (url.pathname.startsWith('/_next/static/') || url.pathname === '/coachlenz-logo.png') {
    event.respondWith(cacheFirst(req));
    return;
  }
  // Cold offline load is scoped to /live only (narrow blast radius).
  if (req.mode === 'navigate' && url.pathname.startsWith('/live')) {
    event.respondWith(networkFirstDoc(req));
    return;
  }
  // Everything else: straight to the network (no offline fallback).
});
