'use client'

import { useEffect, useState } from 'react'
import { publicApi } from '@/lib/api'

export type SignupGate = 'loading' | 'open' | 'closed'

/**
 * Closed until GET /auth/signups says otherwise. Pass the server's answer as
 * initialOpen so the first paint matches the flag. A failed check stays closed
 * unless the server already said open.
 */
export function useSignupGate(initialOpen?: boolean): SignupGate {
  const [gate, setGate] = useState<SignupGate>(
    initialOpen === undefined ? 'loading' : initialOpen ? 'open' : 'closed',
  )

  useEffect(() => {
    let cancelled = false
    publicApi
      .get('/auth/signups', { timeout: 8000 })
      .then((r) => {
        if (!cancelled) setGate(r.data?.signups_enabled === true ? 'open' : 'closed')
      })
      .catch(() => {
        if (cancelled) return
        setGate(initialOpen === true ? 'open' : 'closed')
      })
    return () => {
      cancelled = true
    }
  }, [initialOpen])

  return gate
}
