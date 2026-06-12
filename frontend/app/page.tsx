import Link from 'next/link'
import IntroOverlay from '@/components/IntroOverlay'

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      <IntroOverlay />
      <header className="border-b border-gray-800 px-8 py-4 flex items-center justify-between">
        <div className="text-2xl font-bold text-brand-400">CoachLenz</div>
        <div className="flex gap-4">
          <Link href="/login" className="btn-secondary">Sign In</Link>
          <Link href="/onboarding" className="btn-primary">Start Free Trial</Link>
        </div>
      </header>
      <main className="flex-1 flex flex-col items-center justify-center text-center px-8 py-20">
        <div className="max-w-3xl">
          <h1 className="text-5xl font-bold mb-6 bg-gradient-to-r from-brand-400 to-purple-400 bg-clip-text text-transparent">
            AI-Powered Film Analysis for Every Coach
          </h1>
          <p className="text-xl text-gray-400 mb-10">
            Upload your game film. CoachLenz finds the tendencies. You win more games.
          </p>
          <div className="flex gap-4 justify-center">
            <Link href="/onboarding" className="btn-primary text-lg px-8 py-3">Start Free Trial</Link>
            <Link href="/login" className="btn-secondary text-lg px-8 py-3">Sign In</Link>
          </div>
        </div>
      </main>
      <footer className="border-t border-gray-800 px-8 py-4 text-center text-sm text-gray-500">
        Powered by <a href="https://cosbyaisolutions.com" className="text-brand-400 hover:underline" target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
      </footer>
    </div>
  )
}
