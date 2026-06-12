'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'

const TIERS = [
  {
    key: 'coach',
    name: 'Coach',
    price: '$199',
    annual: '$1,990/yr',
    desc: 'For individual coaches managing one program',
    features: ['Unlimited film uploads', 'AI tendency reports', 'All sports', 'URL import (YouTube, Hudl, Vimeo)', 'Clip & playlist builder'],
  },
  {
    key: 'athletic_dept',
    name: 'Athletic Dept',
    price: '$399',
    annual: '$3,990/yr',
    desc: 'For athletic departments with multiple teams',
    features: ['Everything in Coach', 'Multi-team management', 'Coach messaging threads', 'Customer surveys', 'Priority support'],
    featured: true,
  },
  {
    key: 'district',
    name: 'District',
    price: '$1,999',
    annual: '$19,990/yr',
    desc: 'District-wide deployment across all schools',
    features: ['Everything in Athletic Dept', 'District-wide access', 'Coach Tenure module', 'Teams of the Month', 'Dedicated account manager'],
  },
  {
    key: 'enterprise',
    name: 'Enterprise',
    price: '$14,999',
    annual: 'Annual billing available',
    desc: 'State associations & large organizations',
    features: ['Everything in District', 'Custom integrations', 'White-label option', 'SLA guarantee', 'On-site onboarding'],
  },
]

export default function BillingPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [loading, setLoading] = useState('')

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])

  async function checkout(tier: string) {
    setLoading(tier)
    try {
      const res = await api.post('/billing/checkout', { tier, success_url: `${window.location.origin}/dashboard`, cancel_url: `${window.location.origin}/settings/billing` })
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
              <div style={{ fontSize: 11, color: 'var(--text2)', marginTop: 2 }}>Lock in current rates before public launch. Prices increase at 500 schools.</div>
            </div>
            {!user.organization?.is_trial && (
              <button onClick={managePortal} disabled={loading === 'portal'} className="btn-gold">{loading === 'portal' ? 'Loading...' : 'Manage Billing'}</button>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 11, marginBottom: 20 }}>
            {TIERS.map(tier => {
              const isCurrent = user.organization?.subscription_tier === tier.key
              return (
                <div key={tier.key} style={{
                  background: isCurrent || (tier as any).featured ? 'linear-gradient(160deg,rgba(45,80,22,0.09),var(--bg2))' : 'var(--bg2)',
                  border: `1px solid ${isCurrent ? 'var(--green3)' : (tier as any).featured ? 'rgba(45,80,22,0.4)' : 'var(--border)'}`,
                  borderRadius: 14, padding: 18,
                }}>
                  {isCurrent && <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--green3)', fontFamily: 'var(--font-syne,sans-serif)', textTransform: 'uppercase' as const, letterSpacing: '0.08em', marginBottom: 6 }}>Current Plan</div>}
                  {(tier as any).featured && !isCurrent && <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--gold)', fontFamily: 'var(--font-syne,sans-serif)', textTransform: 'uppercase' as const, letterSpacing: '0.08em', marginBottom: 6 }}>Most Popular</div>}
                  <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text2)', textTransform: 'uppercase' as const, letterSpacing: '0.08em', marginBottom: 7, fontFamily: 'var(--font-syne,sans-serif)' }}>{tier.name}</div>
                  <div style={{ fontFamily: 'var(--font-syne,sans-serif)', fontSize: 26, fontWeight: 800, color: 'var(--text)', marginBottom: 2 }}>
                    {tier.price}<span style={{ fontSize: 12, fontWeight: 400, color: 'var(--text2)' }}>/mo</span>
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
                      display: 'block', width: '100%', textAlign: 'center', padding: 9, borderRadius: 8,
                      fontSize: 12, fontWeight: 700, cursor: loading ? 'not-allowed' : 'pointer',
                      fontFamily: 'var(--font-syne,sans-serif)',
                      background: (tier as any).featured ? 'var(--green)' : 'transparent',
                      color: (tier as any).featured ? '#fff' : 'var(--text2)',
                      border: (tier as any).featured ? 'none' : '1px solid var(--border2)',
                      opacity: loading ? 0.6 : 1,
                    }}>
                      {loading === tier.key ? 'Redirecting...' : 'Upgrade'}
                    </button>
                  )}
                </div>
              )
            })}
          </div>
          <p style={{ fontSize: 11, color: 'var(--text3)', textAlign: 'center' }}>
            All plans include a 14-day free trial. Cancel anytime.{' '}
            <a href="mailto:info@cosbyaisolutions.com" style={{ color: 'var(--green3)' }}>Contact us</a> for annual pricing.
          </p>
        </div>
      </main>
    </div>
  )
}
