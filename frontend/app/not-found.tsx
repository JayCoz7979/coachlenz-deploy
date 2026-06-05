import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="text-center">
        <h1 className="text-6xl font-bold text-brand-400 mb-4">404</h1>
        <p className="text-gray-400 mb-8">Page not found</p>
        <Link href="/" className="btn-primary">Go Home</Link>
      </div>
      <footer className="fixed bottom-4 w-full text-center text-sm text-gray-600">
        Powered by <a href="https://cosbyaisolutions.com" className="text-brand-400 hover:underline" target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
      </footer>
    </div>
  )
}
