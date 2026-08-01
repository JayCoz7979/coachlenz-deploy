import Link from 'next/link'
import IntroOverlay from '@/components/IntroOverlay'
import {
  Upload, Cpu, FileText, Target, Users, Film, MessageSquare,
  ShieldCheck, Check, ArrowRight,
} from 'lucide-react'

// On-brand: Forest/Hunter green (#1a5c2a / #2d8c40) + gold (#C9A84C) on charcoal.
// Copy claims ONLY what the product actually does. Testimonials are placeholders,
// clearly marked, for real quotes to be swapped in.

const STEPS = [
  {
    icon: Upload,
    title: 'Upload or paste your film',
    body: 'Drop in a file, or paste a YouTube, Hudl, Vimeo, Google Drive, or Dropbox link. No Hudl account needed for public film.',
  },
  {
    icon: Cpu,
    title: 'The AI breaks down every play',
    body: 'Formations, personnel, run or pass, down and distance, even jersey numbers. Play by play, with a confidence score on every read.',
  },
  {
    icon: FileText,
    title: 'Get your scouting report',
    body: 'Opponent tendencies, self-scout, auto cut-ups, and a one-page summary you can hand your players before kickoff.',
  },
]

const FEATURES = [
  {
    icon: Target,
    title: 'Know what is coming',
    body: 'Ranked opponent tendencies by down and distance, formation, personnel, and run direction. See their go-to calls before they make them.',
  },
  {
    icon: Users,
    title: 'Scout yourself',
    body: 'Run the same engine on your own film and see exactly what you are giving away to the other sideline.',
  },
  {
    icon: Film,
    title: 'Reads the film for you',
    body: 'AI vision detects plays, formations, and jersey numbers from a single camera angle, so you are not tagging every snap by hand.',
  },
  {
    icon: MessageSquare,
    title: 'Ask the film questions',
    body: 'Chat with the AI about your report. Every answer is grounded in your actual plays, never invented.',
  },
  {
    icon: ShieldCheck,
    title: 'Honest by design',
    body: 'Every read carries a confidence score, and the AI never fabricates a play it could not see. No made-up tendencies to game-plan against.',
  },
  {
    icon: Cpu,
    title: 'Football and basketball',
    body: 'Purpose-built breakdowns for both sports, from run-pass tendencies to shot zones and turnover clusters.',
  },
]

const TIERS = [
  { name: 'Coach', price: '$199', unit: '/mo', desc: 'One coach, one program' },
  { name: 'Athletic Dept', price: '$399', unit: '/mo', desc: 'Multiple teams, one department', featured: true },
  { name: 'District', price: '$1,999', unit: '/mo', desc: 'Every school in the district' },
  { name: 'Enterprise', price: 'Custom', unit: '', desc: 'State associations and large orgs' },
]

// Swap these for real coach quotes before launch. Left obviously blank so a
// placeholder can never be mistaken for a real testimonial.
const TESTIMONIAL_PLACEHOLDERS = [
  { quote: 'Add a real coach quote here.', who: 'Coach name, Program' },
  { quote: 'Add a real coach quote here.', who: 'Coach name, Program' },
  { quote: 'Add a real coach quote here.', who: 'Coach name, Program' },
]

