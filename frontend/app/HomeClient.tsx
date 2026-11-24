'use client'

import ComingSoon from '@/components/signup/ComingSoon'
import { useSignupGate } from '@/components/signup/useSignupGate'
import HomeLanding from './HomeLanding'

export default function HomeClient({ initialOpen }: { initialOpen: boolean }) {
  const gate = useSignupGate(initialOpen)
  if (gate !== 'open') return <ComingSoon source="app-home" />
  return <HomeLanding />
}
