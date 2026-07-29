# CoachLenz Legal Documents — DRAFTS

> **⚠️ ATTORNEY REVIEW REQUIRED — DO NOT EXECUTE OR PUBLISH AS-IS.**
> These are structured first drafts prepared to accelerate review by licensed
> counsel (preferably an attorney experienced in education technology and student
> data privacy). They are **not legal advice** and are **not attorney-grade final
> documents**. No school, district, or user should be asked to sign or rely on any
> of these until a qualified attorney has reviewed and approved them, the
> `[FILL-IN]` fields are completed, and the review banner is removed.

## Contents

| File | Purpose | Who signs / reads |
|---|---|---|
| [terms-of-service.md](terms-of-service.md) | Organization Terms (school/district accounts) | School/district authorized signer |
| [privacy-policy.md](privacy-policy.md) | Public-facing privacy policy | Public (coachlenz.com) |
| [data-privacy-agreement.md](data-privacy-agreement.md) | Standalone DPA | School/district authorized signer |
| [parents-bill-of-rights.md](parents-bill-of-rights.md) | NY Ed Law §2-d Parents' Bill of Rights | Public, no login |
| [cookie-policy.md](cookie-policy.md) | Cookie disclosure (CA/EU) | Public |
| [deletion-certificate-template.md](deletion-certificate-template.md) | Auto-populated deletion certificate | School/parent on deletion |

## Grounding facts these drafts rely on (verify before finalizing)

- **Provider entity:** Cosby AI Solutions LLC ("CoachLenz" is the product). Founder & CEO: Jason L. Cosby. Governing law: State of Alabama.
- **Contacts:** privacy@coachlenz.com (privacy/COPPA), legal@coachlenz.com (legal/DPA).
- **Sub-processors:** Supabase (Postgres database + hosting), Cloudflare R2 (film storage), Anthropic (AI film analysis), Stripe (payments), Resend (transactional email), Twilio (phone verification), Railway (application hosting), Sentry (error monitoring).
- **Security posture (as implemented):** TLS in transit; film encrypted at rest in Cloudflare R2 (AES-256); sensitive stored fields additionally encrypted with authenticated symmetric encryption (Fernet, AES-128-CBC + HMAC); SSRF-guarded URL fetching; rate-limited auth; default-deny platform-admin gate; refresh-token revocation on logout/password change; documented credential-rotation schedule.
- **EAGLE-EYE:** groups plays by jersey number and general appearance, confirmed by a coach. It does **not** capture faceprints or biometric identifiers.
- **AI training:** student data is not used to train AI models; the AI sub-processor (Anthropic) does not train on API data by default.

## Still to do (product wiring — separate from these drafts, spec 2.3.G)
- Footer links to each doc; require ToS + DPA acceptance at school signup with `legal_acceptances` logging (user, doc, version, timestamp, IP).
- `/privacy/delete-request` form + deletion ticket + auto Deletion Certificate email.
- Public `/privacy/parents-bill-of-rights` route (no login).
- COPPA under-13 gate on player-profile creation.
