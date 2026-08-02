'use client'
/**
 * Live Game report examples — gated behind auth (client-side, same as every other
 * app page). The sample reports are bundled in reports.ts and rendered by the
 * [sport] route in an isolated iframe, so they are never served from public/.
 */
import { useEffect, type CSSProperties } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { EXAMPLES, type ExampleKey } from './reports'

const wrap: CSSProperties = { minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }
const inner: CSSProperties = { maxWidth: 720, margin: '0 auto', padding: '44px 20px 60px' }

export default function ExamplesIndex() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  if (isLoading || !user) return null

  const keys = Object.keys(EXAMPLES) as ExampleKey[]
  const sub: Record<ExampleKey, string> = {
    football: '9 sections · run-gap & pass field heat maps · adjustments',
    flag: 'rush-lane & pass field heat maps · opponent tendencies',
    basketball: 'foul-trouble alert · shot chart · shot-location court · season trend',
  }

  return (
    <div style={wrap}>
      <div style={inner}>
        <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--gold)', display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--gold)', boxShadow: '0 0 0 4px rgba(201,168,76,0.12)' }} /> Live Game Logger · Sample Reports
        </div>
        <h1 style={{ fontSize: 'clamp(26px,5vw,36px)', margin: '0 0 8px', fontWeight: 850, letterSpacing: '-0.02em' }}>What a Live Game report looks like</h1>
        <p style={{ color: 'var(--text3)', fontSize: 14, margin: '0 0 28px', maxWidth: '60ch' }}>
          Chart a game from the sideline and CoachLenz generates a coordinator-style breakdown with heat maps. Here is one full-game report per sport, so you know what you are working toward before you log your first game.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {keys.map(k => (
            <Link key={k} href={`/examples/${k}`} style={{
              display: 'flex', alignItems: 'center', gap: 16, textDecoration: 'none', color: 'var(--text)',
              background: 'var(--bg2)', border: '1px solid var(--gold-border)', borderRadius: 12, padding: '18px 20px',
            }}>
              <span style={{ fontSize: 30, width: 44, textAlign: 'center', flex: 'none' }}>{EXAMPLES[k].emoji}</span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: 'block', fontSize: 17, fontWeight: 800, letterSpacing: '-0.01em' }}>{EXAMPLES[k].label}</span>
                <span style={{ display: 'block', fontSize: 13, color: 'var(--text3)', marginTop: 3 }}>{sub[k]}</span>
              </span>
              <span style={{ color: 'var(--text3)', fontSize: 20, flex: 'none' }}>→</span>
            </Link>
          ))}
        </div>
        <p style={{ marginTop: 26, fontSize: 12, color: 'var(--text3)', borderTop: '1px solid var(--border2)', paddingTop: 16, lineHeight: 1.6 }}>
          Illustrative samples built from representative game data to show the report format. Your real reports are generated from the plays you log in the Live Game Logger.
        </p>
        <div style={{ marginTop: 20, display: 'flex', gap: 18 }}>
          <Link href="/dashboard" style={{ fontSize: 13, color: 'var(--text3)' }}>← dashboard</Link>
          <Link href="/live" style={{ fontSize: 13, color: 'var(--green3)' }}>Start a live game →</Link>
        </div>
      </div>
    </div>
  )
}
