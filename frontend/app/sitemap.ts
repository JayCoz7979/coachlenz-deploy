import type { MetadataRoute } from 'next'
import { signupsEnabled } from '@/lib/signups'

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://app.coachlenz.com'

export const dynamic = 'force-dynamic'

// Only genuinely public, indexable pages belong here. The authed app (dashboard,
// reports, roster, and the rest) is disallowed in robots and stays out. While
// signups are closed, the marketing pages are noindex and drop out of the sitemap.
// Terms and privacy stay.
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date()
  const open = await signupsEnabled()
  const paths = open
    ? [
        '/', '/tools/film-time-saved',
        '/sample/football', '/sample/flag', '/sample/basketball',
        '/terms', '/privacy',
      ]
    : ['/terms', '/privacy']
  return paths.map((p) => ({
    url: `${SITE_URL}${p === '/' ? '' : p}`,
    lastModified: now,
    changeFrequency: 'weekly',
    priority: p === '/' ? 1 : 0.7,
  }))
}
