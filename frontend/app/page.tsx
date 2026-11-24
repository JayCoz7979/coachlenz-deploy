import type { Metadata } from 'next'
import HomeClient from './HomeClient'
import { signupsEnabled } from '@/lib/signups'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  const open = await signupsEnabled()
  if (open) return {}
  return {
    title: 'CoachLenz is launching soon',
    description: 'CoachLenz is launching soon for school basketball and football game film. Join the waitlist.',
    robots: { index: false, follow: false },
  }
}

export default async function Page() {
  const open = await signupsEnabled()
  return <HomeClient initialOpen={open} />
}
