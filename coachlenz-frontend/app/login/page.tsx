'use client'

import { useState, FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { Trophy, Loader2, AlertCircle } from 'lucide-react'
import { authApi } from '@/lib/api'
import { setToken, setCoach } from '@/lib/auth'

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const res = await authApi.login(email, password)
      setToken(res.access_token)
      setCoach({
        id: res.coach_id,
        name: res.name,
        email: res.email,
        role: res.role,
      })
      router.replace('/dashboard')
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Login failed. Please try again.'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#0d0d0d] flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-[#2563eb] mb-4">
            <Trophy className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-white">CoachLenz</h1>
          <p className="text-[#6b7280] mt-2">Sports Coaching Admin Platform</p>
        </div>

        {/* Login card */}
        <div className="bg-[#161616] border border-[#1e1e1e] rounded-2xl p-8">
          <h2 className="text-white font-semibold text-xl mb-6">Sign in to your account</h2>

          {error && (
            <div className="flex items-start gap-3 bg-red-900/20 border border-red-800/50 rounded-lg p-4 mb-6">
              <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="label">Email address</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="coach@school.edu"
                required
                className="input"
                autoComplete="email"
              />
            </div>

            <div>
              <label className="label">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                className="input"
                autoComplete="current-password"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full btn-primary py-3 flex items-center justify-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>
        </div>

        <p className="text-center text-[#4b5563] text-xs mt-8">
          Powered by{' '}
          <a
            href="https://cosbyaisolutions.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[#2563eb] hover:underline"
          >
            Cosby AI Solutions
          </a>
        </p>
      </div>
    </div>
  )
}
