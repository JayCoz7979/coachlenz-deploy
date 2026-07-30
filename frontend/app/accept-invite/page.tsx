'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'

export default function AcceptInvitePage() {
  const router = useRouter()
  const [token, setToken] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // Read the invite token from the URL (?token=...). The invite token IS a
  // password-reset token, so we set the password through /auth/reset-password.
  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get('token') || ''
    setToken(t)
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (password.length < 8) { setError('Password must be at least 8 characters.'); return }
    if (password !== confirm) { setError('Passwords do not match.'); return }
    setLoading(true)
    try {
      await api.post('/auth/reset-password', { token, new_password: password })
      setDone(true)
      setTimeout(() => router.push('/login'), 2500)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Could not accept this invite. The link may have expired.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-brand-400">CoachLenz</h1>
          <p className="text-gray-400 mt-2">Set your password to join your staff</p>
        </div>
        {done ? (
          <div className="card space-y-4 text-center">
            <div className="text-brand-400 text-lg font-semibold">You're all set</div>
            <p className="text-gray-400 text-sm">Your password is set. Sign in to get started. Redirecting…</p>
            <Link href="/login" className="btn-primary w-full inline-block">Sign In</Link>
          </div>
        ) : !token ? (
          <div className="card space-y-4 text-center">
            <div className="text-red-400 text-sm bg-red-400/10 rounded p-3">
              This invite link is missing its token. Ask your head coach to resend the invite.
            </div>
            <Link href="/login" className="btn-primary w-full inline-block">Back to Sign In</Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="card space-y-4">
            {error && <div className="text-red-400 text-sm bg-red-400/10 rounded p-3">{error}</div>}
            <div>
              <label className="label">Create a Password</label>
              <input type="password" className="input" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} />
              <p className="text-xs text-gray-500 mt-1">At least 8 characters.</p>
            </div>
            <div>
              <label className="label">Confirm Password</label>
              <input type="password" className="input" value={confirm} onChange={e => setConfirm(e.target.value)} required />
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full">
              {loading ? 'Setting up...' : 'Accept Invite'}
            </button>
            <p className="text-center text-sm text-gray-400">
              Already have an account? <Link href="/login" className="text-brand-400 hover:underline">Sign In</Link>
            </p>
          </form>
        )}
        <p className="text-center text-xs text-gray-600 mt-6">
          Powered by <a href="https://cosbyaisolutions.com" className="text-brand-500 hover:underline" target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
        </p>
      </div>
    </div>
  )
}
