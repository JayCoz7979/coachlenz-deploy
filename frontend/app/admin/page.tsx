'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'
import { ShieldCheck, Users, AlertTriangle } from 'lucide-react'

export default function AdminPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [orgs, setOrgs] = useState<any[]>([])
  const [stats, setStats] = useState<any>(null)
  const [flags, setFlags] = useState<any[]>([])
  const [tab, setTab] = useState<'orgs'|'flags'|'stats'>('orgs')

  useEffect(() => { fetchMe() }, [])
  useEffect(() => {
    if (!isLoading && !user) { router.push('/login'); return }
    if (!isLoading && user && !user.organization.admin_level) router.push('/dashboard')
  }, [isLoading, user])
  useEffect(() => {
    if (!user?.organization.admin_level) return
    api.get('/admin/orgs').then(r => setOrgs(r.data))
    api.get('/admin/stats').then(r => setStats(r.data))
    api.get('/admin/risk-flags').then(r => setFlags(r.data))
  }, [user])

  async function toggleTenure(orgId: string, current: boolean) {
    await api.patch(`/admin/orgs/${orgId}`, { has_coach_tenure_access: !current })
    setOrgs(o => o.map(x => x.id === orgId ? { ...x, has_coach_tenure_access: !current } : x))
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-2xl font-bold mb-6 flex items-center gap-3"><ShieldCheck className="text-brand-400" /> Admin Panel</h2>
          <div className="flex gap-2 mb-6">
            {(['orgs','flags','stats'] as const).map(t => (
              <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === t ? 'bg-brand-500 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-100'}`}>{t === 'orgs' ? 'Organizations' : t === 'flags' ? 'Risk Flags' : 'Stats'}</button>
            ))}
          </div>
          {tab === 'stats' && stats && (
            <div className="grid grid-cols-4 gap-4">
              {Object.entries(stats).map(([k, v]) => (
                <div key={k} className="card text-center"><div className="text-2xl font-bold">{v as number}</div><div className="text-sm text-gray-400 capitalize">{k.replace(/_/g,' ')}</div></div>
              ))}
            </div>
          )}
          {tab === 'orgs' && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-gray-400 border-b border-gray-800"><th className="text-left pb-3">Name</th><th className="text-left pb-3">Tier</th><th className="text-left pb-3">Trial</th><th className="text-left pb-3">Tenure</th><th className="pb-3">Actions</th></tr></thead>
                <tbody className="divide-y divide-gray-800">
                  {orgs.map(o => (
                    <tr key={o.id}>
                      <td className="py-3">{o.name}</td>
                      <td className="py-3 capitalize">{o.subscription_tier}</td>
                      <td className="py-3">{o.is_trial ? 'Yes' : 'No'}</td>
                      <td className="py-3">{o.has_coach_tenure_access ? <span className="text-brand-400">On</span> : <span className="text-gray-500">Off</span>}</td>
                      <td className="py-3 text-center">
                        <button onClick={() => toggleTenure(o.id, o.has_coach_tenure_access)} className="text-xs btn-secondary py-1">{o.has_coach_tenure_access ? 'Disable Tenure' : 'Enable Tenure'}</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {tab === 'flags' && (
            <div className="space-y-3">
              {flags.map(f => (
                <div key={f.id} className="card flex items-center gap-4">
                  <AlertTriangle size={20} className={f.severity === 'critical' ? 'text-red-400' : f.severity === 'high' ? 'text-orange-400' : 'text-yellow-400'} />
                  <div>
                    <div className="font-medium">{f.flag_type}</div>
                    <div className="text-sm text-gray-400">{f.severity} · {new Date(f.created_at).toLocaleDateString()}</div>
                    <div className="text-xs text-gray-500 mt-1">{JSON.stringify(f.details)}</div>
                  </div>
                </div>
              ))}
              {flags.length === 0 && <div className="text-center text-gray-500 py-12">No unresolved risk flags.</div>}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
