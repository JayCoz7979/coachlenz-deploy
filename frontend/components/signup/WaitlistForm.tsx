'use client'

import { useEffect, useState } from 'react'
import { publicApi } from '@/lib/api'
import { readWaitlistAttribution } from '@/lib/waitlistAttribution'

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
  { value: 'principal_admin', label: 'Principal or Admin' },
  { value: 'video_coordinator', label: 'Video Coordinator' },
  { value: 'parent', label: 'Parent' },
  { value: 'other', label: 'Other' },
]

// Locked live copy. Version cl-halftime-v1. Pair A is not rendered.
export const CONSENT_LINE = "By clicking Send me the Halftime Sheet, you join the CoachLenz waitlist and agree that CoachLenz can email you about the waitlist, free coaching resources, launch news, and pricing when we open. You can unsubscribe anytime with one click. See our Privacy Policy."
export const CONSENT_BUTTON = "Send me the Halftime Sheet"
export const WAITLIST_SUCCESS = "You're on the list."
const WAITLIST_CHECK_EMAIL = "Almost done. Check your inbox and tap the confirm button to join the waitlist. If you don't see it, check your spam or promotions folder."

function ConsentLine({ line }: { line: string }) {
  const mark = 'Privacy Policy'
  const at = line.lastIndexOf(mark)
  if (at < 0) return <>{line}</>
  return (
    <>
      {line.slice(0, at)}
      <a href="https://app.coachlenz.com/privacy" className="text-brand-400 underline">{mark}</a>
      {line.slice(at + mark.length)}
    </>
  )
}

function problem(firstName: string, email: string, role: string): string {
  if (!firstName.trim()) return 'First name is required.'
  if (firstName.trim().length > 80) return 'First name must be 80 characters or less.'
  if (!email.trim()) return 'Email is required.'
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) return 'Enter a valid email address.'
  if (!role) return 'Please tell us your role.'
  return ''
}

function serverProblem(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg).replace(/^Value error,\s*/i, '')
  return 'Could not join the waitlist. Please try again.'
}

export default function WaitlistForm({ source, id = 'waitlist' }: { source: string; id?: string }) {
  const [firstName, setFirstName] = useState('')
  const [email, setEmail] = useState('')
  const [school, setSchool] = useState('')
  const [sport, setSport] = useState('')
  const [role, setRole] = useState('')
  const [emailOn, setEmailOn] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)

  useEffect(() => {
    publicApi.get('/auth/signups', { timeout: 8000 })
      .then((r) => {
        setEmailOn(r.data?.waitlist_email_enabled === true)
      })
      .catch(() => setEmailOn(false))
  }, [])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const message = problem(firstName, email, role)
    if (message) {
      setError(message)
      return
    }
    setError('')
    setLoading(true)
    try {
      await publicApi.post('/leads', {
        email: email.trim(),
        first_name: firstName.trim(),
        role,
        source,
        ...(school.trim() ? { school: school.trim() } : {}),
        ...(sport ? { sport } : {}),
        ...readWaitlistAttribution(),
      })
      setSent(true)
    } catch (err) {
      setError(serverProblem(err))
    } finally {
      setLoading(false)
    }
  }

  if (sent) return <p role="status" className="text-base text-gray-100">{emailOn ? WAITLIST_CHECK_EMAIL : WAITLIST_SUCCESS}</p>

  return (
    <form id={id} onSubmit={submit} className="space-y-4 text-left" noValidate>
      {error && <div role="alert" className="text-red-400 text-sm bg-red-400/10 rounded p-3">{error}</div>}
      <div>
        <label className="label" htmlFor={`${id}-first`}>First name</label>
        <input id={`${id}-first`} className="input" value={firstName} onChange={(e) => setFirstName(e.target.value)} required maxLength={80} autoComplete="given-name" />
      </div>
      <div>
        <label className="label" htmlFor={`${id}-email`}>Email</label>
        <input id={`${id}-email`} type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@yourschool.org" className="input" />
      </div>
      <div>
        <label className="label" htmlFor={`${id}-role`}>I am a...</label>
        <select id={`${id}-role`} required value={role} onChange={(e) => setRole(e.target.value)} className="input">
          {ROLES.map((r) => <option key={r.value || 'none'} value={r.value}>{r.label}</option>)}
        </select>
      </div>
      <div>
        <label className="label" htmlFor={`${id}-school`}>School <span className="normal-case tracking-normal">(optional)</span></label>
        <input id={`${id}-school`} className="input" value={school} onChange={(e) => setSchool(e.target.value)} maxLength={200} />
      </div>
      <div>
        <label className="label" htmlFor={`${id}-sport`}>Sport <span className="normal-case tracking-normal">(optional)</span></label>
        <select id={`${id}-sport`} value={sport} onChange={(e) => setSport(e.target.value)} className="input">
          {SPORTS.map((s) => <option key={s.value || 'none'} value={s.value}>{s.label}</option>)}
        </select>
      </div>
      <p className="text-base text-gray-100">
        <ConsentLine line={CONSENT_LINE} />
      </p>
      <button type="submit" disabled={loading} className="btn-primary w-full">{loading ? 'Sending...' : CONSENT_BUTTON}</button>
    </form>
  )
}
