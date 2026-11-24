import type { Metadata } from 'next'
import ComingSoon from '@/components/signup/ComingSoon'

export const metadata: Metadata = {
  title: 'CoachLenz is launching soon',
  description: 'CoachLenz is launching soon for school basketball and football game film. Join the waitlist.',
  robots: { index: false, follow: false },
}

export default function WaitlistPage() {
  return <ComingSoon source="app-waitlist" />
}
