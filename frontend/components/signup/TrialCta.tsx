'use client'

import Link from 'next/link'
import { useSignupGate } from './useSignupGate'

/** A "start trial" link. While signups are closed it points at the waitlist. */
export default function TrialCta({
  openHref = '/onboarding',
  openLabel,
  closedHref = '/waitlist',
  closedLabel = 'Join the waitlist',
  className,
  onClick,
}: {
  openHref?: string
  openLabel: string
  closedHref?: string
  closedLabel?: string
  className?: string
  onClick?: () => void
}) {
  const gate = useSignupGate()
  const open = gate === 'open'
  return (
    <Link href={open ? openHref : closedHref} onClick={onClick} className={className}>
      {open ? openLabel : closedLabel}
    </Link>
  )
}
