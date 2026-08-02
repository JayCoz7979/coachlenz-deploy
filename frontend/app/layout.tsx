import type { Metadata } from 'next'
import { Bebas_Neue, DM_Sans, DM_Mono, Syne } from 'next/font/google'
import './globals.css'
import './os.css'
import ReconsentGate from '@/components/legal/ReconsentGate'
import ServiceWorkerRegistrar from '@/components/ServiceWorkerRegistrar'

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
  manifest: '/manifest.webmanifest',
  icons: {
    icon: [
      { url: '/icons/favicon-32.png', sizes: '32x32', type: 'image/png' },
      { url: '/icons/favicon-48.png', sizes: '48x48', type: 'image/png' },
      { url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
      { url: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
    ],
    apple: [{ url: '/icons/apple-touch-icon.png', sizes: '180x180', type: 'image/png' }],
  },
  // Home-screen (installed) behavior only; does NOT change in-browser appearance.
  appleWebApp: { capable: true, title: 'CoachLenz', statusBarStyle: 'black-translucent' },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${bebasNeue.variable} ${dmSans.variable} ${dmMono.variable} ${syne.variable}`}>
        {children}
        <ReconsentGate />
        <ServiceWorkerRegistrar />
      </body>
    </html>
  )
}
