export default function TermsPage() {
  return (
    <div className="min-h-screen bg-gray-950 px-8 py-16 max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold mb-8">Terms of Service</h1>
      <div className="space-y-6 text-gray-300">
        <p>By using CoachLenz, you agree to these terms. CoachLenz is provided by Cosby AI Solutions LLC.</p>
        <p>You are responsible for the content you upload. Do not upload content you do not have rights to.</p>
        <p>We reserve the right to terminate accounts that violate these terms.</p>
        <p>The service is provided as-is without warranty.</p>
      </div>
      <footer className="mt-16 text-sm text-gray-600">
        Powered by <a href="https://cosbyaisolutions.com" className="text-brand-400 hover:underline">Cosby AI Solutions</a>
      </footer>
    </div>
  )
}
