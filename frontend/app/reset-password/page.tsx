'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'

export default function ResetPasswordPage() {
  const router = useRouter()
  const [token, setToken] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // Read the token from the URL without useSearchParams (avoids a Suspense
  // requirement at build time). Runs once on mount.
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
      setError(err.response?.data?.detail || 'Could not reset password. The link may have expired.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-brand-400">CoachLenz</h1>
          <p className="text-gray-400 mt-2">Choose a new password</p>
        </div>
        {done ? (
          <div className="card space-y-4 text-center">
            <div className="text-brand-400 text-lg font-semibold">Password reset</div>
            <p className="text-gray-400 text-sm">You can now sign in with your new password. Redirecting…</p>
            <Link href="/login" className="btn-primary w-full inline-block">Sign In</Link>
          </div>
        ) : !token ? (
          <div className="card space-y-4 text-center">
            <div className="text-red-400 text-sm bg-red-400/10 rounded p-3">
              This reset link is missing its token. Request a new one.
            </div>
            <Link href="/forgot-password" className="btn-primary w-full inline-block">Request New Link</Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="card space-y-4">
            {error && <div className="text-red-400 text-sm bg-red-400/10 rounded p-3">{error}</div>}
            <div>
              <label className="label">New Password</label>
              <input type="password" className="input" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} />
              <p className="text-xs text-gray-500 mt-1">At least 8 characters.</p>
            </div>
            <div>
              <label className="label">Confirm New Password</label>
              <input type="password" className="input" value={confirm} onChange={e => setConfirm(e.target.value)} required />
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full">
              {loading ? 'Resetting...' : 'Reset Password'}
            </button>
            <p className="text-center text-sm text-gray-400">
              <Link href="/login" className="text-brand-400 hover:underline">Back to Sign In</Link>
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
