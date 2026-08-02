'use client'
/**
 * Renders a single sample Live Game report in an isolated iframe (srcDoc), so its
 * inline styles/scripts never touch the app. Gated behind auth like the index.
 */
import { useEffect } from 'react'
import { useRouter, useParams } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { EXAMPLES, type ExampleKey } from '../reports'

export default function ExampleReport() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const params = useParams()
  const key = String(params.sport) as ExampleKey

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  if (isLoading || !user) return null

  const ex = EXAMPLES[key]
  if (!ex) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12 }}>
        <div>That example report was not found.</div>
        <Link href="/examples" style={{ color: 'var(--green3)' }}>← all examples</Link>
      </div>
    )
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 16px', borderBottom: '1px solid var(--border2)', background: 'var(--bg)', flex: 'none' }}>
        <Link href="/examples" style={{ color: 'var(--text3)', fontSize: 13, textDecoration: 'none' }}>← examples</Link>
        <span style={{ color: 'var(--text2)', fontSize: 13, fontWeight: 700 }}>{ex.emoji} {ex.label} — sample report</span>
      </div>
      <iframe
        title={`${ex.label} sample report`}
        srcDoc={ex.html}
        style={{ flex: 1, width: '100%', border: 0 }}
      />
    </div>
  )
}
