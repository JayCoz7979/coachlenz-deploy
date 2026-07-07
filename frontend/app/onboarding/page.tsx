'use client'
import { Suspense } from 'react'
import { useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'

type Sport = { value: string; label: string }

function OnboardingForm() {
  const router = useRouter()
  const params = useSearchParams()
  const [phase, setPhase] = useState<'register' | 'sport'>('register')
  const [form, setForm] = useState({ name: '', email: '', password: '', org_name: '', referral_code: params.get('ref') || '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // Sport-selection step state
  const [choosable, setChoosable] = useState<Sport[]>([])
  const [maxSports, setMaxSports] = useState(1)
  const [tier, setTier] = useState('trial')
  const [picked, setPicked] = useState<string[]>([])

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setForm(f => ({ ...f, [k]: e.target.value }))

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const res = await api.post('/auth/register', form)
      localStorage.setItem('access_token', res.data.access_token)
      localStorage.setItem('refresh_token', res.data.refresh_token)
      const status = await api.get('/onboarding/status')
      setChoosable(status.data.choosable_sports || [])
      setMaxSports(status.data.max_sports || 1)
      setTier(status.data.tier || 'trial')
      setPhase('sport')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  function toggleSport(v: string) {
    setError('')
    setPicked(prev => {
      if (prev.includes(v)) return prev.filter(s => s !== v)
      if (prev.length >= maxSports) {
        // At the plan limit: replace when only one is allowed, else warn.
        if (maxSports === 1) return [v]
        setError(`Your ${tier} plan includes ${maxSports} sports. Deselect one to change.`)
        return prev
      }
      return [...prev, v]
    })
  }

  async function handleChooseSport() {
    if (picked.length === 0) { setError('Pick your sport to continue.'); return }
    setLoading(true); setError('')
    try {
      await api.post('/onboarding/sports', { sports: picked })
      router.push('/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Could not save your sport selection.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center py-12">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-brand-400">CoachLenz</h1>
          <p className="text-gray-400 mt-2">
            {phase === 'register' ? 'Start your 14-day free trial' : 'Choose your sport'}
          </p>
        </div>

        {phase === 'register' ? (
          <form onSubmit={handleRegister} className="card space-y-4">
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
            <button type="submit" disabled={loading} className="btn-primary w-full">
              {loading ? 'Creating account...' : 'Start Free Trial'}
            </button>
            <p className="text-center text-sm text-gray-400">
              Already have an account? <Link href="/login" className="text-brand-400 hover:underline">Sign in</Link>
            </p>
            <p className="text-center text-xs text-gray-500">
              By signing up you agree to our <Link href="/terms" className="underline">Terms</Link> and <Link href="/privacy" className="underline">Privacy Policy</Link>
            </p>
          </form>
        ) : (
          <div className="card space-y-4">
            {error && <div className="text-red-400 text-sm bg-red-400/10 rounded p-3">{error}</div>}
            <p className="text-gray-400 text-sm">
              Your <span className="text-gray-200">{tier}</span> plan includes{' '}
              <span className="text-brand-400 font-semibold">{maxSports}</span> sport{maxSports !== 1 ? 's' : ''}.
              This is <span className="text-gray-200">locked in</span> once you continue — everything you analyze
              stays tied to your selection.
            </p>
            <div className="space-y-2">
              {choosable.map(s => {
                const on = picked.includes(s.value)
                return (
                  <button key={s.value} type="button" onClick={() => toggleSport(s.value)}
                    className="w-full flex items-center justify-between rounded-lg px-4 py-3 text-left transition"
                    style={{
                      background: on ? 'rgba(26,92,42,0.4)' : 'rgba(255,255,255,0.04)',
                      border: on ? '1px solid #2d8c40' : '1px solid rgba(255,255,255,0.1)',
                      color: '#f8f6f0',
                    }}>
                    <span className="font-semibold">{s.label}</span>
                    <span style={{ color: on ? '#2d8c40' : '#7a7a6e', fontSize: 13 }}>{on ? '✓ Selected' : 'Select'}</span>
                  </button>
                )
              })}
            </div>
            <p className="text-xs text-gray-500">Selected {picked.length} of {maxSports}.</p>
            <button onClick={handleChooseSport} disabled={loading || picked.length === 0} className="btn-primary w-full">
              {loading ? 'Locking in...' : 'Continue'}
            </button>
          </div>
        )}

        <p className="text-center text-xs text-gray-600 mt-6">
          Powered by <a href="https://cosbyaisolutions.com" className="text-brand-500 hover:underline" target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
        </p>
      </div>
    </div>
  )
}

export default function OnboardingPage() {
  return (
    <Suspense fallback={null}>
      <OnboardingForm />
    </Suspense>
  )
}
