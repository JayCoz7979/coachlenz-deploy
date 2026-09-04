import type { Metadata } from 'next'
import FilmTimeCalculator from './FilmTimeCalculator'

export const metadata: Metadata = {
  title: 'Film Breakdown Time Calculator for Coaches',
  description: 'See how many hours you spend breaking down game film every season by hand, and how many you could get back. Free, no signup required to use it.',
  alternates: { canonical: '/tools/film-time-saved' },
  openGraph: {
    title: 'Film Breakdown Time Calculator for Coaches',
    description: 'See how many hours breaking down film costs you every season.',
    type: 'website',
  },
}

export default function Page() {
  return <FilmTimeCalculator />
}
