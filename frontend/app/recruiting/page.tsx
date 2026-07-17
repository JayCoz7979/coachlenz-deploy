'use client'
/**
 * Recruiting board - recruit intel cards.
 * There is no backend recruiting endpoint yet, so this renders the approved demo
 * layout as a clearly labeled PREVIEW. The sample recruits are framed as examples
 * of the layout a connected recruiting pipeline will populate, never as real data.
 * Trial/coach tiers see an upgrade call-to-action (Athletic Dept plans and up).
 */
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import OSShell from '@/components/os/OSShell'

interface Recruit {
  name: string
  pos: string
  a: string
  b: string
  cLabel: string
  cValue: string
  fill: number
  tags: { text: string; cls: string }[]
}

const SAMPLE_RECRUITS: Recruit[] = [
  {
    name: 'Darius M. - QB',
    pos: 'Class of 2026 · Athens, AL · Football',
    a: '6\'2"', b: '195 lbs', cLabel: '40yd', cValue: '4.61', fill: 92,
    tags: [{ text: 'Priority', cls: 'tg' }, { text: 'Film: A', cls: 'tgo' }, { text: 'D1 Proj', cls: 'tw' }],
  },
  {
    name: 'Keion T. - WR',
    pos: 'Class of 2026 · Huntsville, AL · Football',
    a: '6\'0"', b: '172 lbs', cLabel: '40yd', cValue: '4.42', fill: 87,
    tags: [{ text: 'Priority', cls: 'tg' }, { text: 'Film: A-', cls: 'tgo' }, { text: 'Offer Pending', cls: 'tq' }],
  },
  {
    name: 'Aaliyah C. - Libero',
    pos: 'Class of 2027 · Madison, AL · Volleyball',
    a: '5\'5"', b: 'Volleyball', cLabel: '', cValue: 'Dig: .94', fill: 89,
    tags: [{ text: 'Priority', cls: 'tg' }, { text: 'Film: A', cls: 'tgo' }, { text: 'D2 Proj', cls: 'tw' }],
  },
]

const GATED_TIERS = ['trial', 'coach']

export default function RecruitingPage() {
  const { user } = useAuth()
  const tier = user?.organization?.subscription_tier || ''
  const gated = GATED_TIERS.includes(tier)

  return (
    <OSShell title="Recruiting">
      <div className="sec-title" style={{ marginBottom: 16 }}>🎯 Recruiting Intelligence</div>

      <div className="ai-box" style={{ marginTop: 0, marginBottom: 16 }}>
        <strong>Recruiting board preview</strong> - connect your recruiting pipeline to populate.
        Available on Athletic Dept plans.
      </div>

      {gated && (
        <div className="tier-lock" style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, color: 'var(--text2)', marginBottom: 10 }}>
            The recruiting board unlocks on Athletic Dept plans and up. Upgrade to connect your pipeline
            and populate this board with your real recruits.
          </div>
          <Link href="/settings/billing" className="tl-btn" style={{ textDecoration: 'none' }}>Upgrade →</Link>
        </div>
      )}

      <div className="rec-g">
        {SAMPLE_RECRUITS.map((r, i) => (
          <div className="rec" key={i}>
            <div className="rec-name">{r.name}</div>
            <div className="rec-pos">{r.pos}</div>
            <div style={{ display: 'flex', gap: 10, marginBottom: 7, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 10, color: 'var(--text2)' }}><strong style={{ color: 'var(--text)' }}>{r.a}</strong></span>
              <span style={{ fontSize: 10, color: 'var(--text2)' }}><strong style={{ color: 'var(--text)' }}>{r.b}</strong></span>
              <span style={{ fontSize: 10, color: 'var(--text2)' }}>
                <strong style={{ color: 'var(--text)' }}>{r.cValue}</strong>{r.cLabel ? ' ' + r.cLabel : ''}
              </span>
            </div>
            <div className="rec-bar"><div className="rec-fill" style={{ width: r.fill + '%' }} /></div>
            <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
              {r.tags.map((t, j) => (
                <span className={'tag ' + t.cls} key={j}>{t.text}</span>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="powered">Powered by <a href="https://cosbyaisolutions.com" target="_blank" rel="noreferrer">Cosby AI Solutions</a></div>
    </OSShell>
  )
}
