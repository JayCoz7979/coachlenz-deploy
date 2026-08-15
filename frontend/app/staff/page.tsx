'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth, usePermission } from '@/lib/auth'
import api from '@/lib/api'
import { UserPlus, UserX, UserCheck } from 'lucide-react'
import ConfirmModal from '@/components/ConfirmModal'

interface Staff { id: string; name: string; email: string; role: string; is_active: boolean }

// Roles a head coach can assign (friendly labels), matching backend STAFF_ASSIGNABLE_ROLES.
const ASSIGNABLE_ROLES: { value: string; label: string }[] = [
  { value: 'head_coach', label: 'Head Coach' },
  { value: 'coordinator_offense', label: 'Offensive Coordinator' },
  { value: 'coordinator_defense', label: 'Defensive Coordinator' },
  { value: 'coordinator_special_teams', label: 'Special Teams Coordinator' },
  { value: 'position_coach', label: 'Position Coach' },
  { value: 'analyst', label: 'Analyst' },
  { value: 'athletic_trainer', label: 'Athletic Trainer (view only)' },
]
const ROLE_LABEL: Record<string, string> = Object.fromEntries(ASSIGNABLE_ROLES.map(r => [r.value, r.label]))

export default function StaffPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const canInvite = usePermission('can_invite_staff')

  const [staff, setStaff] = useState<Staff[]>([])
  const [confirmReq, setConfirmReq] = useState<{ title: string; message: string; confirmLabel?: string; danger?: boolean; onConfirm: () => void } | null>(null)
  const [form, setForm] = useState({ email: '', name: '', role: 'analyst' })
  const [showForm, setShowForm] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  // "Special Teams Coordinator" is a football-only role — hide it for basketball.
  const [isBball, setIsBball] = useState(false)
  const assignableRoles = ASSIGNABLE_ROLES.filter(r => !isBball || r.value !== 'coordinator_special_teams')

  useEffect(() => { fetchMe() }, [])
  useEffect(() => {
    if (!isLoading && !user) { router.push('/login'); return }
    if (!isLoading && user && !user.permissions?.includes('can_invite_staff')) router.push('/dashboard')
  }, [isLoading, user])
  useEffect(() => { if (canInvite) load() }, [canInvite])
  useEffect(() => {
    if (user) api.get('/onboarding/status').then(r => setIsBball((r.data?.chosen_sports || [])[0] === 'basketball')).catch(() => {})
  }, [user])

  function flash(setter: (s: string) => void, t: string) { setter(t); setTimeout(() => setter(''), 3500) }
  async function load() { try { const r = await api.get('/staff'); setStaff(r.data) } catch {} }

  async function invite(e: React.FormEvent) {
    e.preventDefault(); setErr('')
    try {
      await api.post('/staff/invite', form)
      setForm({ email: '', name: '', role: 'analyst' }); setShowForm(false); await load()
      flash(setMsg, `Invite sent to ${form.email}.`)
    } catch (e: any) { flash(setErr, e.response?.data?.detail || 'Could not send invite.') }
  }
  async function changeRole(id: string, role: string) {
    try { await api.post(`/staff/${id}/role`, { role }); await load() }
    catch (e: any) { flash(setErr, e.response?.data?.detail || 'Could not change role.') }
  }
  function revoke(id: string) {
    setConfirmReq({
      title: 'Revoke access?',
      message: 'Revoke this staff member’s access? Their sessions end immediately.',
      confirmLabel: 'Revoke access',
      onConfirm: async () => {
        setConfirmReq(null)
        try { await api.post(`/staff/${id}/revoke`); await load() } catch (e: any) { flash(setErr, e.response?.data?.detail || 'Could not revoke.') }
      },
    })
  }
  async function reactivate(id: string) {
    try { await api.post(`/staff/${id}/reactivate`); await load() } catch {}
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-2xl font-bold">Staff</h2>
              <p className="text-gray-400 text-sm">Invite coaches to your program, set their role, and manage access.</p>
            </div>
            <button onClick={() => setShowForm(s => !s)} className="btn-primary flex items-center gap-2"><UserPlus size={16} /> Invite Coach</button>
          </div>

          {msg && <div className="mb-4 text-sm bg-brand-500/10 border border-brand-500/30 text-brand-400 rounded p-2">{msg}</div>}
          {err && <div className="mb-4 text-sm bg-red-400/10 border border-red-400/30 text-red-400 rounded p-2">{err}</div>}

          {showForm && (
            <form onSubmit={invite} className="card mb-6 space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div><label className="label">Name</label><input className="input" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required /></div>
                <div><label className="label">Email</label><input type="email" className="input" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} required /></div>
                <div><label className="label">Role</label>
                  <select className="input" value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}>
                    {assignableRoles.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                  </select>
                </div>
              </div>
              <div className="flex gap-2"><button type="submit" className="btn-primary">Send Invite</button><button type="button" onClick={() => setShowForm(false)} className="btn-secondary">Cancel</button></div>
            </form>
          )}

          <div className="card">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-gray-400 border-b border-gray-800">
                <th className="py-2">Name</th><th className="py-2">Email</th><th className="py-2">Role</th><th className="py-2">Status</th><th></th>
              </tr></thead>
              <tbody>
                {staff.map(s => {
                  const isOwner = s.role === 'owner'
                  const isSelf = s.id === user?.id
                  return (
                    <tr key={s.id} className="border-b border-gray-800/60">
                      <td className="py-2">{s.name}</td>
                      <td className="py-2 text-gray-400">{s.email}</td>
                      <td className="py-2">
                        {isOwner ? <span className="text-gray-300">Owner</span> : (
                          <select className="input py-1 text-xs" value={s.role} onChange={e => changeRole(s.id, e.target.value)}>
                            {!ROLE_LABEL[s.role] && <option value={s.role}>{s.role}</option>}
                            {assignableRoles.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                          </select>
                        )}
                      </td>
                      <td className="py-2">{s.is_active ? <span className="text-brand-400">Active</span> : <span className="text-gray-500">Revoked</span>}</td>
                      <td className="py-2 text-right">
                        {!isOwner && !isSelf && (s.is_active
                          ? <button onClick={() => revoke(s.id)} className="text-gray-500 hover:text-red-400 flex items-center gap-1 ml-auto"><UserX size={15} /> Revoke</button>
                          : <button onClick={() => reactivate(s.id)} className="text-gray-500 hover:text-brand-400 flex items-center gap-1 ml-auto"><UserCheck size={15} /> Reactivate</button>)}
                      </td>
                    </tr>
                  )
                })}
                {staff.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-gray-500">Just you so far. Invite a coach to get started.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
        <ConfirmModal
          open={!!confirmReq}
          title={confirmReq?.title || ''}
          message={confirmReq?.message || ''}
          confirmLabel={confirmReq?.confirmLabel}
          danger={confirmReq?.danger ?? true}
          onConfirm={() => confirmReq?.onConfirm()}
          onCancel={() => setConfirmReq(null)}
        />
      </main>
    </div>
  )
}
