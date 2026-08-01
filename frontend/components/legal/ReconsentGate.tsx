'use client'
import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'

// Blocking re-consent modal. When the Terms/Privacy version bumps, existing users
// must re-accept before continuing. Mounted globally in the root layout: it no-ops
// until a user is signed in, then checks GET /legal/status.reconsent_needed and,
// if non-empty, blocks the app until the user accepts (recorded server-side).
const DOC_LABEL: Record<string, string> = { terms: 'Terms of Service', privacy: 'Privacy Policy' }

export default function ReconsentGate() {
  const user = useAuth((s) => s.user)
  const [needed, setNeeded] = useState<string[]>([])
  const [checkedFor, setCheckedFor] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!user) { setNeeded([]); setCheckedFor(null); return }
    if (checkedFor === user.id) return
    let cancelled = false
    ;(async () => {
      try {
        const r = await api.get('/legal/status')
        if (!cancelled) { setNeeded(r.data?.reconsent_needed || []); setCheckedFor(user.id) }
      } catch {
        // Never trap the user on a status error — fail open (no modal).
        if (!cancelled) { setNeeded([]); setCheckedFor(user.id) }
      }
    })()
    return () => { cancelled = true }
  }, [user, checkedFor])

  if (!user || needed.length === 0) return null

  const label = needed.map((d) => DOC_LABEL[d] || d).join(' and ')

  const accept = async () => {
    setSaving(true); setErr('')
    try {
      await api.post('/legal/accept-latest')
      setNeeded([])
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Could not record your acceptance. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 9999, background: 'rgba(0,0,0,0.78)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div style={{ maxWidth: 440, width: '100%', background: '#161616',
        border: '1px solid rgba(201,168,76,0.4)', borderRadius: 10, padding: 24 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: '#f8f6f0', marginBottom: 8 }}>
          We&apos;ve updated our {label}
        </h2>
        <p style={{ fontSize: 13, color: '#c8c3b6', lineHeight: 1.55, marginBottom: 14 }}>
          Please review and accept the updated {label} to keep using CoachLenz.
        </p>
        <div style={{ display: 'flex', gap: 16, fontSize: 12, marginBottom: 18 }}>
          <a href="/terms" target="_blank" rel="noreferrer" style={{ color: '#C9A84C', textDecoration: 'underline' }}>Terms of Service</a>
          <a href="/privacy" target="_blank" rel="noreferrer" style={{ color: '#C9A84C', textDecoration: 'underline' }}>Privacy Policy</a>
        </div>
        {err && <div style={{ fontSize: 12, color: '#e07070', marginBottom: 10 }}>{err}</div>}
        <button onClick={accept} disabled={saving} className="btn-primary" style={{ width: '100%' }}>
          {saving ? 'Saving…' : `I have read and accept the updated ${label}`}
        </button>
        <p style={{ fontSize: 10, color: '#7a7a6e', marginTop: 10, textAlign: 'center' }}>
          Your acceptance is recorded with a timestamp.
        </p>
      </div>
    </div>
  )
}
