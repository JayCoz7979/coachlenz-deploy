'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'
import { Share2, Copy, CheckCircle } from 'lucide-react'

export default function ReferralsPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [code, setCode] = useState<{ code: string; link: string } | null>(null)
  const [stats, setStats] = useState<any>(null)
  const [history, setHistory] = useState<any[]>([])
  const [copied, setCopied] = useState(false)

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => {
    if (!user) return
    Promise.all([
      api.get('/referrals/code'),
      api.get('/referrals/stats'),
      api.get('/referrals/history'),
    ]).then(([c, s, h]) => {
      setCode(c.data)
      setStats(s.data)
      setHistory(h.data)
    })
  }, [user])

  function copyLink() {
    if (!code) return
    navigator.clipboard.writeText(code.link)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-2xl font-bold mb-6 flex items-center gap-3"><Share2 className="text-brand-400" /> Referral Program</h2>
          {code && (
            <div className="card mb-6">
              <h3 className="font-semibold mb-3">Your Referral Link</h3>
              <div className="flex gap-3 items-center">
                <div className="flex-1 input font-mono text-sm">{code.link}</div>
                <button onClick={copyLink} className="btn-secondary flex items-center gap-2">
                  {copied ? <CheckCircle size={16} className="text-green-400" /> : <Copy size={16} />}
                  {copied ? 'Copied!' : 'Copy'}
                </button>
              </div>
              <p className="text-sm text-gray-400 mt-3">Share this link and earn commission when someone subscribes. Commission increases with each referral tier.</p>
            </div>
          )}
          {stats && (
            <div className="grid grid-cols-3 gap-4 mb-6">
              <div className="card text-center"><div className="text-2xl font-bold">{stats.total_referrals}</div><div className="text-sm text-gray-400">Total Referrals</div></div>
              <div className="card text-center"><div className="text-2xl font-bold">{stats.converted}</div><div className="text-sm text-gray-400">Converted</div></div>
              <div className="card text-center"><div className="text-2xl font-bold">{stats.current_tier_pct}%</div><div className="text-sm text-gray-400">Commission Rate</div></div>
            </div>
          )}
          <div className="card mb-4">
            <h3 className="font-semibold mb-3">Commission Tiers</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-gray-400">Tier 1 (0+ referrals)</span><span>10%</span></div>
              <div className="flex justify-between"><span className="text-gray-400">Tier 2 (3+ referrals)</span><span>15%</span></div>
              <div className="flex justify-between"><span className="text-gray-400">Tier 3 (10+ referrals)</span><span>20%</span></div>
            </div>
          </div>
          {history.length > 0 && (
            <div className="card">
              <h3 className="font-semibold mb-3">Referral History</h3>
              <div className="space-y-2">
                {history.map(r => (
                  <div key={r.id} className="flex justify-between text-sm">
                    <span className={`capitalize ${r.status === 'paid' ? 'text-green-400' : 'text-gray-400'}`}>{r.status}</span>
                    <span>{r.commission_pct}% commission</span>
                    {r.stripe_credit_cents && <span className="text-green-400">${(r.stripe_credit_cents / 100).toFixed(2)}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
