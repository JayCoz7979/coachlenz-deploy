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
  { value: 'player', label: 'Player' },
  { value: 'other', label: 'Other' },
]

// Pair A, the default. GET /auth/signups can replace both strings together.
export const CONSENT_LINE_A = "By joining, you agree that CoachLenz can email you about the waitlist, free coaching resources, launch news, and pricing when we open. You can unsubscribe anytime with one click. See our Privacy Policy."
export const CONSENT_BUTTON_A = "Join the waitlist"
export const WAITLIST_SUCCESS = "You're on the list."

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

function problem(firstName: string, email: string, role: string, adult: '' | 'yes' | 'no', playerOn: boolean): string {
  if (!firstName.trim()) return 'First name is required.'
  if (firstName.trim().length > 80) return 'First name must be 80 characters or less.'
  if (!email.trim()) return 'Email is required.'
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) return 'Enter a valid email address.'
  if (!role) return 'Please tell us your role.'
  if (role === 'player' && playerOn && !adult) return 'Please tell us if you are 19 or older.'
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
  const [adult, setAdult] = useState<'' | 'yes' | 'no'>('')
  const [playerOn, setPlayerOn] = useState(false)
  const [buttonLabel, setButtonLabel] = useState(CONSENT_BUTTON_A)
  const [consentLine, setConsentLine] = useState(CONSENT_LINE_A)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)

  useEffect(() => {
    publicApi.get('/auth/signups', { timeout: 8000 })
      .then((r) => {
        setPlayerOn(r.data?.player_role_enabled === true)
        if (typeof r.data?.consent_button === 'string' && r.data.consent_button.trim()) {
          setButtonLabel(r.data.consent_button)
        }
        if (typeof r.data?.consent_line === 'string' && r.data.consent_line.trim()) {
          setConsentLine(r.data.consent_line)
        }
      })
      .catch(() => setPlayerOn(false))
  }, [])

  const roles = playerOn ? ROLES : ROLES.filter((r) => r.value !== 'player')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const message = problem(firstName, email, role, adult, playerOn)
    if (message) {
      setError(message)
      return
    }
    setError('')
    setLoading(true)
    try {
      const res = await publicApi.post('/leads', {
        email: email.trim(),
        first_name: firstName.trim(),
        role,
        source,
        ...(role === 'player' ? { is_19_or_older: adult === 'yes' } : {}),
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

  if (sent) return <p role="status" className="text-base text-gray-100">{WAITLIST_SUCCESS}</p>

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
        <select id={`${id}-role`} required value={role} onChange={(e) => { setRole(e.target.value); setAdult('') }} className="input">
          {roles.map((r) => <option key={r.value || 'none'} value={r.value}>{r.label}</option>)}
        </select>
      </div>
      {playerOn && role === 'player' && (
        <fieldset className="space-y-2">
          <legend className="text-sm text-gray-100 mb-1">Are you 19 or older?</legend>
          <label className="flex items-center gap-2 text-sm text-gray-100"><input type="radio" name={`${id}-adult`} checked={adult === 'yes'} onChange={() => setAdult('yes')} /> Yes</label>
          <label className="flex items-center gap-2 text-sm text-gray-100"><input type="radio" name={`${id}-adult`} checked={adult === 'no'} onChange={() => setAdult('no')} /> No</label>
        </fieldset>
      )}
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
        <ConsentLine line={consentLine} />
      </p>
      <button type="submit" disabled={loading} className="btn-primary w-full">{loading ? 'Sending...' : buttonLabel}</button>
    </form>
  )
}
