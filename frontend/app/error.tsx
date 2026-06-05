'use client'
export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="text-center">
        <h2 className="text-2xl font-bold mb-4">Something went wrong</h2>
        <p className="text-gray-400 mb-8">{error.message}</p>
        <button onClick={reset} className="btn-primary">Try again</button>
      </div>
      <footer className="fixed bottom-4 w-full text-center text-sm text-gray-600">
        Powered by <a href="https://cosbyaisolutions.com" className="text-brand-400 hover:underline" target="_blank" rel="noopener noreferrer">Cosby AI Solutions</a>
      </footer>
    </div>
  )
}
