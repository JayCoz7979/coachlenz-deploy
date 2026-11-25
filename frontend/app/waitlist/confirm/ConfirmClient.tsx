'use client'

import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { publicApi } from '@/lib/api'

export default function ConfirmClient() {
  const params = useSearchParams()
  const [download, setDownload] = useState<string | null>(null)
  const [message, setMessage] = useState('Confirming your spot...')

  useEffect(() => {
    const token = params.get('token') || ''
    if (!token) {
      setMessage('This confirm link is missing. The Halftime Sheet is not available yet.')
      return
    }
    publicApi.post('/waitlist/confirm', { token })
      .then((r) => {
        if (r.data?.ok && r.data?.download_url) {
          setDownload(r.data.download_url)
          setMessage("You're on the list. Your free Halftime Sheet is ready.")
        } else {
          setDownload(null)
          setMessage('This confirm link is not valid. The Halftime Sheet is not available yet.')
        }
      })
      .catch(() => {
        setDownload(null)
        setMessage('This confirm link is not valid. The Halftime Sheet is not available yet.')
      })
  }, [params])

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center px-6">
      <div className="max-w-lg text-center">
        <h1 className="text-3xl font-bold text-gray-100 mb-4">You&apos;re on the list.</h1>
        <p className="text-base text-gray-100 mb-6">{message}</p>
        {download ? <a href={download} className="btn-primary inline-block px-8 py-3">Download</a> : null}
        <p className="text-sm text-gray-400 mt-6">We&apos;ll email you when CoachLenz opens.</p>
      </div>
    </div>
  )
}
