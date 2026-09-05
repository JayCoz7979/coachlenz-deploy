'use client'
import { useEffect } from 'react'
import Link from 'next/link'
import { EXAMPLES, type ExampleKey } from '../../examples/reports'
import { track } from '@/lib/funnel'

// Public proof page. No auth. Shows the illustrative Live Game Logger sample report in
// an isolated iframe, with logged-out CTAs and source attribution, so a cold link
// actually opens and every visit is counted as a visitor.
export default function SampleView({ sport }: { sport: string }) {
  const ex = EXAMPLES[sport as ExampleKey]

  useEffect(() => {
    if (ex) track('landing_view', { page: `sample-${sport}` })
  }, [ex, sport])

  if (!ex) {
    return (
      <div className="min-h-screen bg-gray-950 flex flex-col items-center justify-center gap-4 text-gray-300">
        <div>That sample report was not found.</div>
        <Link href="/" className="text-brand-400 hover:underline">Back to CoachLenz</Link>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      <header className="border-b border-gray-800 px-6 sm:px-8 py-4 flex items-center justify-between">
        <Link href="/" className="text-2xl font-bold text-brand-400">CoachLenz</Link>
        <Link href="/login" className="text-sm text-gray-400 hover:text-gray-100">Sign in</Link>
      </header>

      <div className="px-6 sm:px-8 pt-8 pb-4 max-w-3xl mx-auto w-full">
        <div className="text-xs uppercase tracking-widest text-gray-500 mb-2">Sample breakdown, {ex.label}</div>
        <h1 className="text-2xl sm:text-3xl font-bold mb-2">This is a real CoachLenz game breakdown</h1>
        <p className="text-gray-400 text-sm">
          You chart the game from the sideline, CoachLenz turns it into a coordinator-style
          breakdown with tendencies and heat maps. Here is a full one so you can see it before
          you log a single play.
        </p>
      </div>

      {/* The sample report itself, isolated so its styles never touch the page. */}
      <div className="px-6 sm:px-8 w-full max-w-3xl mx-auto">
        <div className="rounded-xl overflow-hidden border border-gray-800">
          <iframe
            title={`${ex.label} sample report`}
            srcDoc={ex.html}
            className="w-full"
            style={{ height: '75vh', border: 0, background: '#1c1c1c' }}
          />
        </div>
      </div>

      {/* Logged-out CTA. The Live Game Logger is the free way in; AI film analysis is the upgrade. */}
      <section className="px-6 sm:px-8 py-12 text-center">
        <h2 className="text-xl font-bold mb-2">Want one for your team?</h2>
        <p className="text-gray-400 text-sm mb-5">Chart your next game and get a breakdown like this. Free to start, no credit card.</p>
        <Link
          href="/onboarding"
          onClick={() => track('cta_click', { cta: `sample-${sport}` })}
          className="btn-primary text-lg px-8 py-3 inline-block"
        >
          Start free
        </Link>
        <p className="text-sm text-gray-500 mt-4">
          Curious what film breakdown costs you in a season?{' '}
          <Link href="/tools/film-time-saved" className="text-brand-400 hover:underline">Run the 30-second calculator.</Link>
        </p>
      </section>

      <footer className="border-t border-gray-800 px-8 py-4 text-center text-xs text-gray-500">
        <p className="mb-1">Illustrative sample built from representative game data to show the report format. Your real reports come from the plays you log.</p>
        Powered by <a href="https://cosbyaisolutions.com" className="text-brand-400 hover:underline" target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
      </footer>
    </div>
  )
}
