'use client'

import { useSignupGate } from '@/components/signup/useSignupGate'
import HomeLanding from './HomeLanding'

export default function HomeClient({ initialOpen }: { initialOpen: boolean }) {
  const gate = useSignupGate(initialOpen)
  return <HomeLanding signupsOpen={gate === 'open'} />
}
