import type { MetadataRoute } from 'next'

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://app.coachlenz.com'

// Public marketing surfaces are crawlable; the authenticated app is not. Keeping the
// private, per-user pages out of the index protects them and keeps the crawl focused
// on the pages meant to rank.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: ['/', '/tools/', '/terms', '/privacy'],
        disallow: [
          '/admin', '/dashboard', '/settings', '/games', '/reports', '/roster',
          '/players', '/grades', '/scout', '/live', '/recruiting', '/staff',
          '/teams', '/tendencies', '/intel', '/messaging', '/referrals', '/ad',
          '/playlists', '/onboarding', '/login', '/accept-invite', '/reset-password',
          '/forgot-password',
        ],
      },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
  }
}
