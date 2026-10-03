'use client'
import { useState } from 'react'
import { publicApi } from '@/lib/api'

export default function PrivacyDeleteRequestPage() {
  const [form, setForm] = useState({
    request_type: 'deletion',
    requester_name: '',
    requester_email: '',
    relationship: 'parent',
    student_name: '',
    school_or_org: '',
    student_details: '',
    details: '',
  })
  const [submitting, setSubmitting] = useState(false)
  const [reference, setReference] = useState<string | null>(null)
  const [error, setError] = useState('')

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (!form.requester_name.trim() || !form.requester_email.trim() || !form.student_name.trim()) {
      setError('Please fill in your name, your email, and the student’s name.')
      return
    }
    setSubmitting(true)
    try {
      const res = await publicApi.post('/privacy/requests', form)
      setReference(res.data.reference)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Something went wrong. Please email privacy@coachlenz.com.')
    } finally {
      setSubmitting(false)
    }
  }

  if (reference) {
    return (
      <div className="min-h-screen bg-gray-950 px-6 py-16 max-w-2xl mx-auto text-gray-200">
        <h1 className="text-2xl font-bold mb-4">Request received</h1>
        <p className="text-gray-300 mb-4">
          Thank you. We received your request and sent a confirmation to your email. Your reference is:
        </p>
        <p className="font-mono text-brand-400 text-lg mb-6">{reference}</p>
        <p className="text-gray-400 text-sm">
          To protect students, we verify every request before acting on it, in coordination with the
          school when needed. We’ll email you when it’s complete — most requests are handled within 14 days.
          Questions? <a className="text-brand-400 hover:underline" href="mailto:privacy@coachlenz.com">privacy@coachlenz.com</a>.
        </p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-950 px-6 py-16 max-w-2xl mx-auto text-gray-200">
      <h1 className="text-2xl font-bold mb-2">Student data request</h1>
      <p className="text-gray-400 text-sm mb-8">
        A parent, guardian, or eligible student can request access to, or deletion of, a student-athlete’s
        data in CoachLenz. We verify every request before acting on it. You can also email{' '}
        <a className="text-brand-400 hover:underline" href="mailto:privacy@coachlenz.com">privacy@coachlenz.com</a>.
      </p>

      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="label">What would you like to do?</label>
          <select className="input" value={form.request_type} onChange={set('request_type')}>
            <option value="deletion">Delete the student’s data</option>
            <option value="access">Access / review the student’s data</option>
          </select>
        </div>
        <div>
          <label className="label">Your name</label>
          <input className="input" value={form.requester_name} onChange={set('requester_name')} required />
        </div>
        <div>
          <label className="label">Your email</label>
          <input type="email" className="input" value={form.requester_email} onChange={set('requester_email')} required />
        </div>
        <div>
          <label className="label">Your relationship to the student</label>
          <select className="input" value={form.relationship} onChange={set('relationship')}>
            <option value="parent">Parent</option>
            <option value="guardian">Legal guardian</option>
            <option value="eligible_student">The student (18+ or eligible)</option>
            <option value="school_official">School official</option>
            <option value="other">Other</option>
          </select>
        </div>
        <div>
          <label className="label">Student’s name</label>
          <input className="input" value={form.student_name} onChange={set('student_name')} required />
        </div>
        <div>
          <label className="label">School, team, or program</label>
          <input className="input" value={form.school_or_org} onChange={set('school_or_org')} placeholder="e.g. Lincoln High — Varsity Football" />
        </div>
        <div>
          <label className="label">Anything that helps us find the data</label>
          <input className="input" value={form.student_details} onChange={set('student_details')} placeholder="Jersey number, team, season, grad year" />
        </div>
        <div>
          <label className="label">Details (optional)</label>
          <textarea className="input" rows={4} value={form.details} onChange={set('details')} />
        </div>

        {error && <p className="text-red-400 text-sm">{error}</p>}

        <button type="submit" disabled={submitting} className="btn-primary w-full">
          {submitting ? 'Submitting…' : 'Submit request'}
        </button>
      </form>

      <footer className="mt-12 text-xs text-gray-600">
        Powered by <a href="https://cosbyaisolutions.com" className="text-brand-400 hover:underline">Cosby AI Solutions</a>
      </footer>
    </div>
  )
}
