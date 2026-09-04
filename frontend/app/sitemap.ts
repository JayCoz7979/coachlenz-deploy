import type { MetadataRoute } from 'next'

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://app.coachlenz.com'

// Only genuinely public, indexable pages belong here. The authed app (dashboard,
// reports, roster, and the rest) is disallowed in robots and stays out.
export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date()
  const paths = ['/', '/tools/film-time-saved', '/terms', '/privacy']
  return paths.map((p) => ({
    url: `${SITE_URL}${p === '/' ? '' : p}`,
    lastModified: now,
    changeFrequency: 'weekly',
    priority: p === '/' ? 1 : 0.7,
  }))
}
