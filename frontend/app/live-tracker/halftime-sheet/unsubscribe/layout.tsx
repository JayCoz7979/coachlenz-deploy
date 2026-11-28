import type { Metadata } from 'next'

// The unsubscribe URL carries a signed token: never send it on as a Referer, and keep
// the page out of search indexes.
export const metadata: Metadata = {
  title: 'Unsubscribe | CoachLenz',
  referrer: 'no-referrer',
  robots: { index: false, follow: false },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
