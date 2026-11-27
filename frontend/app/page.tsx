import type { Metadata } from 'next'
import HomeView from './HomeView'

// The landing itself is an interactive client component (HomeView). This server wrapper
// adds the one SEO signal a client page cannot export: an absolute canonical for the
// root. Title and description stay the layout defaults, which are the homepage's own.
export const metadata: Metadata = {
  alternates: { canonical: '/' },
}

export default function Page() {
  return <HomeView />
}
