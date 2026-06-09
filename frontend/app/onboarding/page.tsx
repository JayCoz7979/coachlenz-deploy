'use client'
import { Suspense } from 'react'
import { useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'

function OnboardingForm() {
  const router = useRouter()
  const params = useSearchParams()
  const [form, setForm] = useState({ name: '', email: '', password: '', org_name: '', referral_code: params.get('ref') || '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const res = await api.post('/auth/register', form)
      localStorage.setItem('access_token', res.data.access_token)
      localStorage.setItem('refresh_token', res.data.refresh_token)
      router.push('/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center py-12">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-brand-400">CoachLenz</h1>
          <p className="text-gray-400 mt-2">Start your 14-day free trial</p>
        </div>
        <form onSubmit={handleSubmit} className="card space-y-4">
          {error && <div className="text-red-400 text-sm bg-red-400/10 rounded p-3">{error}</div>}
          <div>
            <label className="label">Your Name</label>
            <input className="input" value={form.name} onChange={set('name')} required />
          </div>
          <div>
            <label className="label">Email</label>
            <input type="email" className="input" value={form.email} onChange={set('email')} required />
          </div>
          <div>
            <label className="label">Password</label>
            <input type="password" className="input" value={form.password} onChange={set('password')} required minLength={8} />
          </div>
          <div>
            <label className="label">School / Organization Name</label>
            <input className="input" value={form.org_name} onChange={set('org_name')} required />
          </div>
          {form.referral_code && (
            <div>
              <label className="label">Referral Code</label>
              <input className="input bg-gray-700" value={form.referral_code} readOnly />
            </div>
          )}
          <button type="submit" disabled={loading} className="btn-primary w-full">{loading ? 'Creating account...' : 'Start Free Trial'}</button>
          <p className="text-center text-sm text-gray-400">
            Already have an account? <Link href="/login" className="text-brand-400 hover:underline">Sign in</Link>
          </p>
          <p className="text-center text-xs text-gray-500">
            By signing up you agree to our <Link href="/terms" className="underline">Terms</Link> and <Link href="/privacy" className="underline">Privacy Policy</Link>
          </p>
        </form>
        <p className="text-center text-xs text-gray-600 mt-6">
          Powered by <a href="https://cosbyaisolutions.com" className="text-brand-500 hover:underline" target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
        </p>
      </div>
    </div>
  )
}

export default function OnboardingPage() {
  return (
    <Suspense>
      <OnboardingForm />
    </Suspense>
  )
}
