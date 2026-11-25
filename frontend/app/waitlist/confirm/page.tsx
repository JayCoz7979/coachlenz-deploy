import { Suspense } from 'react'
import type { Metadata } from 'next'
import ConfirmClient from './ConfirmClient'

export const metadata: Metadata = {
  title: "You're on the list",
  robots: { index: false, follow: false },
}

export default function ConfirmPage() {
  return (
    <Suspense fallback={null}>
      <ConfirmClient />
    </Suspense>
  )
}
