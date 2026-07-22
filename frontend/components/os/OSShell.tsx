'use client'
/**
 * OSShell — the CoachLenz analysis-OS chrome (sidebar + topbar).
 * Wraps page content in the scoped `.clz` design system (see app/os.css) so it
 * never collides with the legacy Tailwind pages. Ported from the approved demo
 * layout, wired to real auth/routing.
 */
import { ReactNode, useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { SPORTS, SPORT_META } from '@/lib/sports'
// Static import so the asset is emitted to /_next/static/media (served in the
// standalone build); the public/ folder is not bundled with output:'standalone'.
import logo from '../../public/coachlenz-logo.png'

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: 'Analysis',
    items: [
      { href: '/dashboard', label: 'Dashboard', icon: '📊' },
      { href: '/games', label: 'Film Room', icon: '🎬' },
      { href: '/tendencies', label: 'Tendency Engine', icon: '🧠' },
      { href: '/reports', label: 'Scout Reports', icon: '📋' },
    ],
  },
  {
    section: 'Intelligence',
    items: [{ href: '/intel', label: 'Film Intelligence', icon: '🔬', badge: 'Live', badgeKind: 'g' }],
  },
  {
    section: 'Roster',
    items: [
      { href: '/players', label: 'Player Grades', icon: '👤' },
      { href: '/recruiting', label: 'Recruiting', icon: '🎯', badge: 'New', badgeKind: 'gold' },
    ],
  },
  {
    section: 'Staff',
    items: [
      { href: '/messaging', label: 'Staff Messaging', icon: '💬' },
      { href: '/games/upload', label: 'Upload Film', icon: '⬆️' },
    ],
  },
  {
    section: 'Account',
    items: [
      { href: '/settings/connections', label: 'Connected Accounts', icon: '🔗' },
      { href: '/settings/billing', label: 'Plans & Pricing', icon: '💳' },
      { href: '/referrals', label: 'Referrals', icon: '🎁' },
      { href: '/admin', label: 'Admin', icon: '🛡️', requiresAdmin: true },
    ],
  },
]

interface NavItem {
  href: string
  label: string
  icon: string
  badge?: string
  badgeKind?: 'g' | 'gold' | 'r'
  requiresAdmin?: boolean
}

// Sport tabs, sourced from the single sports list (mirrors backend CHOOSABLE_SPORTS).
const ALL_SPORTS = SPORTS.map(k => ({ key: k as string, ...SPORT_META[k] }))

const TIER_LABELS: Record<string, string> = {
  trial: 'Trial', coach: 'Coach', athletic_dept: 'Athletic Dept', district: 'District', enterprise: 'Enterprise',
}

export default function OSShell({ title, children }: { title: string; children: ReactNode }) {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  const [sports, setSports] = useState<string[]>([])

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => {
    if (!user) return
    api.get('/onboarding/status')
      .then(s => setSports((s.data?.chosen_sports || []).map((x: string) => String(x).toLowerCase())))
      .catch(() => {})
  }, [user])

  if (isLoading || !user) return null

  const org = user.organization
  const isAdmin = !!org.admin_level
  const tabs = ALL_SPORTS.filter(s => sports.includes(s.key))
  const shownTabs = tabs.length ? tabs : [ALL_SPORTS[0]]
  const activeSport = shownTabs[0]?.key || 'football'

  const isActive = (href: string) =>
    href === '/dashboard' ? pathname === '/dashboard' : pathname === href || pathname.startsWith(href + '/')

  return (
    <div className="clz">
      {/* SIDEBAR */}
      <nav className="sidebar">
        <div className="logo-block">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={logo.src} alt="CoachLenz"
               style={{ width: '100%', maxWidth: 210, height: 'auto', display: 'block' }} />
        </div>
        {NAV.map(group => {
          const items = group.items.filter(i => !i.requiresAdmin || isAdmin)
          if (!items.length) return null
          return (
            <div className="nav-sec" key={group.section}>
              <div className="nav-lbl">{group.section}</div>
              {items.map(item => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={'ni' + (isActive(item.href) ? ' active' : '')}
                >
                  <span className="ni-icon">{item.icon}</span>
                  {item.label}
                  {item.badge && (
                    <span className={'ni-badge nb-' + (item.badgeKind || 'g')}>{item.badge}</span>
                  )}
                </Link>
              ))}
            </div>
          )
        })}
        <div className="sidebar-foot">
          <div className="plan-chip">
            <div className="pn">{TIER_LABELS[org.subscription_tier] || 'CoachLenz'} Plan</div>
            <div className="pi">
              {org.is_trial ? `Trial · ${org.trial_days_remaining} days left` : org.name}
            </div>
          </div>
        </div>
      </nav>

      {/* MAIN */}
      <div className="main">
        <div className="topbar">
          <div className="page-ttl">{title}</div>
          <div className="sport-tabs">
            {shownTabs.map(s => (
              <button key={s.key} className={'stab' + (s.key === activeSport ? ' active' : '')}>
                {s.emoji} {s.label}
              </button>
            ))}
          </div>
        </div>
        <div className="page">{children}</div>
      </div>
    </div>
  )
}
