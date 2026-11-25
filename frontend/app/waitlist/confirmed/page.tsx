import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: "You're on the list",
  robots: { index: false, follow: false },
}

export default function ConfirmedPage() {
  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center px-6">
      <div className="max-w-lg text-center">
        <h1 className="text-3xl font-bold text-gray-100 mb-4">You&apos;re on the list.</h1>
        <p className="text-base text-gray-100 mb-6">
          Use the confirm link in your email. The Halftime Sheet download appears after that link is confirmed.
        </p>
        <p className="text-sm text-gray-400 mt-6">We&apos;ll email you when CoachLenz opens.</p>
      </div>
    </div>
  )
}
