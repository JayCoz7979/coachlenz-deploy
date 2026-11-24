'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import IntroOverlay from '@/components/IntroOverlay'
import { track } from '@/lib/funnel'
import api from '@/lib/api'
import logo from '../public/coachlenz-logo.png'
import WaitlistForm from '@/components/signup/WaitlistForm'
import { captureWaitlistAttribution } from '@/lib/waitlistAttribution'

const OBJECTIONS: { q: string; a: string }[] = [
  {
    q: "How much does it cost to try?",
    a: "Nothing to start. Your first 14 days are free and no credit card is required to begin.",
  },
  {
    q: "Will it work on the film I already have?",
    a: "Yes. Upload the game film you already record. CoachLenz breaks it down, you do not change how you film.",
  },
  {
    q: "Is my team's data safe?",
    a: "Your film and roster stay yours. CoachLenz is built to COPPA and FERPA standards for student-athlete data, and you can cancel any time.",
  },
  {
    q: "How long until I see something useful?",
    a: "Your first breakdown comes back in minutes, not the hours it takes by hand.",
  },
]

export default function HomeLanding({ signupsOpen = true }: { signupsOpen?: boolean }) {
  const [email, setEmail] = useState('')
  const [leadSent, setLeadSent] = useState(false)

  useEffect(() => { track('landing_view'); captureWaitlistAttribution() }, [])

  async function submitLead(e: React.FormEvent) {
    e.preventDefault()
    if (!email.trim()) return
    setLeadSent(true) // optimistic; capture is best-effort
    try { await api.post('/leads', { email: email.trim(), source: 'landing' }) } catch { /* noop */ }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      <IntroOverlay />
      <header className="border-b border-gray-800 px-6 sm:px-8 py-4 flex items-center justify-between">
        <img src={logo.src} alt="CoachLenz" style={{ height: 30, width: 'auto' }} />
        <nav className="flex items-center gap-5">
          {/* Secondary link only. The primary action stays the "Start your free trial" CTA below. */}
          <Link href="/book" className="text-sm text-gray-400 hover:text-gray-100">Book a Free Strategy Call</Link>
          <Link href="/login" className="text-sm text-gray-400 hover:text-gray-100">Sign in</Link>
        </nav>
      </header>

      <main className="flex-1">
        {/* Hero: lead with the pain, one primary action. */}
        <section className="flex flex-col items-center justify-center text-center px-6 sm:px-8 pt-20 pb-16">
          <div className="max-w-3xl">
            <h1 className="text-4xl sm:text-5xl font-bold mb-6 bg-gradient-to-r from-brand-400 to-purple-400 bg-clip-text text-transparent">
              You lose hours breaking down film and still miss what matters
            </h1>
            <p className="text-lg sm:text-xl text-gray-400 mb-10">
              CoachLenz watches your game film for you and finds the tendencies, so you
              walk into every game plan with the reads instead of the busywork.
            </p>
            {signupsOpen ? (
              <Link
                href="/onboarding"
                onClick={() => track('cta_click', { cta: 'hero' })}
                className="btn-primary text-lg px-8 py-3 inline-block"
              >
                Start your free trial
              </Link>
            ) : (
              <a href="#waitlist" className="btn-primary text-lg px-8 py-3 inline-block">
                Join the waitlist
              </a>
            )}
            <p className="text-sm text-gray-500 mt-4">
              {signupsOpen
                ? '14 days free. No credit card to start. Cancel any time.'
                : 'Coming soon. Join the list and you will be among the first to experience CoachLenz.'}
            </p>
          </div>
        </section>

        {/* Value against the real cost: your evenings. */}
        <section className="px-6 sm:px-8 pb-16">
          <div className="max-w-3xl mx-auto card text-center">
            <p className="text-lg text-gray-300">
              Breaking down one game by hand costs you a full evening. CoachLenz does it
              while you sleep, so the hours go back to coaching your team.
            </p>
          </div>
        </section>

        {/* Honest objection handling. No invented proof. */}
        <section className="px-6 sm:px-8 pb-16">
          <div className="max-w-4xl mx-auto">
            <h2 className="text-2xl font-bold text-center mb-8">Straight answers before you start</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {(signupsOpen ? OBJECTIONS : OBJECTIONS.map((o) => o.q.startsWith('How much')
                ? { ...o, a: 'Nothing yet. CoachLenz is launching soon. Join the list and you will be among the first.' }
                : o)).map((o) => (
                <div key={o.q} className="card">
                  <div className="font-medium text-gray-100 mb-1">{o.q}</div>
                  <div className="text-sm text-gray-400">{o.a}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* One more shot at the primary action. */}
        <section className="px-6 sm:px-8 pb-16 text-center">
          {signupsOpen ? (
            <Link
              href="/onboarding"
              onClick={() => track('cta_click', { cta: 'footer' })}
              className="btn-primary text-lg px-8 py-3 inline-block"
            >
              Start your free trial
            </Link>
          ) : (
            <a href="#waitlist" className="btn-primary text-lg px-8 py-3 inline-block">
              Join the waitlist
            </a>
          )}
        </section>

        {/* Email capture. While signups are closed this is the launch list, after the intro. */}
        <section id="waitlist" className="px-6 sm:px-8 pb-20">
          <div className="max-w-xl mx-auto card text-center">
            {signupsOpen ? (
              leadSent ? (
                <p className="text-gray-300">Thanks. We will keep you posted.</p>
              ) : (
                <>
                  <div className="font-medium text-gray-100 mb-1">Not ready to start?</div>
                  <p className="text-sm text-gray-400 mb-4">
                    Leave your email and we will send you updates as CoachLenz grows.
                  </p>
                  <form onSubmit={submitLead} className="flex flex-col sm:flex-row gap-3 justify-center">
                    <input
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@yourschool.org"
                      className="input flex-1"
                    />
                    <button type="submit" className="btn-secondary">Keep me posted</button>
                  </form>
                </>
              )
            ) : (
              <>
                <p className="text-xs uppercase tracking-[0.18em] text-gold-400 mb-2">Coming soon</p>
                <div className="font-medium text-gray-100 mb-1">Be among the first to experience CoachLenz</div>
                <p className="text-base text-gray-200 mb-4">
                  Game film for school basketball and football. Join the waitlist and we&apos;ll email you when CoachLenz opens, plus a few free coaching resources before then. Already have an account? You can still sign in.
                </p>
                <WaitlistForm source="app-home" id="home-waitlist" />
              </>
            )}
          </div>
        </section>
      </main>

      <footer className="border-t border-gray-800 px-8 py-4 text-center text-sm text-gray-500">
        Powered by <a href="https://cosbyaisolutions.com" className="text-brand-400 hover:underline" target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
      </footer>
    </div>
  )
}
