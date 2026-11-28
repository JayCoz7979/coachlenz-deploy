import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Live Tracker: chart the game live, get the Halftime Sheet | CoachLenz',
  description:
    'Chart Football, Flag Football, or Basketball live from the sideline and get the Halftime Sheet at the break. $7 USD, one time.',
  alternates: { canonical: '/live-tracker' },
}

export default function LiveTrackerLayout({ children }: { children: React.ReactNode }) {
  return children
}
