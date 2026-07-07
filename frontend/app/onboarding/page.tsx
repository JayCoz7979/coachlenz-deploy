'use client'
import { Suspense } from 'react'
import { useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'

type Sport = { value: string; label: string }
type Phase = 'register' | 'email' | 'phone' | 'sport'

function OnboardingForm() {
  const router = useRouter()
  const params = useSearchParams()
  const [phase, setPhase] = useState<Phase>('register')
  const [form, setForm] = useState({ name: '', email: '', password: '', org_name: '', referral_code: params.get('ref') || '' })
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [loading, setLoading] = useState(false)

  // verification state
  const [emailCode, setEmailCode] = useState('')
  const [emailCodeSent, setEmailCodeSent] = useState(false)
  const [phone, setPhone] = useState('')
  const [phoneSent, setPhoneSent] = useState(false)
  const [phoneCode, setPhoneCode] = useState('')

  // sport-selection state
  const [choosable, setChoosable] = useState<Sport[]>([])
  const [maxSports, setMaxSports] = useState(1)
  const [tier, setTier] = useState('trial')
  const [picked, setPicked] = useState<string[]>([])

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setForm(f => ({ ...f, [k]: e.target.value }))

  // Resume in place if a signed-in-but-unfinished user lands here.
  useEffect(() => {
    if (!localStorage.getItem('access_token')) return
    api.get('/onboarding/status').then(s => {
      setChoosable(s.data.choosable_sports || []); setMaxSports(s.data.max_sports || 1); setTier(s.data.tier || 'trial')
      const step = s.data.next_step
      if (step === 'done') router.push('/dashboard')
      else if (step === 'verify_email') goEmail()
      else if (step === 'verify_phone') setPhase('phone')
      else if (step === 'choose_sport') setPhase('sport')
    }).catch(() => {})
  }, [])

  async function goEmail() {
    setPhase('email')
    if (!emailCodeSent) { await sendEmailCode() }
  }

  async function sendEmailCode() {
    setError(''); setNote('')
    try {
      const r = await api.post('/auth/send-email-code')
      setEmailCodeSent(true)
      setNote(r.data.already_verified ? 'Email already verified.' : r.data.message || 'Code sent.')
      if (r.data.already_verified) setPhase('phone')
    } catch (err: any) { setError(err.response?.data?.detail || 'Could not send the code.') }
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const res = await api.post('/auth/register', form)
      localStorage.setItem('access_token', res.data.access_token)
      localStorage.setItem('refresh_token', res.data.refresh_token)
      const status = await api.get('/onboarding/status')
      setChoosable(status.data.choosable_sports || []); setMaxSports(status.data.max_sports || 1); setTier(status.data.tier || 'trial')
      await goEmail()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed')
    } finally { setLoading(false) }
  }

  async function verifyEmail() {
    setLoading(true); setError('')
    try {
      await api.post('/auth/verify-email', { code: emailCode.trim() })
      setNote(''); setPhase('phone')
    } catch (err: any) { setError(err.response?.data?.detail || 'Invalid code.') }
    finally { setLoading(false) }
  }

  async function sendPhoneCode() {
    setLoading(true); setError(''); setNote('')
    try {
      const r = await api.post('/auth/send-phone-code', { phone })
      setPhoneSent(true); setNote(r.data.message || 'Code sent.')
    } catch (err: any) { setError(err.response?.data?.detail || 'Could not send the text.') }
    finally { setLoading(false) }
  }

  async function verifyPhone() {
    setLoading(true); setError('')
    try {
      await api.post('/auth/verify-phone', { code: phoneCode.trim() })
      setNote(''); setPhase('sport')
    } catch (err: any) { setError(err.response?.data?.detail || 'Invalid code.') }
    finally { setLoading(false) }
  }

  function toggleSport(v: string) {
    setError('')
    setPicked(prev => {
      if (prev.includes(v)) return prev.filter(s => s !== v)
      if (prev.length >= maxSports) {
        if (maxSports === 1) return [v]
        setError(`Your ${tier} plan includes ${maxSports} sports. Deselect one to change.`)
        return prev
      }
      return [...prev, v]
    })
  }

  async function chooseSport() {
    if (picked.length === 0) { setError('Pick your sport to continue.'); return }
    setLoading(true); setError('')
    try {
      await api.post('/onboarding/sports', { sports: picked })
      router.push('/dashboard')
    } catch (err: any) { setError(err.response?.data?.detail || 'Could not save your sport.') }
    finally { setLoading(false) }
  }

  const heading = phase === 'register' ? 'Start your 14-day free trial'
    : phase === 'email' ? 'Verify your email'
    : phase === 'phone' ? 'Verify your phone'
    : 'Choose your sport'

  const Steps = () => (
    <div className="flex items-center justify-center gap-2 mb-6">
      {(['register', 'email', 'phone', 'sport'] as Phase[]).map((p, i) => {
        const order = ['register', 'email', 'phone', 'sport']
        const done = order.indexOf(phase) > i
        const active = phase === p
        return <div key={p} style={{ width: 34, height: 4, borderRadius: 2, background: done || active ? '#2d8c40' : 'rgba(255,255,255,0.12)' }} />
      })}
    </div>
  )

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center py-12">
      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <h1 className="text-3xl font-bold text-brand-400">CoachLenz</h1>
          <p className="text-gray-400 mt-2">{heading}</p>
        </div>
        <Steps />

        {error && <div className="text-red-400 text-sm bg-red-400/10 rounded p-3 mb-3">{error}</div>}
        {note && <div className="text-brand-400 text-sm bg-brand-400/10 rounded p-3 mb-3">{note}</div>}

        {phase === 'register' && (
          <form onSubmit={handleRegister} className="card space-y-4">
            <div><label className="label">Your Name</label><input className="input" value={form.name} onChange={set('name')} required /></div>
            <div><label className="label">Email</label><input type="email" className="input" value={form.email} onChange={set('email')} required /></div>
            <div><label className="label">Password</label><input type="password" className="input" value={form.password} onChange={set('password')} required minLength={8} /></div>
            <div><label className="label">School / Organization Name</label><input className="input" value={form.org_name} onChange={set('org_name')} required /></div>
            {form.referral_code && <div><label className="label">Referral Code</label><input className="input bg-gray-700" value={form.referral_code} readOnly /></div>}
            <button type="submit" disabled={loading} className="btn-primary w-full">{loading ? 'Creating account...' : 'Start Free Trial'}</button>
            <p className="text-center text-sm text-gray-400">Already have an account? <Link href="/login" className="text-brand-400 hover:underline">Sign in</Link></p>
            <p className="text-center text-xs text-gray-500">By signing up you agree to our <Link href="/terms" className="underline">Terms</Link> and <Link href="/privacy" className="underline">Privacy Policy</Link></p>
          </form>
        )}

        {phase === 'email' && (
          <div className="card space-y-4">
            <p className="text-gray-400 text-sm">Enter the 6-digit code we emailed to <span className="text-gray-200">{form.email || 'your email'}</span>.</p>
            <input className="input text-center tracking-[0.4em] text-lg" value={emailCode} onChange={e => setEmailCode(e.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="000000" inputMode="numeric" />
            <button onClick={verifyEmail} disabled={loading || emailCode.length !== 6} className="btn-primary w-full">{loading ? 'Verifying...' : 'Verify Email'}</button>
            <button onClick={sendEmailCode} className="text-center text-sm text-brand-400 hover:underline w-full">Resend code</button>
          </div>
        )}

        {phase === 'phone' && (
          <div className="card space-y-4">
            {!phoneSent ? (
              <>
                <p className="text-gray-400 text-sm">Add your mobile number for verification. We&apos;ll text you a code.</p>
                <input className="input" value={phone} onChange={e => setPhone(e.target.value)} placeholder="(555) 123-4567" inputMode="tel" />
                <button onClick={sendPhoneCode} disabled={loading || phone.replace(/\D/g, '').length < 10} className="btn-primary w-full">{loading ? 'Sending...' : 'Send Code'}</button>
              </>
            ) : (
              <>
                <p className="text-gray-400 text-sm">Enter the 6-digit code we texted to <span className="text-gray-200">{phone}</span>.</p>
                <input className="input text-center tracking-[0.4em] text-lg" value={phoneCode} onChange={e => setPhoneCode(e.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="000000" inputMode="numeric" />
                <button onClick={verifyPhone} disabled={loading || phoneCode.length !== 6} className="btn-primary w-full">{loading ? 'Verifying...' : 'Verify Phone'}</button>
                <button onClick={() => { setPhoneSent(false); setPhoneCode('') }} className="text-center text-sm text-brand-400 hover:underline w-full">Change number</button>
              </>
            )}
          </div>
        )}

        {phase === 'sport' && (
          <div className="card space-y-4">
            <p className="text-gray-400 text-sm">
              Your <span className="text-gray-200">{tier}</span> plan includes <span className="text-brand-400 font-semibold">{maxSports}</span> sport{maxSports !== 1 ? 's' : ''}.
              This <span className="text-gray-200">locks in</span> once you continue, and everything you analyze stays tied to it.
            </p>
            <div className="space-y-2">
              {choosable.map(s => {
                const on = picked.includes(s.value)
                return (
                  <button key={s.value} type="button" onClick={() => toggleSport(s.value)}
                    className="w-full flex items-center justify-between rounded-lg px-4 py-3 text-left transition"
                    style={{ background: on ? 'rgba(26,92,42,0.4)' : 'rgba(255,255,255,0.04)', border: on ? '1px solid #2d8c40' : '1px solid rgba(255,255,255,0.1)', color: '#f8f6f0' }}>
                    <span className="font-semibold">{s.label}</span>
                    <span style={{ color: on ? '#2d8c40' : '#7a7a6e', fontSize: 13 }}>{on ? '✓ Selected' : 'Select'}</span>
                  </button>
                )
              })}
            </div>
            <p className="text-xs text-gray-500">Selected {picked.length} of {maxSports}.</p>
            <button onClick={chooseSport} disabled={loading || picked.length === 0} className="btn-primary w-full">{loading ? 'Locking in...' : 'Continue'}</button>
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
