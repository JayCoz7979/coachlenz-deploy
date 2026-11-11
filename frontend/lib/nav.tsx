// Single source of truth for the app's left-nav. BOTH chromes render from this:
// the legacy `components/layout/Sidebar.tsx` (lucide icons) and the analysis-OS
// `components/os/OSShell.tsx` (emoji icons, badges). Pages are split across the
// two shells, so before this existed each shell only listed a slice of the app and
// clicking certain items stranded the user in a shell whose nav was missing half the
// sections. Keeping one list here means every section is reachable from anywhere,
// no matter which shell the current page happens to use, and the two lists can
// never drift apart again.
import type { LucideIcon } from 'lucide-react'
import {
  LayoutDashboard, Film, Upload, Zap, Target, BarChart3, FileText, FlaskConical,
  Users, ClipboardList, Award, UserPlus, MessageSquare, Link2, CreditCard, Share2,
  UserCircle, ShieldCheck, ShieldAlert, Settings,
} from 'lucide-react'

export interface NavEntry {
  href: string
  label: string
  icon: LucideIcon           // rendered by the legacy Sidebar
  emoji: string              // rendered by OSShell
  badge?: string
  badgeKind?: 'g' | 'gold' | 'r'
  requiresAdmin?: boolean
  requiresPermission?: string
  requiresAdTier?: boolean
  requiresTenure?: boolean
}

export interface NavSection { label: string; items: NavEntry[] }

export const NAV_SECTIONS: NavSection[] = [
  {
    label: 'Film Room',
    items: [
      { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, emoji: '📊' },
      { href: '/games', label: 'Film Room', icon: Film, emoji: '🎬' },
      { href: '/games/upload?tab=url', label: 'Import Film', icon: Upload, emoji: '⬆️' },
      { href: '/live', label: 'Live Game', icon: Zap, emoji: '⚡', badge: 'New', badgeKind: 'gold' },
      { href: '/scout', label: 'Scout Opponent', icon: Target, emoji: '🎯' },
      { href: '/tendencies', label: 'Tendency Engine', icon: BarChart3, emoji: '🧠' },
      { href: '/reports', label: 'Reports', icon: FileText, emoji: '📋' },
      { href: '/intel', label: 'Film Intelligence', icon: FlaskConical, emoji: '🔬', badge: 'Live', badgeKind: 'g' },
    ],
  },
  {
    label: 'Roster',
    items: [
      { href: '/teams', label: 'Teams', icon: Users, emoji: '👥' },
      { href: '/roster', label: 'Rosters', icon: ClipboardList, emoji: '🧾' },
      { href: '/players', label: 'Player Grades', icon: Award, emoji: '🏅' },
      { href: '/recruiting', label: 'Recruiting', icon: Target, emoji: '🧭', badge: 'New', badgeKind: 'gold' },
      { href: '/staff', label: 'Staff', icon: UserPlus, emoji: '🧑‍🏫', requiresPermission: 'can_invite_staff' },
    ],
  },
  {
    label: 'Communication',
    items: [
      { href: '/messaging', label: 'Staff Messaging', icon: MessageSquare, emoji: '💬' },
    ],
  },
  {
    label: 'Account',
    items: [
      { href: '/ad', label: 'Usage Dashboard', icon: BarChart3, emoji: '📈', requiresAdTier: true },
      { href: '/settings/connections', label: 'Connected Accounts', icon: Link2, emoji: '🔗' },
      { href: '/settings/billing', label: 'Plans & Pricing', icon: CreditCard, emoji: '💳' },
      { href: '/referrals', label: 'Referrals', icon: Share2, emoji: '🎁' },
      { href: '/coaches', label: 'Coach Tenure', icon: UserCircle, emoji: '🧑‍💼', requiresAdmin: true },
      { href: '/admin', label: 'Admin', icon: ShieldCheck, emoji: '🛡️', requiresAdmin: true },
      { href: '/admin/privacy-requests', label: 'Privacy Requests', icon: ShieldAlert, emoji: '🔒', requiresAdmin: true },
      { href: '/settings', label: 'Settings', icon: Settings, emoji: '⚙️' },
    ],
  },
]

// One gating predicate shared by both shells, so an item that is hidden for a user
// in one chrome is hidden in the other too. Matches the legacy Sidebar's original
// rules (admin / permission / AD-tier / coach-tenure).
export function navItemVisible(item: NavEntry, user: any): boolean {
  if (item.requiresTenure && !user?.organization?.has_coach_tenure_access) return false
  if (item.requiresAdmin && !user?.organization?.admin_level) return false
  if (item.requiresPermission && !user?.permissions?.includes(item.requiresPermission)) return false
  if (item.requiresAdTier && !['athletic_dept', 'district'].includes(user?.organization?.subscription_tier || '')) return false
  return true
}
