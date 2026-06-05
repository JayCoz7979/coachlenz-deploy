'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'
import { CreditCard, CheckCircle } from 'lucide-react'

const TIERS = [
  { key: 'coach', name: 'Coach', price: '$49/mo', features: ['Unlimited film uploads', 'Tendency reports', 'All sports'] },
  { key: 'athletic_dept', name: 'Athletic Department', price: '$99/mo', features: ['Everything in Coach', 'Multi-team management', 'Customer surveys', 'Priority support'] },
  { key: 'district', name: 'District', price: '$249/mo', features: ['Everything in Athletic Dept', 'District-wide access', 'Coach Tenure module', 'Dedicated support'] },
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
      const res = await api.post('/billing/checkout', {
        tier,
        success_url: `${window.location.origin}/dashboard`,
        cancel_url: `${window.location.origin}/settings/billing`,
      })
      window.location.href = res.data.checkout_url
    } catch {
      setLoading('')
    }
  }

  async function managePortal() {
    setLoading('portal')
    try {
      const res = await api.post('/billing/portal')
      window.location.href = res.data.portal_url
    } catch {
      setLoading('')
    }
  }

  if (!user) return null

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-2xl font-bold mb-2">Billing & Plan</h2>
          <p className="text-gray-400 mb-8">Current plan: <span className="text-white font-medium capitalize">{user.organization.subscription_tier}</span></p>
          {!user.organization.is_trial && (
            <button onClick={managePortal} disabled={loading === 'portal'} className="btn-secondary mb-8 flex items-center gap-2">
              <CreditCard size={16} /> {loading === 'portal' ? 'Loading...' : 'Manage Billing Portal'}
            </button>
          )}
          <div className="grid md:grid-cols-3 gap-6">
            {TIERS.map(tier => {
              const isCurrent = user.organization.subscription_tier === tier.key
              return (
                <div key={tier.key} className={`card border-2 ${isCurrent ? 'border-brand-500' : 'border-gray-800'}`}>
                  {isCurrent && <div className="text-xs text-brand-400 font-medium mb-2">CURRENT PLAN</div>}
                  <h3 className="text-lg font-bold">{tier.name}</h3>
                  <div className="text-2xl font-bold text-brand-400 my-2">{tier.price}</div>
                  <ul className="space-y-2 mb-6">
                    {tier.features.map(f => (
                      <li key={f} className="flex items-center gap-2 text-sm text-gray-300">
                        <CheckCircle size={14} className="text-green-400 flex-shrink-0" />{f}
                      </li>
                    ))}
                  </ul>
                  {!isCurrent && (
                    <button onClick={() => checkout(tier.key)} disabled={!!loading} className="btn-primary w-full">
                      {loading === tier.key ? 'Redirecting...' : 'Upgrade'}
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </main>
    </div>
  )
}
