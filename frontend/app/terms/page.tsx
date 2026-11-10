import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Terms of Service',
  description: 'The terms for using CoachLenz, the AI film analyst OS from Cosby AI Solutions LLC.',
  alternates: { canonical: '/terms' },
}

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-gray-950 px-8 py-16 max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Terms of Service</h1>
      <p className="text-sm text-gray-500 mb-8">Last updated: November 10, 2026</p>

      <div className="space-y-6 text-gray-300 leading-relaxed">
        <p>
          CoachLenz is an AI film-analysis service provided by Cosby AI Solutions LLC
          (&ldquo;CoachLenz,&rdquo; &ldquo;we,&rdquo; &ldquo;us&rdquo;). By creating an account, checking the
          box that you agree to these Terms, or using the service, you agree to these Terms of
          Service. If you do not agree, do not use CoachLenz.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">1. What CoachLenz is</h2>
        <p>
          CoachLenz analyzes game and practice film and produces play breakdowns, tendencies,
          reports, and grades to help coaches. It is a coaching aid, not an official record and not
          a substitute for your own judgment.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">2. Your account</h2>
        <p>
          You agree to provide accurate information, to keep your password secure, and to be
          responsible for everything done through your account. One login is for one person. Tell us
          at <a href="mailto:support@coachlenz.com" className="text-brand-400 hover:underline">support@coachlenz.com</a> if
          you believe your account has been accessed without your permission.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">3. Content you upload, and the rights you confirm</h2>
        <p>
          You represent and warrant that you have the right to upload and use every piece of content
          you put into CoachLenz, including all game and practice film, rosters, player names, and
          statistics, and that you have obtained, or are otherwise covered by a lawful basis or
          school authorization for, every consent required to collect that content and to have
          CoachLenz process it on your behalf. This includes any consent required for
          student-athletes under the age of 13.
        </p>
        <p>
          You are solely responsible for obtaining and keeping those consents and authorizations. You
          agree to provide proof of them within 5 business days of our written request, and you agree
          to indemnify and hold harmless Cosby AI Solutions LLC against any claim, loss, or penalty
          arising from content you did not have the right to upload or any consent you failed to
          obtain.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">4. Student-athlete data: FERPA and COPPA</h2>
        <p>
          Most athletes in your film and rosters are minors. When you use CoachLenz for a school,
          district, or athletic program, you do so as that institution&rsquo;s authorized
          representative, and CoachLenz acts as a school official or service provider performing
          athletic film analysis under your direction, consistent with the Family Educational Rights
          and Privacy Act (FERPA, 20 U.S.C. &sect;1232g) and its service-provider provisions.
        </p>
        <p>
          For any student under 13, you confirm, through the separate in-app attestation CoachLenz
          requires before you add roster data, that the consent required under the Children&rsquo;s
          Online Privacy Protection Act (COPPA, 15 U.S.C. &sect;6501 et seq.), whether through your
          school&rsquo;s authorization under COPPA&rsquo;s school-consent provision or through
          verifiable parental consent, has been obtained. Schools and districts that require a signed
          Data Privacy Agreement can request one at <a href="mailto:legal@coachlenz.com" className="text-brand-400 hover:underline">legal@coachlenz.com</a>.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">5. AI film analysis</h2>
        <p>
          CoachLenz uses automated artificial intelligence to detect plays and events in your film
          and to draft reports, grades, and tendencies. Our AI sub-processor is Anthropic, which does
          not train its models on data submitted through its API by default, and CoachLenz does not
          use your film or student-athlete data to train AI models without your separate, explicit
          opt-in.
        </p>
        <p>
          AI analysis is a coaching aid, not an official record. It can miss plays or label them
          incorrectly, particularly on lower-resolution or single-camera film. You are responsible
          for reviewing and confirming any output before relying on it.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">6. Player grouping is not facial recognition</h2>
        <p>
          The EAGLE-EYE feature groups plays by jersey number and general appearance (such as
          clothing, hairstyle, and general look), confirmed by a coach. It does not create faceprints
          and does not capture biometric identifiers as defined under the Illinois Biometric
          Information Privacy Act (740 ILCS 14), the Texas Capture or Use of Biometric Identifier Act
          (Tex. Bus. &amp; Com. Code &sect;503.001), or Washington law (RCW 19.375). If CoachLenz ever
          introduces true facial recognition, we will obtain separate informed consent before any
          such capture.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">7. Ownership, no sale, no advertising</h2>
        <p>
          Your content, and the student-athlete data in it, remain yours or your school&rsquo;s. We do
          not sell it, and we do not use it for targeted advertising. We use it only to provide and
          improve the service you requested.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">8. Subscriptions, trial, credits, and cancellation</h2>
        <p>
          CoachLenz offers a free trial and paid subscription tiers billed through Stripe. Analysis
          credits may be purchased separately and are consumed when you run an analysis. Subscriptions
          renew automatically until you cancel. You may cancel at any time and keep access through the
          end of the period you have paid for. The current prices, included amounts, and credit terms
          are shown in the app at the time of purchase. We never store your full card number.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">9. Acceptable use</h2>
        <p>
          Do not upload content you do not have the rights to, and do not upload unlawful, infringing,
          or harmful content. Do not attempt to breach, probe, or disrupt the service, and do not use
          it to violate anyone&rsquo;s privacy or legal rights. We may suspend or terminate accounts
          that violate these Terms.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">10. Service provided as is; limitation of liability</h2>
        <p>
          The service is provided &ldquo;as is&rdquo; and &ldquo;as available,&rdquo; without
          warranties of any kind, and we do not guarantee that AI output is accurate or complete. To
          the maximum extent permitted by law, the aggregate liability of Cosby AI Solutions LLC for
          any claim relating to the service is limited to the fees you paid in the 12 months before
          the claim, and we are not liable for indirect, incidental, or consequential damages.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">11. Data retention and deletion</h2>
        <p>
          We keep your content while your account is active. On account closure or your written
          request, we delete your content, including backups, within 30 days. A parent, guardian, or
          eligible student can request access to, or deletion of, a student-athlete&rsquo;s data at
          any time using the{' '}
          <a href="/privacy/delete-request" className="text-brand-400 hover:underline">student data request form</a>{' '}
          or by emailing <a href="mailto:privacy@coachlenz.com" className="text-brand-400 hover:underline">privacy@coachlenz.com</a>.
          Full detail is in our <a href="/privacy" className="text-brand-400 hover:underline">Privacy Policy</a>.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">12. Changes to these Terms</h2>
        <p>
          We may update these Terms. When we make a material change, you will be asked to review and
          re-accept the updated Terms before continuing to use CoachLenz. Continued use after an
          update means you accept it.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">13. Governing law</h2>
        <p>
          These Terms are governed by the laws of the State of Alabama, without regard to its
          conflict-of-laws rules. Any dispute will be resolved in the state or federal courts located
          in Alabama, except that either party may seek injunctive relief to protect its intellectual
          property or confidential information.
        </p>

        <h2 className="text-xl font-semibold text-gray-100 pt-2">14. Contact</h2>
        <p>
          Questions about these Terms: <a href="mailto:legal@coachlenz.com" className="text-brand-400 hover:underline">legal@coachlenz.com</a>.
          Cosby AI Solutions LLC, Jason L. Cosby, Founder &amp; CEO.
        </p>
      </div>

      <footer className="mt-16 text-sm text-gray-600">
        Powered by <a href="https://cosbyaisolutions.com" className="text-brand-400 hover:underline">Cosby AI Solutions</a>
      </footer>
    </div>
  )
}
