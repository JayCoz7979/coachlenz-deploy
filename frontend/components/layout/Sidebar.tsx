'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import { LayoutDashboard, Users, Film, FileText, Settings, Trophy, UserCircle, Share2, ShieldCheck, LogOut } from 'lucide-react'
import clsx from 'clsx'

export default function Sidebar() {
  const pathname = usePathname()
  const { user, logout } = useAuth()

  const links = [
    { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { href: '/teams', label: 'Teams', icon: Users },
    { href: '/games', label: 'Games', icon: Film },
    { href: '/reports', label: 'Reports', icon: FileText },
    { href: '/teams-of-month', label: 'Teams of the Month', icon: Trophy },
    { href: '/referrals', label: 'Referrals', icon: Share2 },
    ...(user?.organization?.has_coach_tenure_access ? [{ href: '/coaches', label: 'Coach Tenure', icon: UserCircle }] : []),
    ...(user?.organization?.admin_level ? [{ href: '/admin', label: 'Admin', icon: ShieldCheck }] : []),
    { href: '/settings/billing', label: 'Settings', icon: Settings },
  ]

  return (
    <aside className="w-60 bg-gray-900 border-r border-gray-800 flex flex-col h-screen sticky top-0">
      <div className="p-5 border-b border-gray-800">
        <Link href="/dashboard" className="text-xl font-bold text-brand-400">CoachLenz</Link>
        {user?.organization?.is_trial && (
          <div className="mt-2 text-xs text-yellow-400 bg-yellow-400/10 rounded px-2 py-1">
            Trial — {user.organization.trial_days_remaining}d left
          </div>
        )}
      </div>
      <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
        {links.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={clsx(
              'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
              pathname?.startsWith(href)
                ? 'bg-brand-500/20 text-brand-400'
                : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800'
            )}
          >
            <Icon size={18} />
            {label}
          </Link>
        ))}
      </nav>
      <div className="p-3 border-t border-gray-800">
        <div className="text-xs text-gray-500 mb-2 truncate">{user?.email}</div>
        <button onClick={logout} className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-100 w-full px-3 py-2 rounded-lg hover:bg-gray-800 transition-colors">
          <LogOut size={16} /> Sign Out
        </button>
        <div className="mt-3 text-xs text-gray-600 text-center">
          Powered by <a href="https://cosbyaisolutions.com" className="text-brand-500 hover:underline" target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
        </div>
      </div>
    </aside>
  )
}
