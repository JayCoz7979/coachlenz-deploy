export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-gray-950 px-8 py-16 max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold mb-8">Privacy Policy</h1>
      <div className="space-y-6 text-gray-300">
        <p>CoachLenz collects only the data necessary to provide the service: account information, uploaded game film, and usage data.</p>
        <p>We do not sell your data to third parties.</p>
        <p>Game film is stored securely on Cloudflare R2 with presigned URL access expiring after 7 days.</p>
        <p>You may request deletion of your account and data at any time by contacting info@cosbyaisolutions.com.</p>
      </div>
      <footer className="mt-16 text-sm text-gray-600">
        Powered by <a href="https://cosbyaisolutions.com" className="text-brand-400 hover:underline">Cosby AI Solutions</a>
      </footer>
    </div>
  )
}