const GOLD = '#C9A84C'
const GREEN = '#2d8c40'

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col" style={{ background: '#1c1c1c', color: '#f8f6f0' }}>
      <IntroOverlay />

      {/* Header */}
      <header className="sticky top-0 z-40 flex items-center justify-between px-6 md:px-10 py-4"
        style={{ background: 'rgba(28,28,28,0.85)', backdropFilter: 'blur(8px)', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <div className="text-xl font-bold tracking-tight" style={{ color: GOLD }}>CoachLenz</div>
        <div className="flex items-center gap-3">
          <Link href="/login" className="btn-secondary" style={{ fontSize: 13 }}>Sign In</Link>
          <Link href="/onboarding" className="btn-primary" style={{ fontSize: 13 }}>Start Free Trial</Link>
        </div>
      </header>

      <main className="flex-1">
        {/* Hero */}
        <section className="relative px-6 md:px-10 pt-20 pb-16 text-center overflow-hidden">
          <div aria-hidden style={{
            position: 'absolute', top: -160, left: '50%', transform: 'translateX(-50%)',
            width: 720, height: 720, borderRadius: '50%', pointerEvents: 'none',
            background: 'radial-gradient(circle, rgba(45,140,64,0.18), transparent 60%)',
          }} />
          <div className="relative max-w-3xl mx-auto">
            <div className="inline-block mb-5 px-3 py-1 rounded-full text-xs font-semibold tracking-wide"
              style={{ color: GOLD, background: 'rgba(201,168,76,0.10)', border: '1px solid rgba(201,168,76,0.25)' }}>
              AI FILM ANALYST · FOOTBALL &amp; BASKETBALL
            </div>
            <h1 className="text-4xl md:text-6xl font-extrabold leading-tight mb-6">
              <span style={{ background: `linear-gradient(90deg, ${GREEN}, ${GOLD})`, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>
                See every tendency.
              </span>
              <br />Win every game.
            </h1>
            <p className="text-lg md:text-xl mb-9 mx-auto max-w-2xl" style={{ color: '#c8c3b6' }}>
              Upload your game film and CoachLenz breaks down every play: formations, personnel,
              down-and-distance tendencies, even jersey numbers. Walk into Friday night knowing
              exactly what is coming.
            </p>
            <div className="flex flex-wrap gap-3 justify-center">
              <Link href="/onboarding" className="btn-primary" style={{ fontSize: 16, padding: '12px 28px', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                Start Free Trial <ArrowRight size={17} />
              </Link>
              <a href="#how" className="btn-secondary" style={{ fontSize: 16, padding: '12px 28px' }}>See how it works</a>
            </div>
            <p className="mt-5 text-xs" style={{ color: '#7a7a6e' }}>
              14-day free trial · Cancel anytime · Works with the film you already have
            </p>
          </div>
        </section>

        {/* Founding-member band (true scarcity, matches billing) */}
        <section className="px-6 md:px-10">
          <div className="max-w-4xl mx-auto flex items-center gap-3 rounded-xl px-5 py-3 text-sm flex-wrap"
            style={{ background: 'rgba(201,168,76,0.08)', border: '1px solid rgba(201,168,76,0.22)' }}>
            <span style={{ fontSize: 16 }}>★</span>
            <span style={{ color: '#e2c06a', fontWeight: 700 }}>Founding Member pricing.</span>
            <span style={{ color: '#c8c3b6' }}>Lock in today&apos;s rates before public launch. Prices increase at 500 schools.</span>
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="px-6 md:px-10 py-20">
          <div className="max-w-5xl mx-auto">
            <div className="text-center mb-12">
              <div className="text-xs font-semibold tracking-wide mb-2" style={{ color: GREEN }}>HOW IT WORKS</div>
              <h2 className="text-3xl md:text-4xl font-bold">Film to game plan in three steps</h2>
            </div>
            <div className="grid md:grid-cols-3 gap-5">
              {STEPS.map((s, i) => (
                <div key={s.title} className="rounded-2xl p-6" style={{ background: '#2e2e2e', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <div className="flex items-center gap-3 mb-4">
                    <div className="flex items-center justify-center rounded-xl" style={{ width: 40, height: 40, background: 'rgba(45,140,64,0.15)', color: GREEN }}>
                      <s.icon size={20} />
                    </div>
                    <div className="text-sm font-bold" style={{ color: GOLD }}>Step {i + 1}</div>
                  </div>
                  <h3 className="text-lg font-bold mb-2">{s.title}</h3>
                  <p className="text-sm leading-relaxed" style={{ color: '#a8a396' }}>{s.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Features / benefits */}
        <section className="px-6 md:px-10 py-8">
          <div className="max-w-5xl mx-auto">
            <div className="text-center mb-12">
              <div className="text-xs font-semibold tracking-wide mb-2" style={{ color: GREEN }}>WHAT YOU GET</div>
              <h2 className="text-3xl md:text-4xl font-bold">Everything you would tag by hand, done for you</h2>
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {FEATURES.map((f) => (
                <div key={f.title} className="rounded-2xl p-6" style={{ background: '#2e2e2e', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <div className="flex items-center justify-center rounded-xl mb-4" style={{ width: 40, height: 40, background: 'rgba(201,168,76,0.12)', color: GOLD }}>
                    <f.icon size={20} />
                  </div>
                  <h3 className="text-base font-bold mb-2">{f.title}</h3>
                  <p className="text-sm leading-relaxed" style={{ color: '#a8a396' }}>{f.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Honest-by-design highlight (the real differentiator) */}
        <section className="px-6 md:px-10 py-20">
          <div className="max-w-4xl mx-auto rounded-3xl px-8 py-12 text-center"
            style={{ background: 'linear-gradient(160deg, rgba(26,92,42,0.18), #232323)', border: '1px solid rgba(45,140,64,0.35)' }}>
            <div className="flex items-center justify-center rounded-2xl mx-auto mb-5" style={{ width: 56, height: 56, background: 'rgba(45,140,64,0.2)', color: GREEN }}>
              <ShieldCheck size={28} />
            </div>
            <h2 className="text-2xl md:text-3xl font-bold mb-4">A scouting report you can actually trust</h2>
            <p className="text-base md:text-lg mx-auto max-w-2xl" style={{ color: '#c8c3b6' }}>
              CoachLenz flags its own confidence on every read and tells you what the camera could not see.
              It never invents a tendency to fill a gap. When it is not sure, it says so, so you never
              game-plan against a stat that is not real.
            </p>
          </div>
        </section>

        {/* Pricing */}
        <section id="pricing" className="px-6 md:px-10 py-12">
          <div className="max-w-5xl mx-auto">
            <div className="text-center mb-10">
              <div className="text-xs font-semibold tracking-wide mb-2" style={{ color: GREEN }}>PRICING</div>
              <h2 className="text-3xl md:text-4xl font-bold">Simple plans for every program</h2>
              <p className="mt-3 text-sm" style={{ color: '#a8a396' }}>Every plan includes all sports, a 14-day free trial, and cancel anytime.</p>
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {TIERS.map((t) => (
                <div key={t.name} className="rounded-2xl p-6 flex flex-col"
                  style={{ background: t.featured ? 'linear-gradient(160deg, rgba(45,80,22,0.12), #2e2e2e)' : '#2e2e2e',
                    border: `1px solid ${t.featured ? 'rgba(45,140,64,0.45)' : 'rgba(255,255,255,0.06)'}` }}>
                  {t.featured && <div className="text-[10px] font-bold uppercase tracking-wider mb-2" style={{ color: GOLD }}>Most Popular</div>}
                  <div className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: '#a8a396' }}>{t.name}</div>
                  <div className="mb-1"><span className="text-3xl font-extrabold">{t.price}</span><span className="text-sm" style={{ color: '#a8a396' }}>{t.unit}</span></div>
                  <p className="text-xs mb-5" style={{ color: '#a8a396' }}>{t.desc}</p>
                  {t.name === 'Enterprise' ? (
                    <a href="mailto:info@cosbyaisolutions.com?subject=CoachLenz%20Enterprise%20inquiry"
                      className="btn-secondary mt-auto text-center" style={{ fontSize: 13 }}>Contact Sales</a>
                  ) : (
                    <Link href="/onboarding" className={t.featured ? 'btn-primary mt-auto text-center' : 'btn-secondary mt-auto text-center'} style={{ fontSize: 13 }}>Start Free Trial</Link>
                  )}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Testimonials (placeholders — swap for real quotes) */}
        <section className="px-6 md:px-10 py-16">
          <div className="max-w-5xl mx-auto">
            <div className="text-center mb-10">
              <div className="text-xs font-semibold tracking-wide mb-2" style={{ color: GREEN }}>FROM THE SIDELINE</div>
              <h2 className="text-2xl md:text-3xl font-bold">What coaches are saying</h2>
            </div>
            <div className="grid md:grid-cols-3 gap-4">
              {TESTIMONIAL_PLACEHOLDERS.map((t, i) => (
                <div key={i} className="rounded-2xl p-6" style={{ background: '#2e2e2e', border: '1px dashed rgba(201,168,76,0.35)' }}>
                  <div className="mb-3" style={{ color: GOLD, fontSize: 22, lineHeight: 1 }}>&ldquo;</div>
                  <p className="text-sm italic mb-4" style={{ color: '#8f8b7f' }}>{t.quote}</p>
                  <div className="text-xs font-semibold" style={{ color: '#a8a396' }}>{t.who}</div>
                </div>
              ))}
            </div>
            <p className="text-center text-[11px] mt-4" style={{ color: '#6b675d' }}>Real coach testimonials coming soon.</p>
          </div>
        </section>

        {/* Final CTA */}
        <section className="px-6 md:px-10 py-20 text-center">
          <div className="max-w-2xl mx-auto">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">Break down film the smart way</h2>
            <p className="text-base mb-8" style={{ color: '#c8c3b6' }}>
              Start your free trial and get your first opponent report tonight.
            </p>
            <Link href="/onboarding" className="btn-primary" style={{ fontSize: 16, padding: '13px 32px', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              Start Free Trial <ArrowRight size={17} />
            </Link>
            <div className="flex items-center justify-center gap-5 mt-6 text-xs" style={{ color: '#7a7a6e' }}>
              <span className="inline-flex items-center gap-1"><Check size={13} style={{ color: GREEN }} /> All sports</span>
              <span className="inline-flex items-center gap-1"><Check size={13} style={{ color: GREEN }} /> 14-day trial</span>
              <span className="inline-flex items-center gap-1"><Check size={13} style={{ color: GREEN }} /> Cancel anytime</span>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="px-6 md:px-10 py-6 text-center text-sm" style={{ borderTop: '1px solid rgba(255,255,255,0.06)', color: '#7a7a6e' }}>
        <div className="flex items-center justify-center gap-4 mb-2 flex-wrap">
          <Link href="/terms" style={{ color: '#a8a396' }}>Terms</Link>
          <Link href="/privacy" style={{ color: '#a8a396' }}>Privacy</Link>
        </div>
        Powered by <a href="https://cosbyaisolutions.com" style={{ color: GOLD }} target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
      </footer>
    </div>
  )
}
