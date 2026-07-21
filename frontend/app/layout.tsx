// deploy-trigger check 2026-07-21: verifies frontend auto-deploys from main on merge
import type { Metadata } from 'next'
import { Bebas_Neue, DM_Sans, DM_Mono, Syne } from 'next/font/google'
import './globals.css'
import './os.css'

const bebasNeue = Bebas_Neue({
  subsets: ['latin'],
  weight: '400',
  variable: '--font-bebas',
})

const dmSans = DM_Sans({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600'],
  variable: '--font-dm-sans',
})

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-dm-mono',
})

const syne = Syne({
  subsets: ['latin'],
  weight: ['400', '600', '700', '800'],
  variable: '--font-syne',
})

export const metadata: Metadata = {
  title: 'CoachLenz — AI Film Analyst OS',
  description: 'See Every Tendency. Win Every Game.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${bebasNeue.variable} ${dmSans.variable} ${dmMono.variable} ${syne.variable}`}>
        {children}
      </body>
    </html>
  )
}
