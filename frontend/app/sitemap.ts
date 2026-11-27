import type { MetadataRoute } from 'next'
import lastmod from './sitemap-data.json'

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://app.coachlenz.com'

// Only genuinely public, indexable pages belong here. The authed app (dashboard,
// reports, roster, and the rest) is disallowed in robots and stays out. Per-URL
// lastmod is each page's real last content change (scripts/gen-sitemap-dates.mjs
// refreshes it from git at build), never one build timestamp across every URL.
const LASTMOD = lastmod as Record<string, string>

export default function sitemap(): MetadataRoute.Sitemap {
  const paths = [
    '/', '/tools/film-time-saved',
    '/sample/football', '/sample/flag', '/sample/basketball',
    '/terms', '/privacy',
  ]
  return paths.map((p) => ({
    url: `${SITE_URL}${p === '/' ? '' : p}`,
    lastModified: LASTMOD[p] ? new Date(LASTMOD[p]) : undefined,
    changeFrequency: 'weekly' as const,
    priority: p === '/' ? 1 : 0.7,
  }))
}
