'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'
// Static import so the transparent lockup is emitted to /_next/static/media
// (public/ is not bundled with output:'standalone').
import logo from '../../public/coachlenz-logo.png'

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const res = await api.post('/auth/login', { email, password })
      localStorage.setItem('access_token', res.data.access_token)
      localStorage.setItem('refresh_token', res.data.refresh_token)
      router.push('/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="w-full max-w-md">
        <div className="text-center mb-8 px-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={logo.src} alt="CoachLenz" className="mx-auto w-full h-auto" style={{ maxWidth: 340 }} />
          <p className="text-gray-400 mt-5">Sign in to your account</p>
        </div>
        <form onSubmit={handleSubmit} className="card space-y-4">
          {error && <div className="text-red-400 text-sm bg-red-400/10 rounded p-3">{error}</div>}
          <div>
            <label className="label">Email</label>
            <input type="email" className="input" value={email} onChange={e => setEmail(e.target.value)} required />
          </div>
          <div>
            <div className="flex items-center justify-between">
              <label className="label">Password</label>
              <Link href="/forgot-password" className="text-xs text-brand-400 hover:underline">Forgot password?</Link>
            </div>
            <input type="password" className="input" value={password} onChange={e => setPassword(e.target.value)} required />
          </div>
          <button type="submit" disabled={loading} className="btn-primary w-full">{loading ? 'Signing in...' : 'Sign In'}</button>
          <p className="text-center text-sm text-gray-400">
            No account? <Link href="/onboarding" className="text-brand-400 hover:underline">Start free trial</Link>
          </p>
        </form>
        <p className="text-center text-xs text-gray-600 mt-6">
          Powered by <a href="https://cosbyaisolutions.com" className="text-brand-500 hover:underline" target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
        </p>
      </div>
    </div>
  )
}
