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
// Shared nav source of truth, rendered by both OSShell and the legacy Sidebar, so
// every section is reachable from whichever shell the current page uses.
import { NAV_SECTIONS, navItemVisible } from '@/lib/nav'

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
  const tabs = ALL_SPORTS.filter(s => sports.includes(s.key))
  // Show ONLY the org's actually-chosen sport(s). Never invent a default (the old
  // code fell back to Football, which was wrong for a basketball coach). If the sport
  // is not known yet, show nothing rather than a guess.
  const shownTabs = tabs
  const activeSport = shownTabs[0]?.key || ''

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
        {NAV_SECTIONS.map(group => {
          const items = group.items.filter(i => navItemVisible(i, user))
          if (!items.length) return null
          return (
            <div className="nav-sec" key={group.label}>
              <div className="nav-lbl">{group.label}</div>
              {items.map(item => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={'ni' + (isActive(item.href) ? ' active' : '')}
                  onClick={() => setNavOpen(false)}
                >
                  <span className="ni-icon">{item.emoji}</span>
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
          {shownTabs.length > 0 && (
            <div className="sport-tabs">
              {shownTabs.map(s => (
                <span key={s.key} className={'stab' + (s.key === activeSport ? ' active' : '')} style={{ cursor: 'default' }}>
                  {s.emoji} {s.label}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="page">{children}</div>
      </div>
    </div>
  )
}
