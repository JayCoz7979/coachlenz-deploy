'use client'

import { useEffect } from 'react'
import Link from 'next/link'
import logo from '../../public/coachlenz-logo.png'
import WaitlistForm from './WaitlistForm'

function NoIndex() {
  useEffect(() => {
    const meta = document.createElement('meta')
    meta.name = 'robots'
    meta.content = 'noindex, nofollow'
    document.head.appendChild(meta)
    return () => { meta.remove() }
  }, [])
  return null
}

/** Full-page waitlist used by /waitlist and by /onboarding while signups are closed. */
export default function ComingSoon({ source = 'waitlist' }: { source?: string }) {
  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      <NoIndex />
      <header className="border-b border-gray-800 px-6 sm:px-8 py-4 flex items-center justify-between">
        <Link href="/"><img src={logo.src} alt="CoachLenz" style={{ height: 30, width: 'auto' }} /></Link>
        <Link href="/login" className="text-sm text-gray-400 hover:text-gray-100">Sign in</Link>
      </header>

      <main className="flex-1 flex items-center justify-center px-6 py-16">
        <div className="w-full max-w-lg">
          <p className="text-xs uppercase tracking-[0.18em] text-gold-400 mb-3">Coming soon</p>
          <h1 className="text-3xl sm:text-4xl font-bold text-gray-100 mb-4">
            CoachLenz is launching soon
          </h1>
          <p className="text-gray-400 mb-8">
            Game film for school basketball and football. Leave your name and email and
            you will be among the first to experience it. If you already have an account,
            you can still sign in.
          </p>
          <div className="card">
            <WaitlistForm source={source} />
          </div>
          <p className="text-center text-sm text-gray-400 mt-6">
            Already have an account? <Link href="/login" className="text-brand-400 hover:underline">Sign in</Link>
          </p>
        </div>
      </main>

      <footer className="border-t border-gray-800 px-8 py-4 text-center text-sm text-gray-500">
        Powered by <a href="https://cosbyaisolutions.com" className="text-brand-400 hover:underline" target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
      </footer>
    </div>
  )
}
