import type { Metadata } from 'next'
import localFont from 'next/font/local'
import './globals.css'
import './os.css'
import ReconsentGate from '@/components/legal/ReconsentGate'
import ServiceWorkerRegistrar from '@/components/ServiceWorkerRegistrar'
import { ThemeProvider } from '@/components/theme/ThemeProvider'
import { NO_FLASH_SCRIPT } from '@/lib/theme/theme'

// Self-hosted latin files so the production build does not fetch Google Fonts.
const bebasNeue = localFont({
  src: '../fonts/bebas-neue-400.woff2',
  weight: '400',
  display: 'swap',
  variable: '--font-bebas',
})

const dmSans = localFont({
  src: '../fonts/dm-sans.woff2',
  weight: '300 600',
  display: 'swap',
  variable: '--font-dm-sans',
})

const dmMono = localFont({
  src: [
    { path: '../fonts/dm-mono-400.woff2', weight: '400', style: 'normal' },
    { path: '../fonts/dm-mono-500.woff2', weight: '500', style: 'normal' },
  ],
  display: 'swap',
  variable: '--font-dm-mono',
})

const syne = localFont({
  src: '../fonts/syne.woff2',
  weight: '400 800',
  display: 'swap',
  variable: '--font-syne',
})

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://app.coachlenz.com'

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: 'CoachLenz, AI Film Analyst OS', template: '%s | CoachLenz' },
  description: 'See Every Tendency. Win Every Game.',
  applicationName: 'CoachLenz',
  openGraph: {
    title: 'CoachLenz, AI Film Analyst OS',
    description: 'See Every Tendency. Win Every Game.',
    siteName: 'CoachLenz',
    type: 'website',
    url: '/',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'CoachLenz, AI Film Analyst OS',
    description: 'See Every Tendency. Win Every Game.',
  },
  manifest: '/manifest.webmanifest',
  icons: {
    icon: [
      { url: '/icons/favicon-16.png', sizes: '16x16', type: 'image/png' },
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
        {/* Applies the saved light/dark theme + accent before paint, so there is no flash. */}
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_SCRIPT }} />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              '@context': 'https://schema.org',
              '@type': 'SoftwareApplication',
              name: 'CoachLenz',
              applicationCategory: 'SportsApplication',
              operatingSystem: 'Web',
              description: 'AI film analysis for coaches. Upload your game film and CoachLenz finds the tendencies, so you spend your time coaching instead of breaking down film.',
              offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD', description: '14-day free trial' },
              publisher: { '@type': 'Organization', name: 'Cosby AI Solutions', url: 'https://cosbyaisolutions.com' },
            }),
          }}
        />
        <ThemeProvider>
          {children}
          <ReconsentGate />
        </ThemeProvider>
        <ServiceWorkerRegistrar />
      </body>
    </html>
  )
}
