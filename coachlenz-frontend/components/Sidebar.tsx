'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  Users,
  Calendar,
  BarChart2,
  ClipboardList,
  LogOut,
  Trophy,
} from 'lucide-react'
import { getCoach, logout } from '@/lib/auth'
import { useEffect, useState } from 'react'

const navItems = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/roster', label: 'Roster', icon: Users },
  { href: '/schedule', label: 'Schedule', icon: Calendar },
  { href: '/stats', label: 'Statistics', icon: BarChart2 },
  { href: '/practice', label: 'Practice Plans', icon: ClipboardList },
]

export default function Sidebar() {
  const pathname = usePathname()
  const [coachName, setCoachName] = useState('')

  useEffect(() => {
    const coach = getCoach()
    if (coach) setCoachName(coach.name)
  }, [])

  return (
    <aside className="w-64 min-h-screen bg-[#161616] border-r border-[#1e1e1e] flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-[#1e1e1e]">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-[#2563eb] flex items-center justify-center">
            <Trophy className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-white font-bold text-lg leading-tight">CoachLenz</h1>
            <p className="text-[#6b7280] text-xs">Sports Admin</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-4 space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon
          const isActive = pathname === item.href || pathname.startsWith(item.href + '/')
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-[#2563eb] text-white'
                  : 'text-[#9ca3af] hover:text-white hover:bg-[#1e1e1e]'
              }`}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {item.label}
            </Link>
          )
        })}
      </nav>

      {/* Coach info + logout */}
      <div className="p-4 border-t border-[#1e1e1e]">
        {coachName && (
          <div className="px-3 py-2 mb-2">
            <p className="text-[#9ca3af] text-xs">Logged in as</p>
            <p className="text-white text-sm font-medium truncate">{coachName}</p>
          </div>
        )}
        <button
          onClick={logout}
          className="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium text-[#9ca3af] hover:text-white hover:bg-[#1e1e1e] transition-colors"
        >
          <LogOut className="w-4 h-4" />
          Sign Out
        </button>
        <div className="mt-4 px-3">
          <p className="text-[#4b5563] text-xs">
            Powered by{' '}
            <a
              href="https://cosbyaisolutions.com"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#2563eb] hover:underline"
            >
              Cosby AI Solutions
            </a>
          </p>
        </div>
      </div>
    </aside>
  )
}
