'use client'
import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { track, getSource } from '@/lib/funnel'
import api from '@/lib/api'

export default function FilmTimeCalculator() {
  const [games, setGames] = useState(10)
  const [hours, setHours] = useState(3)
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)

  // A visitor arriving on the tool is a top-of-funnel visitor, attributed by source.
  useEffect(() => { track('landing_view', { page: 'film-time-calculator' }) }, [])

  const seasonHours = useMemo(() => Math.max(0, Math.round(games * hours)), [games, hours])
  const workWeeks = useMemo(() => (seasonHours / 40).toFixed(1), [seasonHours])

  async function submitLead(e: React.FormEvent) {
    e.preventDefault()
    if (!email.trim()) return
    setSent(true)
    try { await api.post('/leads', { email: email.trim(), source: getSource() || 'film-time-calculator' }) } catch { /* noop */ }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      <header className="border-b border-gray-800 px-6 sm:px-8 py-4 flex items-center justify-between">
        <Link href="/" className="text-2xl font-bold text-brand-400">CoachLenz</Link>
        <Link href="/login" className="text-sm text-gray-400 hover:text-gray-100">Sign in</Link>
      </header>

      <main className="flex-1 px-6 sm:px-8 py-12">
        <div className="max-w-2xl mx-auto">
          <h1 className="text-3xl sm:text-4xl font-bold mb-3">How many hours does film breakdown cost you?</h1>
          <p className="text-gray-400 mb-8">
            Breaking down game film by hand quietly eats your season. Put in your numbers
            and see the real total, then decide what those hours are worth.
          </p>

          <div className="card space-y-6">
            <div>
              <label className="block text-sm text-gray-400 mb-2">Games you break down in a season</label>
              <input type="number" min={1} max={60} value={games}
                     onChange={(e) => setGames(Math.max(0, Number(e.target.value) || 0))}
                     className="input" />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-2">Hours it takes you to break down one game</label>
              <input type="number" min={0} max={40} step={0.5} value={hours}
                     onChange={(e) => setHours(Math.max(0, Number(e.target.value) || 0))}
                     className="input" />
            </div>

            <div className="border-t border-gray-800 pt-6 text-center">
              <div className="text-sm text-gray-400">That is</div>
              <div className="text-5xl font-bold text-brand-400 my-2">{seasonHours} hours</div>
              <div className="text-sm text-gray-400">a season on film breakdown, about {workWeeks} full work weeks.</div>
              <p className="text-gray-300 mt-4">
                CoachLenz does the breakdown for you and finds the tendencies, so those
                hours go back to coaching your team.
              </p>
            </div>
          </div>

          <div className="text-center mt-8">
            <Link href="/onboarding" onClick={() => track('cta_click', { cta: 'calculator' })}
                  className="btn-primary text-lg px-8 py-3 inline-block">
              Start your free trial
            </Link>
            <p className="text-sm text-gray-500 mt-3">14 days free. No credit card to start.</p>
          </div>

          <div className="card mt-10 text-center">
            {sent ? (
              <p className="text-gray-300">Thanks. We will be in touch.</p>
            ) : (
              <>
                <div className="font-medium text-gray-100 mb-1">Want this and coaching tips by email?</div>
                <p className="text-sm text-gray-400 mb-4">Leave your email. No spam, unsubscribe any time.</p>
                <form onSubmit={submitLead} className="flex flex-col sm:flex-row gap-3 justify-center">
                  <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                         placeholder="you@yourschool.org" className="input flex-1" />
                  <button type="submit" className="btn-secondary">Send it to me</button>
                </form>
              </>
            )}
          </div>
        </div>
      </main>

      <footer className="border-t border-gray-800 px-8 py-4 text-center text-sm text-gray-500">
        Powered by <a href="https://cosbyaisolutions.com" className="text-brand-400 hover:underline" target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
      </footer>
    </div>
  )
}
