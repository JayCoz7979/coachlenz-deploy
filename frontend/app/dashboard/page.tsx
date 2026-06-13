'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'
import { Film, FileText, Users, TrendingUp, Link2, Upload } from 'lucide-react'
import Link from 'next/link'

export default function DashboardPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [stats, setStats] = useState({ games: 0, reports: 0, teams: 0 })

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => {
    if (!user) return
    Promise.all([
      api.get('/games').catch(() => ({ data: [] })),
      api.get('/reports').catch(() => ({ data: [] })),
      api.get('/teams').catch(() => ({ data: [] })),
    ]).then(([g, r, t]) => setStats({ games: g.data.length, reports: r.data.length, teams: t.data.length }))
  }, [user])

  if (isLoading || !user) return null

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-5xl mx-auto">
          <div className="mb-8">
            <h2 className="text-2xl font-bold">Welcome back, {user.name.split(' ')[0]}</h2>
            <p className="text-gray-400 mt-1">{user.organization.name}</p>
            {user.organization.is_trial && (
              <div className="mt-3 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-sm text-yellow-400">
                Trial active — {user.organization.trial_days_remaining} days remaining. <Link href="/settings/billing" className="underline">Upgrade now</Link>
              </div>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            <div className="card flex items-center gap-4">
              <Film className="text-brand-400" size={32} />
              <div>
                <div className="text-2xl font-bold">{stats.games}</div>
                <div className="text-sm text-gray-400">Games</div>
              </div>
            </div>
            <div className="card flex items-center gap-4">
              <FileText className="text-brand-400" size={32} />
              <div>
                <div className="text-2xl font-bold">{stats.reports}</div>
                <div className="text-sm text-gray-400">Reports</div>
              </div>
            </div>
            <div className="card flex items-center gap-4">
              <Users className="text-brand-400" size={32} />
              <div>
                <div className="text-2xl font-bold">{stats.teams}</div>
                <div className="text-sm text-gray-400">Teams</div>
              </div>
            </div>
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="card">
              <h3 className="font-semibold mb-4 flex items-center gap-2"><TrendingUp size={18} className="text-brand-400" /> Add Film</h3>
              <div className="space-y-2">
                <Link
                  href="/games/upload?tab=url"
                  className="btn-primary w-full flex items-center justify-center gap-2"
                  style={{ background: '#C9A84C', color: '#1c1c1c' }}
                >
                  <Link2 size={16} /> Import from YouTube / Hudl / Vimeo
                </Link>
                <Link
                  href="/games/upload"
                  className="btn-secondary w-full flex items-center justify-center gap-2"
                >
                  <Upload size={16} /> Upload a File
                </Link>
                <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', margin: '8px 0' }} />
                <Link href="/reports" className="btn-secondary w-full block text-center">View Reports</Link>
                <Link href="/teams" className="btn-secondary w-full block text-center">Manage Teams</Link>
              </div>
            </div>
            <div className="card">
              <h3 className="font-semibold mb-4">Your Plan</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-gray-400">Tier</span><span className="capitalize">{user.organization.subscription_tier}</span></div>
                <div className="flex justify-between"><span className="text-gray-400">Status</span><span>{user.organization.is_trial ? 'Trial' : 'Active'}</span></div>
                {user.organization.has_coach_tenure_access && <div className="flex justify-between"><span className="text-gray-400">Coach Tenure</span><span className="text-brand-400">Enabled</span></div>}
              </div>
              <Link href="/settings/billing" className="btn-secondary w-full block text-center mt-4 text-sm">Manage Billing</Link>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
