import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from './api'

/**
 * Sport guard for the football scout pages. Keeps scouting tied to the sport the
 * client set on their team/film: a basketball-only org that lands on a football
 * scout URL is sent back to /scout (which dispatches to the basketball scout).
 * Football or mixed or no-team orgs proceed. On any error we let them through
 * rather than trapping the user.
 *
 * Returns 'checking' while resolving (render a spinner) or 'ok' to proceed.
 */
export function useFootballGuard(enabled: boolean): 'checking' | 'ok' {
  const router = useRouter()
  const [state, setState] = useState<'checking' | 'ok'>('checking')

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    api.get('/teams').then(res => {
      if (cancelled) return
      const sports: string[] = (res.data || []).map((t: any) => t.sport)
      const hasFootball = sports.some(s => s === 'football' || s === 'flag_football')
      const hasBasketball = sports.includes('basketball')
      if (hasBasketball && !hasFootball) { router.replace('/scout'); return }
      setState('ok')
    }).catch(() => setState('ok'))
    return () => { cancelled = true }
  }, [enabled, router])

  return state
}
