'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'

// Access-only subscription tiers. Credits are separate (bought in bundles below).
const TIERS = [
  {
    key: 'coach',
    name: 'Coach',
    price: '$9.99',
    annual: '$99/yr (2 months free)',
    desc: 'One head coach, add assistant coaches',
    features: ['Head coach + assistant seats', 'Assistants: view-only or analysis access', 'Your own credit wallet', 'Free Live Game Logger', 'Buy analysis credits as you need them'],
  },
  {
    key: 'athletic_dept',
    name: 'Athletic Dept',
    price: '$29.99',
    annual: '$299/yr (2 months free)',
    desc: 'The whole school, all sports, one subscription',
    features: ['All sports, unlimited coach seats', 'Shared school-wide credit pool', 'Per-sport and per-coach credit caps', 'AD dashboard controls', 'Free Live Game Logger'],
    featured: true,
  },
]

const SALES_EMAIL = 'info@cosbyaisolutions.com'

export default function BillingPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [loading, setLoading] = useState('')
  const [credits, setCredits] = useState<any>(null)

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => { if (user) api.get('/credits').then(r => setCredits(r.data)).catch(() => {}) }, [user])

  async function checkout(tier: string) {
    setLoading(tier)
    try {
      const res = await api.post('/billing/checkout', { tier, success_url: `${window.location.origin}/dashboard`, cancel_url: `${window.location.origin}/settings/billing` })
      window.location.href = res.data.checkout_url
    } catch { setLoading('') }
  }

  async function buyBundle(bundle: string) {
    setLoading(bundle)
    try {
      const res = await api.post('/credits/checkout', { bundle, success_url: `${window.location.origin}/settings/billing`, cancel_url: `${window.location.origin}/settings/billing` })
      window.location.href = res.data.checkout_url
    } catch { setLoading('') }
  }

  async function managePortal() {
    setLoading('portal')
    try {
      const res = await api.post('/billing/portal')
      window.location.href = res.data.portal_url
    } catch { setLoading('') }
  }

  const money = (cents: number) => `$${(cents / 100).toLocaleString()}`

  if (!user) return null

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main style={{ flex: 1, overflowY: 'auto', padding: 32 }}>
        <div style={{ maxWidth: 920, margin: '0 auto' }}>
          <div style={{ marginBottom: 24 }}>
            <h2 style={{ fontFamily: 'var(--font-syne,sans-serif)', fontSize: 22, fontWeight: 800, color: 'var(--text)', marginBottom: 4 }}>Billing & Plan</h2>
            <p style={{ fontSize: 13, color: 'var(--text2)' }}>
              Current plan: <span style={{ color: 'var(--text)', fontWeight: 600 }}>{TIERS.find(t => t.key === user.organization?.subscription_tier)?.name || user.organization?.subscription_tier}</span>
            </p>
          </div>

          <div style={{ background: 'var(--goldl)', border: '1px solid rgba(201,168,76,0.28)', borderRadius: 14, padding: '14px 18px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' as const }}>
            <span style={{ fontSize: 18 }}>★</span>
            <div style={{ flex: 1 }}>
              <div style={{ fontFamily: 'var(--font-syne,sans-serif)', fontSize: 13, fontWeight: 700, color: 'var(--gold2)' }}>Founding Member Pricing</div>
              <div style={{ fontSize: 11, color: 'var(--text2)', marginTop: 2 }}>Lock in current rates before public launch.</div>
            </div>
            {!user.organization?.is_trial && (
              <button onClick={managePortal} disabled={loading === 'portal'} className="btn-gold">{loading === 'portal' ? 'Loading...' : 'Manage Billing'}</button>
            )}
          </div>

          {/* Subscription tiers (access) */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
            {TIERS.map(tier => {
              const isCurrent = user.organization?.subscription_tier === tier.key
              return (
                <div key={tier.key} style={{
                  background: isCurrent || (tier as any).featured ? 'linear-gradient(160deg,rgba(45,80,22,0.09),var(--bg2))' : 'var(--bg2)',
                  border: `1px solid ${isCurrent ? 'var(--green3)' : (tier as any).featured ? 'rgba(45,80,22,0.4)' : 'var(--border)'}`,
                  borderRadius: 14, padding: 20,
                }}>
                  {isCurrent && <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--green3)', fontFamily: 'var(--font-syne,sans-serif)', textTransform: 'uppercase' as const, letterSpacing: '0.08em', marginBottom: 6 }}>Current Plan</div>}
                  {(tier as any).featured && !isCurrent && <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--gold)', fontFamily: 'var(--font-syne,sans-serif)', textTransform: 'uppercase' as const, letterSpacing: '0.08em', marginBottom: 6 }}>Scales your whole school</div>}
                  <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text2)', textTransform: 'uppercase' as const, letterSpacing: '0.08em', marginBottom: 7, fontFamily: 'var(--font-syne,sans-serif)' }}>{tier.name}</div>
                  <div style={{ fontFamily: 'var(--font-syne,sans-serif)', fontSize: 30, fontWeight: 800, color: 'var(--text)', marginBottom: 2 }}>
                    {tier.price}<span style={{ fontSize: 13, fontWeight: 400, color: 'var(--text2)' }}>/mo</span>
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--green3)', marginBottom: 3, fontFamily: 'var(--font-dm-mono,monospace)' }}>{tier.annual}</div>
                  <div style={{ fontSize: 11, color: 'var(--text2)', marginBottom: 12, paddingBottom: 12, borderBottom: '1px solid var(--border)' }}>{tier.desc}</div>
                  <ul style={{ listStyle: 'none', marginBottom: 16 }}>
                    {tier.features.map(f => (
                      <li key={f} style={{ fontSize: 11, color: 'var(--text2)', padding: '2px 0', display: 'flex', gap: 6 }}>
                        <span style={{ color: 'var(--green4)', fontWeight: 700, flexShrink: 0 }}>✓</span>{f}
                      </li>
                    ))}
                  </ul>
                  {isCurrent ? (
                    <div style={{ textAlign: 'center', padding: 9, borderRadius: 8, fontSize: 12, fontWeight: 700, fontFamily: 'var(--font-syne,sans-serif)', background: 'rgba(45,80,22,0.15)', color: 'var(--green3)', border: '1px solid rgba(45,80,22,0.3)' }}>Active</div>
                  ) : (
                    <button onClick={() => checkout(tier.key)} disabled={!!loading} style={{
                      display: 'block', width: '100%', textAlign: 'center', padding: 10, borderRadius: 8,
                      fontSize: 13, fontWeight: 700, cursor: loading ? 'not-allowed' : 'pointer',
                      fontFamily: 'var(--font-syne,sans-serif)',
                      background: (tier as any).featured ? 'var(--green)' : 'transparent',
                      color: (tier as any).featured ? '#fff' : 'var(--text2)',
                      border: (tier as any).featured ? 'none' : '1px solid var(--border2)',
                      opacity: loading ? 0.6 : 1,
                    }}>
                      {loading === tier.key ? 'Redirecting...' : 'Choose plan'}
                    </button>
                  )}
                </div>
              )
            })}
          </div>
          <p style={{ fontSize: 11, color: 'var(--text3)', textAlign: 'center', marginBottom: 22 }}>
            Running a conference or district? <a href={`mailto:${SALES_EMAIL}?subject=${encodeURIComponent('CoachLenz conference/district inquiry')}`} style={{ color: 'var(--green3)' }}>Contact us</a>.
          </p>

          {/* Credit wallet + bundles */}
          {credits?.on_system && (
            <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 14, padding: '16px 18px', marginBottom: 12 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' as const, marginBottom: 4 }}>
                <div style={{ fontFamily: 'var(--font-syne,sans-serif)', fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>Analysis credits</div>
                <div style={{ fontFamily: 'var(--font-syne,sans-serif)', fontSize: 26, fontWeight: 800, color: 'var(--green3)' }}>{credits.balance}<span style={{ fontSize: 12, fontWeight: 400, color: 'var(--text2)' }}> in your wallet</span></div>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text2)', marginBottom: 14 }}>
                Credits never expire while your subscription is active. Standard football is {credits.analysis_costs?.standard?.football ?? 29} credits, deep + grade is {credits.analysis_costs?.deep_grade?.football ?? 55}, a re-analysis is {credits.analysis_costs?.reanalysis ?? 9}. The Live Game Logger is always free.
              </div>
              <div style={{ display: 'flex', gap: 9, flexWrap: 'wrap' as const }}>
                {(credits.bundles || []).map((b: any) => (
                  <button key={b.id} onClick={() => buyBundle(b.id)} disabled={!!loading} style={{
                    padding: '10px 14px', borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: loading ? 'not-allowed' : 'pointer',
                    fontFamily: 'var(--font-syne,sans-serif)', background: 'transparent', color: 'var(--text)', border: '1px solid var(--border2)', opacity: loading ? 0.6 : 1,
                    textAlign: 'center' as const,
                  }}>
                    {loading === b.id ? 'Redirecting...' : (
                      <span>{b.credits} credits · {money(b.price_cents)}<br /><span style={{ fontSize: 10, fontWeight: 400, color: 'var(--text3)' }}>${b.per_credit}/credit</span></span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}

          <p style={{ fontSize: 11, color: 'var(--text3)', textAlign: 'center' }}>
            Credits are purchased separately, never expire while your account is active, and are forfeited on cancellation. The Live Game Logger is always free.{' '}
            <a href={`mailto:${SALES_EMAIL}`} style={{ color: 'var(--green3)' }}>Contact us</a> for annual billing.
          </p>
        </div>
      </main>
    </div>
  )
}
