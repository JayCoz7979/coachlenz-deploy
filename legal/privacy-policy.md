# CoachLenz Privacy Policy

> **⚠️ DRAFT — ATTORNEY REVIEW REQUIRED. Not legal advice.**

**Effective date:** `[FILL-IN]` · **Provider:** Cosby AI Solutions LLC ("CoachLenz," "we," "us") · **Contact:** privacy@coachlenz.com

This policy explains what CoachLenz collects, how we use it, and your rights. CoachLenz is an AI sports-film analysis service used by coaches, schools, and athletic programs.

## 1. Information we collect
- **Account information:** name, email, phone (for verification), organization, role, and password (stored only as a bcrypt hash).
- **Film and content you upload:** game/practice video and any titles, tags, or notes you add.
- **Analysis output:** the play breakdowns, tendencies, reports, and grades our system produces from your film.
- **Usage and telemetry:** log data, device/browser information, and feature usage, used to operate and improve the Service and detect abuse.
- **Payment information:** processed by Stripe. **CoachLenz never stores your full card number**; we retain only a subscription status and Stripe identifiers.

## 2. How we use student-athlete film
- Film and its analysis are used **only** to provide the Service you requested (film breakdown, tendencies, reports).
- We do **not** use student-athlete film or data to **train AI models** without separate, explicit opt-in consent. Our AI sub-processor (Anthropic) does not train on data submitted through its API by default.
- We do **not sell** student data, and we do **not** use it for advertising.

## 3. EAGLE-EYE (player grouping) — not facial recognition
EAGLE-EYE groups plays by **jersey number and general appearance**, confirmed by a coach. It does **not** create faceprints and does **not** capture biometric identifiers as defined under Illinois BIPA (740 ILCS 14), Texas CUBI (Tex. Bus. & Com. Code §503.001), or Washington law (RCW 19.375). See our Terms for details.

## 4. Children's privacy (COPPA)
When the Service is used through a school account, the school provides the required consent for students under 13 as their agent under COPPA's school-consent mechanism. A parent or guardian may request access to, correction of, or deletion of their child's data by contacting **privacy@coachlenz.com**; we respond within **14 days**. See our Parents' Bill of Rights for New York-specific rights.

## 5. Data retention
- Student film and metadata: for the active school contract plus **90 days** after termination; deleted (including backups) within **30 days** of contract termination or written request, with a Deletion Certificate.
- Student-uploaded film (individual accounts): deleted within **14 days** of account closure or written request.
- These periods match our Terms of Service and Data Privacy Agreement.

## 6. Security
We use TLS in transit; film is encrypted at rest in Cloudflare R2 (AES-256); sensitive stored fields are additionally encrypted (Fernet, AES-128-CBC + HMAC). We SSRF-guard server-side URL fetching, rate-limit authentication, default-deny our administrative surface, revoke refresh tokens on logout and password change, and follow a documented credential-rotation schedule. No system is perfectly secure, but we work to protect your data and will notify affected parties and educational agencies of a breach as required by law (for New York agencies, within 7 calendar days of discovery).

## 7. Third-party sub-processors
| Sub-processor | Purpose | Data category |
|---|---|---|
| Supabase | Database & application hosting | Account data, analysis metadata |
| Cloudflare R2 | Film storage & delivery | Uploaded film |
| Anthropic | AI film analysis | Frames/segments of film during analysis |
| Stripe | Payment processing | Billing contact, subscription status (no full card number) |
| Resend | Transactional email | Name, email |
| Twilio | Phone verification | Phone number |
| Railway | Application hosting | All service data in transit through the app |
| Sentry | Error monitoring | Diagnostic/log data (no student PII in logs) |

## 8. Your choices and rights (incl. GDPR)
Where applicable law (including the EU/UK GDPR) grants them, you have rights to access, correct, delete, and port your personal data, and to object to or restrict certain processing. Our lawful bases are legitimate interest (providing sports analysis to coaches) and, for minors via schools, the school's authorization/consent. A Data Processing Agreement is available at **legal@coachlenz.com**. To exercise any right, contact **privacy@coachlenz.com**.

## 9. Changes and contact
We will post changes here and update the effective date; material changes affecting schools will be communicated to them. Questions: **privacy@coachlenz.com** · Cosby AI Solutions LLC.

*Powered by Cosby AI Solutions — cosbyaisolutions.com*
