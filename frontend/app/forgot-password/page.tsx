'use client'
import { useState } from 'react'
import Link from 'next/link'
import api from '@/lib/api'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await api.post('/auth/forgot-password', { email })
      setSent(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Something went wrong. Try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-brand-400">CoachLenz</h1>
          <p className="text-gray-400 mt-2">Reset your password</p>
        </div>
        {sent ? (
          <div className="card space-y-4 text-center">
            <div className="text-brand-400 text-lg font-semibold">Check your email</div>
            <p className="text-gray-400 text-sm">
              If an account exists for <span className="text-gray-200">{email}</span>, we&apos;ve sent a
              reset link. It expires in 1 hour and can be used once.
            </p>
            <Link href="/login" className="btn-primary w-full inline-block">Back to Sign In</Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="card space-y-4">
            {error && <div className="text-red-400 text-sm bg-red-400/10 rounded p-3">{error}</div>}
            <p className="text-gray-400 text-sm">Enter your account email and we&apos;ll send you a reset link.</p>
            <div>
              <label className="label">Email</label>
              <input type="email" className="input" value={email} onChange={e => setEmail(e.target.value)} required />
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full">
              {loading ? 'Sending...' : 'Send Reset Link'}
            </button>
            <p className="text-center text-sm text-gray-400">
              Remembered it? <Link href="/login" className="text-brand-400 hover:underline">Back to Sign In</Link>
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
