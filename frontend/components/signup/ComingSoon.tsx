'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { publicApi } from '@/lib/api'
import logo from '../../public/coachlenz-logo.png'

const SPORTS: { value: string; label: string }[] = [
  { value: '', label: 'Sport (optional)' },
  { value: 'basketball', label: 'Basketball' },
  { value: 'football', label: 'Football' },
  { value: 'soccer', label: 'Soccer' },
  { value: 'volleyball', label: 'Volleyball' },
  { value: 'other', label: 'Other' },
]

function emailProblem(value: string): string {
  const v = value.trim()
  if (!v) return 'Email is required.'
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) return 'Enter a valid email address.'
  return ''
}

function serverProblem(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) return 'Enter a valid email address.'
  return 'Could not join the waitlist. Please try again.'
}

function NoIndex() {
  useEffect(() => {
    const meta = document.createElement('meta')
    meta.name = 'robots'
    meta.content = 'noindex, nofollow'
    document.head.appendChild(meta)
    return () => {
      meta.remove()
    }
  }, [])
  return null
}

export default function ComingSoon({ source = 'waitlist' }: { source?: string }) {
  const [email, setEmail] = useState('')
  const [school, setSchool] = useState('')
  const [sport, setSport] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const problem = emailProblem(email)
    if (problem) {
      setError(problem)
      return
    }
    setError('')
    setLoading(true)
    try {
      await publicApi.post('/leads', {
        email: email.trim(),
        source,
        ...(school.trim() ? { school: school.trim() } : {}),
        ...(sport ? { sport } : {}),
      })
      setSent(true)
    } catch (err) {
      setError(serverProblem(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      <NoIndex />
      <header className="border-b border-gray-800 px-6 sm:px-8 py-4 flex items-center justify-between">
        <img src={logo.src} alt="CoachLenz" style={{ height: 30, width: 'auto' }} />
        <Link href="/login" className="text-sm text-gray-400 hover:text-gray-100">Sign in</Link>
      </header>

      <main className="flex-1 flex items-center justify-center px-6 py-16">
        <div className="w-full max-w-lg">
          <p className="text-xs uppercase tracking-[0.18em] text-gold-400 mb-3">Coming soon</p>
          <h1 className="text-3xl sm:text-4xl font-bold text-gray-100 mb-4">
            CoachLenz is launching soon
          </h1>
          <p className="text-gray-400 mb-8">
            Game film for school basketball and football. Leave your email and we will
            tell you when it opens. If you already have an account, you can still sign in.
          </p>

          <div className="card">
            {sent ? (
              <p role="status" className="text-gray-200">
                You are on the list. We will email you when CoachLenz opens.
              </p>
            ) : (
              <form onSubmit={submit} className="space-y-4" noValidate>
                {error && (
                  <div role="alert" className="text-red-400 text-sm bg-red-400/10 rounded p-3">{error}</div>
                )}
                <div>
                  <label className="label" htmlFor="waitlist-email">Email</label>
                  <input
                    id="waitlist-email"
                    type="email"
                    required
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@yourschool.org"
                    className="input"
                    aria-invalid={error ? true : undefined}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="waitlist-school">School <span className="normal-case tracking-normal">(optional)</span></label>
                  <input
                    id="waitlist-school"
                    type="text"
                    value={school}
                    onChange={(e) => setSchool(e.target.value)}
                    placeholder="Lincoln High"
                    className="input"
                    maxLength={200}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="waitlist-sport">Sport <span className="normal-case tracking-normal">(optional)</span></label>
                  <select
                    id="waitlist-sport"
                    value={sport}
                    onChange={(e) => setSport(e.target.value)}
                    className="input"
                  >
                    {SPORTS.map((s) => (
                      <option key={s.value || 'none'} value={s.value}>{s.label}</option>
                    ))}
                  </select>
                </div>
                <button type="submit" disabled={loading} className="btn-primary w-full">
                  {loading ? 'Joining...' : 'Join the waitlist'}
                </button>
              </form>
            )}
          </div>

          <p className="text-center text-sm text-gray-400 mt-6">
            Already have an account? <Link href="/login" className="text-brand-400 hover:underline">Sign in</Link>
          </p>
        </div>
      </main>

      <footer className="border-t border-gray-800 px-8 py-4 text-center text-sm text-gray-500">
        Powered by <a href="https://cosbyaisolutions.com" className="text-brand-400 hover:underline" target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
      </footer>
    </div>
  )
}
