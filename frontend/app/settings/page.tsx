'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { Loader2, KeyRound, CreditCard, Link2 } from 'lucide-react'

export default function SettingsPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])

  if (isLoading || !user) return null

  async function changePassword(e: React.FormEvent) {
    e.preventDefault()
    setMsg(null)
    if (next.length < 8) { setMsg({ kind: 'err', text: 'New password must be at least 8 characters.' }); return }
    if (next !== confirm) { setMsg({ kind: 'err', text: 'New passwords do not match.' }); return }
    setSaving(true)
    try {
      await api.post('/auth/change-password', { current_password: current, new_password: next })
      setCurrent(''); setNext(''); setConfirm('')
      setMsg({ kind: 'ok', text: 'Password updated.' })
    } catch (err: any) {
      setMsg({ kind: 'err', text: err?.response?.data?.detail || 'Could not update password.' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div style={{ maxWidth: 640, margin: '0 auto' }}>
          <h2 className="text-2xl font-bold" style={{ marginBottom: 4 }}>Account Settings</h2>
          <p style={{ color: 'var(--text3)', fontSize: 13, marginBottom: 24 }}>
            Signed in as <span style={{ color: 'var(--text)' }}>{user.email}</span>
          </p>

          {/* Change password */}
          <div className="card" style={{ marginBottom: 18 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <KeyRound size={16} style={{ color: 'var(--gold)' }} />
              <span style={{ fontWeight: 700 }}>Change Password</span>
            </div>
            <form onSubmit={changePassword} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {msg && (
                <div style={{ fontSize: 13, borderRadius: 8, padding: '10px 12px',
                  background: msg.kind === 'ok' ? 'rgba(45,140,64,0.12)' : 'var(--redl)',
                  color: msg.kind === 'ok' ? 'var(--green3)' : 'var(--red)' }}>{msg.text}</div>
              )}
              <div>
                <label className="label">Current Password</label>
                <input type="password" className="input" value={current} onChange={e => setCurrent(e.target.value)} required autoComplete="current-password" />
              </div>
              <div>
                <label className="label">New Password</label>
                <input type="password" className="input" value={next} onChange={e => setNext(e.target.value)} required minLength={8} autoComplete="new-password" />
                <p style={{ fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>At least 8 characters.</p>
              </div>
              <div>
                <label className="label">Confirm New Password</label>
                <input type="password" className="input" value={confirm} onChange={e => setConfirm(e.target.value)} required autoComplete="new-password" />
              </div>
              <button type="submit" disabled={saving} className="btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, alignSelf: 'flex-start' }}>
                {saving ? <><Loader2 size={15} className="animate-spin" /> Updating…</> : 'Update Password'}
              </button>
            </form>
          </div>

          {/* Quick links to the other settings areas */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Link href="/settings/billing" className="card" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none', color: 'var(--text)' }}>
              <CreditCard size={16} style={{ color: 'var(--gold)' }} /> Billing &amp; Plan
            </Link>
            <Link href="/settings/connections" className="card" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none', color: 'var(--text)' }}>
              <Link2 size={16} style={{ color: 'var(--gold)' }} /> Connected Accounts
            </Link>
          </div>
        </div>
      </main>
    </div>
  )
}
