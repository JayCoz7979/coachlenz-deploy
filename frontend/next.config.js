/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  images: { domains: ['*'] },
  // The type-check gate stays ON. It is the thing that catches a broken build
  // BEFORE it ships as a silent failure. Full `tsc --noEmit` verified clean;
  // do not re-add ignoreBuildErrors to "unblock" a deploy — fix the type error.
}
module.exports = nextConfig
