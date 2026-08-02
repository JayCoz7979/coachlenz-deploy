/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  images: { domains: ['*'] },
  // The service worker must never be edge/browser-cached, or a bad SW (or the kill
  // switch) can't reach devices. Root scope lets /sw.js control the whole origin.
  async headers() {
    return [
      {
        source: '/sw.js',
        headers: [
          { key: 'Cache-Control', value: 'no-cache, no-store, must-revalidate' },
          { key: 'Service-Worker-Allowed', value: '/' },
        ],
      },
      {
        source: '/manifest.webmanifest',
        headers: [
          { key: 'Content-Type', value: 'application/manifest+json' },
        ],
      },
    ]
  },
  // The type-check gate stays ON. It is the thing that catches a broken build
  // BEFORE it ships as a silent failure. Full `tsc --noEmit` verified clean;
  // do not re-add ignoreBuildErrors to "unblock" a deploy — fix the type error.
}
module.exports = nextConfig
