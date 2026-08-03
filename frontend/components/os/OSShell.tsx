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
      { href: '/live', label: 'Live Game', icon: '⚡', badge: 'New', badgeKind: 'gold' },
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
  const { user, isLoading, fetchMe, logout } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  const [sports, setSports] = useState<string[]>([])
  const [navOpen, setNavOpen] = useState(false)

  useEffect(() => { fetchMe() }, [])
  // Close the mobile nav drawer whenever the route changes (a nav tap navigated).
  useEffect(() => { setNavOpen(false) }, [pathname])
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
    <div className={'clz' + (navOpen ? ' nav-open' : '')}>
      {/* Mobile drawer backdrop (hidden on desktop; tap to close) */}
      <div className="nav-backdrop" onClick={() => setNavOpen(false)} aria-hidden="true" />
      {/* SIDEBAR */}
      <nav className={'sidebar' + (navOpen ? ' open' : '')}>
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
                  onClick={() => setNavOpen(false)}
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
          <div className="signed-as">{user.email}</div>
          <button className="tour-btn" onClick={() => logout()}>Sign out</button>
        </div>
      </nav>

      {/* MAIN */}
      <div className="main">
        <div className="topbar">
          {/* Hamburger — mobile only (CSS hides it on desktop) */}
          <button className="menu-btn" onClick={() => setNavOpen(o => !o)} aria-label="Open menu" aria-expanded={navOpen}>
            <span /><span /><span />
          </button>
          <div className="page-ttl">{title}</div>
          {/* The org's plan sports. These are indicators, not a switcher (content
              is not sport-scoped yet), so they are non-interactive spans rather
              than buttons that look clickable but do nothing. */}
          <div className="sport-tabs">
            {shownTabs.map(s => (
              <span key={s.key} className={'stab' + (s.key === activeSport ? ' active' : '')} style={{ cursor: 'default' }}>
                {s.emoji} {s.label}
              </span>
            ))}
          </div>
        </div>
        <div className="page">{children}</div>
      </div>
    </div>
  )
}
