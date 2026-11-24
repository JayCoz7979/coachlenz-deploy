'use client'

import { useState } from 'react'
import { publicApi } from '@/lib/api'

const SPORTS: { value: string; label: string }[] = [
  { value: '', label: 'Sport (optional)' },
  { value: 'basketball', label: 'Basketball' },
  { value: 'football', label: 'Football' },
  { value: 'soccer', label: 'Soccer' },
  { value: 'volleyball', label: 'Volleyball' },
  { value: 'other', label: 'Other' },
]

const ROLES: { value: string; label: string }[] = [
  { value: '', label: 'I am a...' },
  { value: 'head_coach', label: 'Head Coach' },
  { value: 'assistant_coach', label: 'Assistant Coach' },
  { value: 'athletic_director', label: 'Athletic Director' },
  { value: 'school_admin', label: 'Principal / School Admin' },
  { value: 'film_coordinator', label: 'Video / Film Coordinator' },
  { value: 'parent', label: 'Parent' },
  { value: 'player', label: 'Player' },
  { value: 'other', label: 'Other' },
]

export const WAITLIST_SUCCESS = "You're on the list. You'll be among the first to experience CoachLenz."

function attribution(): Record<string, string> {
  if (typeof window === 'undefined') return {}
  const q = new URLSearchParams(window.location.search)
  const out: Record<string, string> = {}
  const magnet = (q.get('lead_magnet') || q.get('magnet') || '').trim()
  if (magnet) out.lead_magnet = magnet
  for (const key of ['utm_source', 'utm_medium', 'utm_campaign'] as const) {
    const value = (q.get(key) || '').trim()
    if (value) out[key] = value
  }
  return out
}

function problem(name: string, email: string, role: string, roleOther: string, consent: boolean): string {
  if (!name.trim()) return 'Name is required.'
  if (name.trim().length > 100) return 'Name must be 100 characters or less.'
  const v = email.trim()
  if (!v) return 'Email is required.'
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) return 'Enter a valid email address.'
  if (!role) return 'Please tell us your role.'
  if (roleOther.trim().length > 100) return 'That note must be 100 characters or less.'
  if (!consent) return 'Please agree to receive launch updates.'
  return ''
}

function serverProblem(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail.length) {
    const msg = detail[0]?.msg
    if (typeof msg === 'string' && msg.trim()) return msg.replace(/^Value error,\s*/i, '')
  }
  return 'Could not join the waitlist. Please try again.'
}

export default function WaitlistForm({ source, id = 'waitlist' }: { source: string; id?: string }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [school, setSchool] = useState('')
  const [sport, setSport] = useState('')
  const [role, setRole] = useState('')
  const [roleOther, setRoleOther] = useState('')
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const message = problem(name, email, role, roleOther, consent)
    if (message) {
      setError(message)
      return
    }
    setError('')
    setLoading(true)
    try {
      await publicApi.post('/leads', {
        email: email.trim(),
        name: name.trim(),
        role,
        source,
        email_consent: true,
        ...attribution(),
        ...(school.trim() ? { school: school.trim() } : {}),
        ...(sport ? { sport } : {}),
        ...(role === 'other' && roleOther.trim() ? { role_other: roleOther.trim() } : {}),
      })
      setSent(true)
    } catch (err) {
      setError(serverProblem(err))
    } finally {
      setLoading(false)
    }
  }

  if (sent) {
    return <p role="status" className="text-gray-200">{WAITLIST_SUCCESS}</p>
  }

  return (
    <form id={id} onSubmit={submit} className="space-y-4 text-left" noValidate>
      {error && (
        <div role="alert" className="text-red-400 text-sm bg-red-400/10 rounded p-3">{error}</div>
      )}
      <div>
        <label className="label" htmlFor={`${id}-name`}>Name</label>
        <input id={`${id}-name`} className="input" value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} autoComplete="name" />
      </div>
      <div>
        <label className="label" htmlFor={`${id}-email`}>Email</label>
        <input id={`${id}-email`} type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@yourschool.org" className="input" aria-invalid={error ? true : undefined} />
      </div>
      <div>
        <label className="label" htmlFor={`${id}-role`}>I am a...</label>
        <select id={`${id}-role`} required value={role} onChange={(e) => setRole(e.target.value)} className="input">
          {ROLES.map((r) => (
            <option key={r.value || 'none'} value={r.value}>{r.label}</option>
          ))}
        </select>
      </div>
      {role === 'other' && (
        <div>
          <label className="label" htmlFor={`${id}-role-other`}>Tell us a bit more <span className="normal-case tracking-normal">(optional)</span></label>
          <input id={`${id}-role-other`} className="input" value={roleOther} onChange={(e) => setRoleOther(e.target.value)} maxLength={100} />
        </div>
      )}
      <div>
        <label className="label" htmlFor={`${id}-school`}>School <span className="normal-case tracking-normal">(optional)</span></label>
        <input id={`${id}-school`} className="input" value={school} onChange={(e) => setSchool(e.target.value)} placeholder="Lincoln High" maxLength={200} />
      </div>
      <div>
        <label className="label" htmlFor={`${id}-sport`}>Sport <span className="normal-case tracking-normal">(optional)</span></label>
        <select id={`${id}-sport`} value={sport} onChange={(e) => setSport(e.target.value)} className="input">
          {SPORTS.map((s) => (
            <option key={s.value || 'none'} value={s.value}>{s.label}</option>
          ))}
        </select>
      </div>
      <label className="flex items-start gap-2 text-sm text-gray-300 cursor-pointer">
        <input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} required />
        <span>Email me launch updates and coaching resources.</span>
      </label>
      <button type="submit" disabled={loading} className="btn-primary w-full">
        {loading ? 'Joining...' : 'Join the waitlist'}
      </button>
    </form>
  )
}
