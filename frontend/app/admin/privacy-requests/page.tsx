'use client'
import { useEffect, useState } from 'react'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { useRouter } from 'next/navigation'

type Req = {
  id: string; request_type: string; status: string
  requester_name: string; requester_email: string; relationship: string
  student_name: string; school_or_org?: string; student_details?: string; details?: string
  resolution_note?: string; certificate_id?: string; organization_id?: string
  created_at?: string; completed_at?: string
}

export default function AdminPrivacyRequestsPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [reqs, setReqs] = useState<Req[]>([])
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  // per-request admin inputs
  const [orgId, setOrgId] = useState<Record<string, string>>({})
  const [players, setPlayers] = useState<Record<string, string>>({})
  const [games, setGames] = useState<Record<string, string>>({})
  const [note, setNote] = useState<Record<string, string>>({})

  useEffect(() => { fetchMe() }, [])
  useEffect(() => {
    if (!isLoading && !user) { router.push('/login'); return }
    if (!isLoading && user && !user.organization.admin_level) router.push('/dashboard')
  }, [isLoading, user])

  function load() {
    api.get('/admin/privacy-requests').then(r => setReqs(r.data)).catch(() => setErr('Failed to load requests'))
  }
  useEffect(() => { if (user?.organization.admin_level) load() }, [user])

  const csv = (s?: string) => (s || '').split(',').map(x => x.trim()).filter(Boolean)

  async function act(id: string, fn: () => Promise<any>) {
    setBusy(id); setErr('')
    try { await fn(); load() }
    catch (e: any) { setErr(e?.response?.data?.detail || 'Action failed') }
    finally { setBusy('') }
  }

  const verify = (r: Req) => act(r.id, () =>
    api.post(`/admin/privacy-requests/${r.id}/verify`, { organization_id: orgId[r.id] || undefined, note: note[r.id] || undefined }))
  const fulfill = (r: Req) => act(r.id, () =>
    api.post(`/admin/privacy-requests/${r.id}/fulfill`, { roster_player_ids: csv(players[r.id]), game_ids: csv(games[r.id]), note: note[r.id] || undefined }))
  const reject = (r: Req) => act(r.id, () =>
    api.post(`/admin/privacy-requests/${r.id}/reject`, { reason: note[r.id] || 'Unable to verify authority over this student’s data.' }))

  if (!user) return null

  const badge: Record<string, string> = {
    pending: 'bg-yellow-500/15 text-yellow-400',
    verified: 'bg-blue-500/15 text-blue-400',
    completed: 'bg-brand-500/15 text-brand-400',
    rejected: 'bg-red-500/15 text-red-400',
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto bg-gray-950 p-8 text-gray-200">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-2xl font-bold mb-1">Privacy Requests</h1>
          <p className="text-gray-400 text-sm mb-6">
            COPPA/FERPA parent data access &amp; deletion requests. Verify the requester (coordinate with
            the school), then fulfill or reject. Deletion emails a certificate. Find roster player / game
            IDs in the org’s roster and games views.
          </p>
          {err && <p className="text-red-400 text-sm mb-4">{err}</p>}
          {reqs.length === 0 && <p className="text-gray-500">No requests yet.</p>}

          <div className="space-y-4">
            {reqs.map(r => (
              <div key={r.id} className="border border-gray-800 rounded-lg p-4 bg-gray-900/50">
                <div className="flex items-center justify-between gap-3 mb-2">
                  <div className="font-semibold">
                    {r.request_type === 'deletion' ? 'Deletion' : 'Access'} — {r.student_name}
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded ${badge[r.status] || 'bg-gray-700'}`}>{r.status}</span>
                </div>
                <div className="text-sm text-gray-400 space-y-0.5 mb-3">
                  <div>From: {r.requester_name} ({r.relationship}) — {r.requester_email}</div>
                  <div>School/program: {r.school_or_org || '—'}</div>
                  <div>Identifiers: {r.student_details || '—'}</div>
                  {r.details && <div>Details: {r.details}</div>}
                  {r.resolution_note && <div className="text-gray-500 whitespace-pre-line">Log: {r.resolution_note}</div>}
                  {r.certificate_id && <div className="text-brand-400">Certificate: {r.certificate_id}</div>}
                </div>

                {r.status === 'pending' && (
                  <div className="space-y-2">
                    <input className="input" placeholder="Organization ID the data lives in"
                      value={orgId[r.id] || ''} onChange={e => setOrgId(s => ({ ...s, [r.id]: e.target.value }))} />
                    <input className="input" placeholder="Note (optional)"
                      value={note[r.id] || ''} onChange={e => setNote(s => ({ ...s, [r.id]: e.target.value }))} />
                    <div className="flex gap-2">
                      <button disabled={busy === r.id} onClick={() => verify(r)} className="btn-primary">Verify</button>
                      <button disabled={busy === r.id} onClick={() => reject(r)} className="px-3 py-2 rounded border border-red-800 text-red-400 text-sm">Reject</button>
                    </div>
                  </div>
                )}

                {r.status === 'verified' && (
                  <div className="space-y-2">
                    {r.request_type === 'deletion' && (
                      <>
                        <input className="input" placeholder="Roster player IDs to delete (comma-separated)"
                          value={players[r.id] || ''} onChange={e => setPlayers(s => ({ ...s, [r.id]: e.target.value }))} />
                        <input className="input" placeholder="Game IDs to delete entirely — school-authorized (comma-separated)"
                          value={games[r.id] || ''} onChange={e => setGames(s => ({ ...s, [r.id]: e.target.value }))} />
                      </>
                    )}
                    <input className="input" placeholder="Note (optional)"
                      value={note[r.id] || ''} onChange={e => setNote(s => ({ ...s, [r.id]: e.target.value }))} />
                    <div className="flex gap-2">
                      <button disabled={busy === r.id} onClick={() => fulfill(r)} className="btn-primary">
                        {r.request_type === 'deletion' ? 'Delete & certify' : 'Mark fulfilled'}
                      </button>
                      <button disabled={busy === r.id} onClick={() => reject(r)} className="px-3 py-2 rounded border border-red-800 text-red-400 text-sm">Reject</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
