import type { Metadata } from 'next'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

/** Live read of GET /auth/signups. Any failure is treated as closed. */
export async function signupsEnabled(): Promise<boolean> {
  try {
    const res = await fetch(`${API}/auth/signups`, { cache: 'no-store' })
    if (!res.ok) return false
    const data = await res.json()
    return data?.signups_enabled === true
  } catch {
    return false
  }
}

/** noindex for a public page while new signups are closed. Empty when they are open. */
export async function closedPageRobots(): Promise<Metadata> {
  if (await signupsEnabled()) return {}
  return { robots: { index: false, follow: false } }
}
