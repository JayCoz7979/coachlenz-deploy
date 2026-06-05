import Link from 'next/link'

export default function ReferPage({ params }: { params: { code: string } }) {
  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="text-center max-w-md">
        <h1 className="text-3xl font-bold text-brand-400 mb-4">You're Invited to CoachLenz</h1>
        <p className="text-gray-400 mb-8">AI-powered sports tendency intelligence for coaches. Start your 14-day free trial.</p>
        <Link href={`/onboarding?ref=${params.code}`} className="btn-primary text-lg px-8 py-3 inline-block">Start Free Trial</Link>
        <p className="text-sm text-gray-500 mt-4">Already have an account? <Link href="/login" className="text-brand-400 hover:underline">Sign in</Link></p>
        <p className="text-xs text-gray-600 mt-8">Powered by <a href="https://cosbyaisolutions.com" className="text-brand-500 hover:underline">Cosby AI Solutions</a></p>
      </div>
    </div>
  )
}
