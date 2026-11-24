'use client'

import { useEffect } from 'react'
import { rememberRefCode } from '@/lib/waitlistAttribution'

export default function RememberRef({ code }: { code: string }) {
  useEffect(() => { rememberRefCode(code) }, [code])
  return null
}
