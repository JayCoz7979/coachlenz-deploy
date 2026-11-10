import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: 'How CoachLenz handles coach and student-athlete data, built to COPPA and FERPA standards, with access and deletion requests.',
  alternates: { canonical: '/privacy' },
}

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-gray-950 px-8 py-16 max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Privacy Policy</h1>
      <p className="text-sm text-gray-500 mb-8">Last updated: November 10, 2026</p>

      <div className="space-y-6 text-gray-300 leading-relaxed">
        <p>
          This policy explains what CoachLenz collects, how we use it, and your rights. CoachLenz is
          an AI sports-film analysis service provided by Cosby AI Solutions LLC
          (&ldquo;CoachLenz,&rdquo; &ldquo;we,&rdquo; &ldquo;us&rdquo;) and used by coaches, schools,
          and athletic programs. Contact us at <a href="mailto:privacy@coachlenz.com" className="text-brand-400 hover:underline">privacy@coachlenz.com</a>.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">1. Information we collect</h2>
        <p>
          <strong className="text-gray-100">Account information:</strong> your name, email,
          organization, and role. Your password is stored only as a secure hash. Email is how we
          verify your account.
        </p>
        <p>
          <strong className="text-gray-100">Film and content you upload:</strong> game and practice
          video, and any titles, tags, notes, rosters, and statistics you add.
        </p>
        <p>
          <strong className="text-gray-100">Analysis output:</strong> the play breakdowns,
          tendencies, reports, and grades our system produces from your film.
        </p>
        <p>
          <strong className="text-gray-100">Usage and telemetry:</strong> log data, device and
          browser information, and feature usage, used to operate and improve the service and to
          detect abuse.
        </p>
        <p>
          <strong className="text-gray-100">Payment information:</strong> processed by Stripe. We
          never store your full card number. We keep only your subscription status and Stripe
          identifiers.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">2. How we use film and student-athlete data</h2>
        <p>
          Film and its analysis are used only to provide the service you requested. We do not use
          your film or student-athlete data to train AI models without your separate, explicit
          opt-in, and our AI sub-processor (Anthropic) does not train on data submitted through its
          API by default. We do not sell student data, and we do not use it for advertising.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">3. EAGLE-EYE is not facial recognition</h2>
        <p>
          EAGLE-EYE groups plays by jersey number and general appearance, confirmed by a coach. It
          does not create faceprints and does not capture biometric identifiers as defined under the
          Illinois Biometric Information Privacy Act (740 ILCS 14), the Texas Capture or Use of
          Biometric Identifier Act (Tex. Bus. &amp; Com. Code &sect;503.001), or Washington law
          (RCW 19.375). See our <a href="/terms" className="text-brand-400 hover:underline">Terms of Service</a> for details.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">4. Children&rsquo;s privacy (COPPA)</h2>
        <p>
          When the service is used through a school or program, the coach or institution provides the
          consent required for students under 13, as the school&rsquo;s agent under COPPA&rsquo;s
          school-consent mechanism, and confirms this through the in-app attestation CoachLenz
          requires before any roster data is added. A parent or guardian may request access to,
          correction of, or deletion of their child&rsquo;s data by contacting{' '}
          <a href="mailto:privacy@coachlenz.com" className="text-brand-400 hover:underline">privacy@coachlenz.com</a>;
          we respond within 14 days.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">5. Data retention and deletion</h2>
        <p>
          We keep your content while your account is active. On account closure or your written
          request, we delete your content, including backups, within 30 days. You can request access
          to, or deletion of, a student-athlete&rsquo;s data at any time using the{' '}
          <a href="/privacy/delete-request" className="text-brand-400 hover:underline">student data request form</a>{' '}
          or by emailing <a href="mailto:privacy@coachlenz.com" className="text-brand-400 hover:underline">privacy@coachlenz.com</a>.
          Schools under a contract may have retention terms set in their Data Privacy Agreement.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">6. Security</h2>
        <p>
          We use TLS in transit, and film is encrypted at rest in Cloudflare R2 (AES-256). Sensitive
          stored fields are additionally encrypted (Fernet, AES-128-CBC with HMAC). Film is served
          through presigned URLs that expire after 7 days. We guard server-side URL fetching against
          SSRF, rate-limit authentication, default-deny our administrative surface, revoke refresh
          tokens on logout and password change, and follow a documented credential-rotation schedule.
          No system is perfectly secure, but we work to protect your data and will notify affected
          parties as required by law.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">7. Sub-processors</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left text-gray-400 border-b border-gray-800">
                <th className="py-2 pr-4 font-semibold">Sub-processor</th>
                <th className="py-2 pr-4 font-semibold">Purpose</th>
              </tr>
            </thead>
            <tbody className="text-gray-300">
              <tr className="border-b border-gray-800/60"><td className="py-2 pr-4">Railway</td><td className="py-2 pr-4">Application and database hosting (PostgreSQL)</td></tr>
              <tr className="border-b border-gray-800/60"><td className="py-2 pr-4">Cloudflare R2</td><td className="py-2 pr-4">Film storage and delivery</td></tr>
              <tr className="border-b border-gray-800/60"><td className="py-2 pr-4">Anthropic</td><td className="py-2 pr-4">AI film analysis</td></tr>
              <tr className="border-b border-gray-800/60"><td className="py-2 pr-4">Stripe</td><td className="py-2 pr-4">Payment processing (no full card number)</td></tr>
              <tr className="border-b border-gray-800/60"><td className="py-2 pr-4">Resend</td><td className="py-2 pr-4">Transactional email</td></tr>
              <tr><td className="py-2 pr-4">Sentry</td><td className="py-2 pr-4">Error monitoring (no student data in logs)</td></tr>
            </tbody>
          </table>
        </div>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">8. Your choices and rights</h2>
        <p>
          Where applicable law (including the EU and UK GDPR) grants them, you have rights to access,
          correct, delete, and port your personal data, and to object to or restrict certain
          processing. Our lawful bases are our legitimate interest in providing sports analysis to
          coaches and, for minors through schools, the school&rsquo;s authorization or consent. A Data
          Processing Agreement is available at <a href="mailto:legal@coachlenz.com" className="text-brand-400 hover:underline">legal@coachlenz.com</a>.
          To exercise any right, contact <a href="mailto:privacy@coachlenz.com" className="text-brand-400 hover:underline">privacy@coachlenz.com</a>.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">9. Changes and contact</h2>
        <p>
          We will post changes here and update the date above. When a change is material, we will ask
          you to re-accept before you continue using CoachLenz. Questions:{' '}
          <a href="mailto:privacy@coachlenz.com" className="text-brand-400 hover:underline">privacy@coachlenz.com</a>.
          Cosby AI Solutions LLC.
        </p>
      </div>

      <footer className="mt-16 text-sm text-gray-600">
        Powered by <a href="https://cosbyaisolutions.com" className="text-brand-400 hover:underline">Cosby AI Solutions</a>
      </footer>
    </div>
  )
}
