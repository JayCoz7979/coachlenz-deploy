import type { Metadata } from 'next'

// The confirm URL carries a single-use token: never send it on as a Referer, and keep
// the page out of search indexes.
export const metadata: Metadata = {
  title: 'Confirm your email | CoachLenz',
  referrer: 'no-referrer',
  robots: { index: false, follow: false },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
