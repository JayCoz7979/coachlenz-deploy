'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import api from '@/lib/api'

// Public one-click marketing unsubscribe. The link in a marketing email carries the
// coach's stable token; this page posts it to flip their opt-in off. The endpoint is
// idempotent and always returns ok, so there is no "invalid token" dead end to show.
export default function UnsubscribePage() {
  const [state, setState] = useState<'working' | 'done' | 'missing'>('working')

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token') || ''
    if (!token) { setState('missing'); return }
    let cancelled = false
    api.post('/auth/unsubscribe', { token })
      .catch(() => { /* idempotent + best-effort: still confirm, never block the coach */ })
      .finally(() => { if (!cancelled) setState('done') })
    return () => { cancelled = true }
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="card max-w-md w-full text-center space-y-4">
        {state === 'working' && (
          <>
            <h1 className="text-xl font-bold">One moment</h1>
            <p className="text-gray-400">Updating your email preferences.</p>
          </>
        )}
        {state === 'done' && (
          <>
            <h1 className="text-xl font-bold">You&apos;re unsubscribed</h1>
            <p className="text-gray-400">You won&apos;t get CoachLenz marketing emails anymore. Account and film-report emails still come through, since those are part of using CoachLenz.</p>
            <p className="text-sm"><Link href="/login" className="text-brand-400 hover:underline">Back to CoachLenz</Link></p>
          </>
        )}
        {state === 'missing' && (
          <>
            <h1 className="text-xl font-bold">Link incomplete</h1>
            <p className="text-gray-400">This unsubscribe link is missing its code. Open the link straight from the email, or contact support and we&apos;ll take care of it.</p>
            <p className="text-sm"><Link href="/login" className="text-brand-400 hover:underline">Back to CoachLenz</Link></p>
          </>
        )}
      </div>
    </div>
  )
}
