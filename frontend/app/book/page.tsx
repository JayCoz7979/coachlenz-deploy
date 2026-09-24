'use client'
import { useEffect } from 'react'
import Link from 'next/link'
import logo from '../../public/coachlenz-logo.png'

export default function Book() {
  // Cal.com inline embed. Run the exact loader + init AFTER mount so the
  // #my-cal-inline-strategy container already exists in the DOM. Reproduces the
  // provided embed script verbatim (no theme/color options added).
  useEffect(() => {
    const w = window as any
    ;(function (C: any, A: string, L: string) {
      const p = function (a: any, ar: any) { a.q.push(ar) }
      const d = C.document
      C.Cal = C.Cal || function () {
        const cal = C.Cal; const ar = arguments as any
        if (!cal.loaded) { cal.ns = {}; cal.q = cal.q || []; d.head.appendChild(d.createElement('script')).src = A; cal.loaded = true }
        if (ar[0] === L) {
          const api: any = function () { p(api, arguments) }
          const namespace = ar[1]; api.q = api.q || []
          if (typeof namespace === 'string') { cal.ns[namespace] = cal.ns[namespace] || api; p(cal.ns[namespace], ar); p(cal, ['initNamespace', namespace]) }
          else p(cal, ar)
          return
        }
        p(cal, ar)
      }
    })(w, 'https://app.cal.com/embed/embed.js', 'init')

    w.Cal('init', 'strategy', { origin: 'https://app.cal.com' })
    w.Cal.config = w.Cal.config || {}
    w.Cal.config.forwardQueryParams = true
    w.Cal.ns.strategy('inline', {
      elementOrSelector: '#my-cal-inline-strategy',
      config: { layout: 'month_view', useSlotsViewOnSmallScreen: 'true' },
      calLink: 'jasoncosby/strategy',
    })
    w.Cal.ns.strategy('ui', { hideEventTypeDetails: false, layout: 'month_view' })
  }, [])

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      <header className="border-b border-gray-800 px-6 sm:px-8 py-4 flex items-center justify-between">
        <Link href="/"><img src={logo.src} alt="CoachLenz" style={{ height: 30, width: 'auto' }} /></Link>
        <nav className="flex items-center gap-5">
          <Link href="/book" className="text-sm text-gray-400 hover:text-gray-100">Book a Free Strategy Call</Link>
          <Link href="/login" className="text-sm text-gray-400 hover:text-gray-100">Sign in</Link>
        </nav>
      </header>

      <main className="flex-1">
        <section className="px-6 sm:px-8 pt-16 pb-8 text-center">
          <div className="max-w-3xl mx-auto">
            <h1 className="text-3xl sm:text-4xl font-bold mb-4 text-gray-100">
              Book a Free Strategy Call
            </h1>
            <p className="text-lg text-gray-400">
              A 30-minute call with founder Jason Cosby to talk through your goals and where
              AI can move your business forward.
            </p>
          </div>
        </section>

        {/* Cal.com inline scheduler: full width, at least 700px tall on desktop, responsive. */}
        <section className="px-6 sm:px-8 pb-16">
          <div style={{ width: '100%', minHeight: 700 }}>
            <div style={{ width: '100%', height: '100%', overflow: 'scroll' }} id="my-cal-inline-strategy"></div>
          </div>
        </section>
      </main>

      <footer className="border-t border-gray-800 px-8 py-4 text-center text-sm text-gray-500">
        Powered by <a href="https://cosbyaisolutions.com" className="text-brand-400 hover:underline" target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
      </footer>
    </div>
  )
}
