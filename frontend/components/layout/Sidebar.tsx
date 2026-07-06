'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import {
  LayoutDashboard, Users, Film, FileText, Settings,
  Trophy, UserCircle, Share2, ShieldCheck, LogOut, Upload, Link2, Target,
} from 'lucide-react'

const NAV_SECTIONS = [
  {
    label: 'Film Room',
    items: [
      { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
      { href: '/games', label: 'Film Library', icon: Film },
      { href: '/games/upload?tab=url', label: 'Import Film', icon: Upload },
      { href: '/scout', label: 'Scout Opponent', icon: Target },
      { href: '/reports', label: 'Reports', icon: FileText },
    ],
  },
  {
    label: 'Organization',
    items: [
      { href: '/teams', label: 'Teams', icon: Users },
      { href: '/coaches', label: 'Coach Tenure', icon: UserCircle, requiresTenure: true },
      { href: '/teams-of-month', label: 'Teams of Month', icon: Trophy },
    ],
  },
  {
    label: 'Account',
    items: [
      { href: '/settings/connections', label: 'Connected Accounts', icon: Link2 },
      { href: '/referrals', label: 'Referrals', icon: Share2 },
      { href: '/admin', label: 'Admin', icon: ShieldCheck, requiresAdmin: true },
      { href: '/settings/billing', label: 'Settings', icon: Settings },
    ],
  },
]

const TIER_LABELS: Record<string, string> = {
  trial: 'Trial',
  coach: 'Coach',
  athletic_dept: 'Athletic Dept',
  district: 'District',
  enterprise: 'Enterprise',
}

export default function Sidebar() {
  const pathname = usePathname()
  const { user, logout } = useAuth()

  return (
    <aside
      style={{ width: 240, flexShrink: 0, background: 'var(--bg2)', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', height: '100vh', position: 'sticky', top: 0, overflowY: 'auto' }}
    >
      {/* Logo block */}
      <div style={{ padding: '16px 14px 12px', borderBottom: '1px solid var(--border)' }}>
        <Link href="/dashboard" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
          <div style={{
            width: 36, height: 36, borderRadius: 9, flexShrink: 0,
            background: 'linear-gradient(135deg, var(--green), var(--green2))',
            boxShadow: '0 4px 14px rgba(45,80,22,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <span style={{ fontFamily: 'var(--font-syne,sans-serif)', fontSize: 13, fontWeight: 800, color: '#fff' }}>CL</span>
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-syne,sans-serif)', fontSize: 16, fontWeight: 800, color: '#fff', lineHeight: '1.2' }}>CoachLenz</div>
            <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 1 }}>AI Film Analyst OS</div>
          </div>
        </Link>
        {user?.organization?.is_trial && (
          <div style={{
            marginTop: 10, background: 'var(--goldl)', border: '1px solid rgba(201,168,76,0.25)',
            borderRadius: 7, padding: '5px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          }}>
            <span style={{ fontFamily: 'var(--font-syne,sans-serif)', fontSize: 11, fontWeight: 700, color: 'var(--gold)' }}>Trial Active</span>
            <span style={{ fontFamily: 'var(--font-dm-mono,monospace)', fontSize: 10, color: 'var(--text3)' }}>
              {user.organization.trial_days_remaining}d left
            </span>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav style={{ flex: 1, padding: '8px 8px', overflowY: 'auto' }}>
        {NAV_SECTIONS.map(section => {
          const visible = section.items.filter(item => {
            if ((item as any).requiresTenure && !user?.organization?.has_coach_tenure_access) return false
            if ((item as any).requiresAdmin && !user?.organization?.admin_level) return false
            return true
          })
          if (!visible.length) return null
          return (
            <div key={section.label} style={{ marginBottom: 16 }}>
              <div style={{
                fontSize: 10, fontWeight: 700, color: 'var(--text3)',
                textTransform: 'uppercase', letterSpacing: '0.09em',
                padding: '0 8px', marginBottom: 3,
                fontFamily: 'var(--font-syne,sans-serif)',
              }}>
                {section.label}
              </div>
              {visible.map(({ href, label, icon: Icon }) => {
                const base = href.split('?')[0]
                const active = pathname === base || (base !== '/dashboard' && (pathname || '').startsWith(base))
                return (
                  <Link
                    key={href}
                    href={href}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 9,
                      padding: '8px 10px', borderRadius: 8, marginBottom: 1,
                      fontSize: 13, cursor: 'pointer', transition: 'all 0.12s',
                      border: `1px solid ${active ? 'rgba(45,80,22,0.3)' : 'transparent'}`,
                      color: active ? 'var(--green3)' : 'var(--text2)',
                      background: active ? 'linear-gradient(135deg, var(--greenl), var(--greenl2))' : 'transparent',
                      textDecoration: 'none',
                    }}
                  >
                    <Icon size={16} style={{ flexShrink: 0 }} />
                    {label}
                  </Link>
                )
              })}
            </div>
          )
        })}
      </nav>

      {/* Footer */}
      <div style={{ marginTop: 'auto', padding: '12px 14px', borderTop: '1px solid var(--border)' }}>
        {user?.organization && (
          <div style={{
            background: 'var(--greenl2)', border: '1px solid rgba(45,80,22,0.25)',
            borderRadius: 9, padding: '10px 12px', marginBottom: 8,
          }}>
            <div style={{ fontFamily: 'var(--font-syne,sans-serif)', fontSize: 12, fontWeight: 700, color: 'var(--green3)' }}>
              {TIER_LABELS[user.organization.subscription_tier] || user.organization.subscription_tier}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 2 }}>{user.organization.name}</div>
          </div>
        )}
        <div style={{ fontSize: 11, color: 'var(--text3)', marginBottom: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {user?.email}
        </div>
        <button
          onClick={logout}
          style={{
            display: 'flex', alignItems: 'center', gap: 8, fontSize: 12,
            color: 'var(--text3)', background: 'transparent', border: 'none',
            cursor: 'pointer', padding: '6px 4px', borderRadius: 6, width: '100%',
          }}
        >
          <LogOut size={14} /> Sign Out
        </button>
        <div style={{ marginTop: 8, fontSize: 10, color: 'var(--text3)', textAlign: 'center' }}>
          Powered by <a href="https://cosbyaisolutions.com" style={{ color: 'var(--green3)' }} target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
        </div>
      </div>
    </aside>
  )
}
