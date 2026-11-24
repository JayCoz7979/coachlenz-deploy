import type { Metadata } from 'next'
import { type ExampleKey } from '../../examples/reports'
import SampleView from './SampleView'
import { closedPageRobots } from '@/lib/signups'

// Request-time render so the noindex tag follows the live signup flag.
export const dynamic = 'force-dynamic'

// Public, no-login proof pages for cold outreach and SEO. Same illustrative sample
// reports the in-app /examples route shows logged-in coaches, served here without the
// auth wall so a cold link actually opens. The in-app /examples stays gated.
const META: Record<ExampleKey, { title: string; description: string }> = {
  football: {
    title: 'What an AI football film breakdown looks like',
    description: 'See a real CoachLenz full-game football breakdown: run-gap and pass heat maps, player tendencies by jersey, and adjustments. Free to view, no signup.',
  },
  flag: {
    title: 'What an AI flag football breakdown looks like',
    description: 'See a real CoachLenz flag football breakdown: rush-lane and pass field heat maps and opponent tendencies. Free to view, no signup.',
  },
  basketball: {
    title: 'What an AI basketball film breakdown looks like',
    description: 'See a real CoachLenz basketball breakdown: foul-trouble alerts, shot chart, shot-location court, and season trend. Free to view, no signup.',
  },
}

export async function generateMetadata({ params }: { params: { sport: string } }): Promise<Metadata> {
  const robots = await closedPageRobots()
  const m = META[params.sport as ExampleKey]
  if (!m) return { title: 'Sample report', ...robots }
  return {
    title: m.title,
    description: m.description,
    alternates: { canonical: `/sample/${params.sport}` },
    openGraph: { title: m.title, description: m.description, type: 'article', url: `/sample/${params.sport}` },
    ...robots,
  }
}

export default function Page({ params }: { params: { sport: string } }) {
  return <SampleView sport={params.sport} />
}
