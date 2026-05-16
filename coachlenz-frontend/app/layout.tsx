'use client'

import './globals.css'
import { usePathname } from 'next/navigation'
import Sidebar from '@/components/Sidebar'
import { useEffect, useState } from 'react'
import { isAuthenticated } from '@/lib/auth'
import { useRouter } from 'next/navigation'

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pathname = usePathname()
  const router = useRouter()
  const [checked, setChecked] = useState(false)

  const isLoginPage = pathname === '/login'

  useEffect(() => {
    if (!isLoginPage && !isAuthenticated()) {
      router.replace('/login')
    } else {
      setChecked(true)
    }
  }, [pathname, isLoginPage, router])

  if (isLoginPage) {
    return (
      <html lang="en">
        <head>
          <title>CoachLenz — Sign In</title>
          <meta name="viewport" content="width=device-width, initial-scale=1" />
        </head>
        <body className="bg-[#0d0d0d]">{children}</body>
      </html>
    )
  }

  if (!checked) {
    return (
      <html lang="en">
        <head>
          <title>CoachLenz</title>
        </head>
        <body className="bg-[#0d0d0d] flex items-center justify-center min-h-screen">
          <div className="text-[#6b7280] text-sm">Loading...</div>
        </body>
      </html>
    )
  }

  return (
    <html lang="en">
      <head>
        <title>CoachLenz — Sports Coaching Admin</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body className="bg-[#0d0d0d] flex min-h-screen">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <div className="p-8 min-h-screen flex flex-col">
            <div className="flex-1">{children}</div>
            <footer className="mt-12 pt-6 border-t border-[#1e1e1e]">
              <p className="text-[#4b5563] text-xs text-center">
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
            </footer>
          </div>
        </main>
      </body>
    </html>
  )
}
