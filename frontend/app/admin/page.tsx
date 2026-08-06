'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'
import { ShieldCheck, Users, AlertTriangle, Trash2, ToggleLeft, ToggleRight } from 'lucide-react'
import ConfirmModal from '@/components/ConfirmModal'

export default function AdminPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [orgs, setOrgs] = useState<any[]>([])
  const [stats, setStats] = useState<any>(null)
  const [flags, setFlags] = useState<any[]>([])
  const [features, setFeatures] = useState<any[]>([])
  const [tab, setTab] = useState<'orgs'|'features'|'flags'|'stats'>('orgs')
  const [orgToDelete, setOrgToDelete] = useState<{id: string, name: string} | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [err, setErr] = useState('')

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
    api.get('/admin/feature-flags').then(r => setFeatures(r.data.flags || [])).catch(() => {})
  }, [user])

  async function toggleFeature(key: string, enabled: boolean) {
    try {
      await api.put(`/admin/feature-flags/${key}`, { enabled: !enabled })
      setFeatures(fs => fs.map(f => f.key === key ? { ...f, enabled: !enabled, source: 'override' } : f))
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Could not toggle feature.')
    }
  }

  async function toggleTenure(orgId: string, current: boolean) {
    await api.patch(`/admin/orgs/${orgId}`, { has_coach_tenure_access: !current })
    setOrgs(o => o.map(x => x.id === orgId ? { ...x, has_coach_tenure_access: !current } : x))
  }

  async function deleteOrg() {
    if (!orgToDelete) return
    setErr(''); setDeleting(true)
    try {
      await api.delete(`/admin/orgs/${orgToDelete.id}`)
      setOrgs(o => o.filter(x => x.id !== orgToDelete.id))
      setOrgToDelete(null)
    } catch (e: any) {
      setErr(e.response?.data?.detail || `Could not delete "${orgToDelete.name}".`)
      setOrgToDelete(null)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-2xl font-bold mb-6 flex items-center gap-3"><ShieldCheck className="text-brand-400" /> Admin Panel</h2>
          {err && <div className="mb-4 text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-2">{err}</div>}
          <div className="flex gap-2 mb-6">
            {(['orgs','features','flags','stats'] as const).map(t => (
              <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === t ? 'bg-brand-500 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-100'}`}>{t === 'orgs' ? 'Organizations' : t === 'features' ? 'Feature Toggles' : t === 'flags' ? 'Risk Flags' : 'Stats'}</button>
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
                        {o.id !== user?.organization?.id && (
                          <button onClick={() => { setErr(''); setOrgToDelete({ id: o.id, name: o.name }) }} title="Delete organization and all its data" className="text-xs text-red-400 hover:text-red-300 ml-3 inline-flex items-center gap-1"><Trash2 size={13} /> Delete</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {tab === 'features' && (
            <div className="space-y-6">
              <p className="text-sm text-gray-400">Toggle features on or off live. Changes take effect within ~20 seconds, no redeploy. A toggle overrides the shipped default; features you never touch stay on their default.</p>
              {Array.from(new Set(features.map(f => f.category))).map(cat => (
                <div key={cat}>
                  <h3 className="text-xs uppercase tracking-wide text-gray-500 mb-2">{cat}</h3>
                  <div className="space-y-2">
                    {features.filter(f => f.category === cat).map(f => (
                      <div key={f.key} className="card flex items-start gap-4">
                        <button onClick={() => toggleFeature(f.key, f.enabled)} title={f.enabled ? 'Turn off' : 'Turn on'} className="mt-0.5 shrink-0">
                          {f.enabled ? <ToggleRight size={34} className="text-brand-400" /> : <ToggleLeft size={34} className="text-gray-600" />}
                        </button>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{f.label}</span>
                            <span className={`text-[10px] px-1.5 py-0.5 rounded ${f.enabled ? 'bg-brand-500/15 text-brand-400' : 'bg-gray-700 text-gray-400'}`}>{f.enabled ? 'ON' : 'OFF'}</span>
                            {f.source === 'override' && <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-700 text-gray-400" title="Manually overriding the shipped default">override</span>}
                          </div>
                          <div className="text-sm text-gray-400 mt-0.5">{f.description}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              {features.length === 0 && <div className="text-center text-gray-500 py-12">No feature toggles available.</div>}
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
        <ConfirmModal
          open={!!orgToDelete}
          title="Delete organization?"
          message={orgToDelete ? `Permanently delete "${orgToDelete.name}" and ALL of its data (users, film, reports, roster). This cannot be undone.` : ''}
          confirmLabel="Delete organization"
          busy={deleting}
          onConfirm={deleteOrg}
          onCancel={() => setOrgToDelete(null)}
        />
      </main>
    </div>
  )
}
