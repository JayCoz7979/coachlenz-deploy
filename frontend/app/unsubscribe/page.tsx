'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import { publicApi } from '@/lib/api'
import { confirmUnsubscribe } from '@/lib/unsubscribeState'

// Public marketing unsubscribe page, opened from the link in a marketing email.
// Opening the page changes nothing (link scanners and prefetchers open links
// too). The person clicks "Confirm unsubscribe", and the page says they are
// unsubscribed only when the API answers 2xx. Mail providers use the separate
// RFC 8058 one-click POST at /unsubscribe/one-click.
type State = 'loading' | 'confirm' | 'working' | 'done' | 'error' | 'missing'

const ERROR_TEXT = "We couldn't update your preferences. Try again or email support@coachlenz.com."

export default function UnsubscribePage() {
  const [state, setState] = useState<State>('loading')
  const [token, setToken] = useState('')

  useEffect(() => {
    const t = (new URLSearchParams(window.location.search).get('token') || '').trim()
    setToken(t)
    setState(t ? 'confirm' : 'missing')
  }, [])

  const submit = async () => {
    setState('working')
    setState(await confirmUnsubscribe((path: string, body: unknown) => publicApi.post(path, body), token))
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="card max-w-md w-full text-center space-y-4">
        {state === 'loading' && (
          <>
            <h1 className="text-xl font-bold">One moment</h1>
            <p className="text-gray-400">Loading your email preferences.</p>
          </>
        )}
        {state === 'confirm' && (
          <>
            <h1 className="text-xl font-bold">Unsubscribe from CoachLenz marketing emails?</h1>
            <p className="text-gray-400">Account and film-report emails still come through, since those are part of using CoachLenz.</p>
            <button type="button" onClick={submit} className="btn-primary w-full">Confirm unsubscribe</button>
          </>
        )}
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
        {state === 'error' && (
          <>
            <h1 className="text-xl font-bold">Something went wrong</h1>
            <p className="text-gray-400" role="alert">{ERROR_TEXT}</p>
            <button type="button" onClick={submit} className="btn-primary w-full">Try again</button>
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
