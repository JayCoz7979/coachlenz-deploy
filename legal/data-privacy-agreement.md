# Data Privacy Agreement (DPA)

> **⚠️ DRAFT — ATTORNEY REVIEW REQUIRED. Not legal advice. Do not execute until reviewed by counsel and `[FILL-IN]` fields are completed.**

This Data Privacy Agreement ("DPA") is between **Cosby AI Solutions LLC** ("CoachLenz," "Provider") and **`[FILL-IN SCHOOL / DISTRICT NAME]`** (the "Educational Agency"), and supplements the CoachLenz Organization Terms of Service. Where this DPA conflicts with the Terms regarding student data, this DPA controls.

**Effective date:** `[FILL-IN]`

## 1. Subject matter and duration
CoachLenz processes student data to provide AI athletic film analysis for the term of the Educational Agency's subscription, plus the retention/deletion windows in Section 7.

## 2. Nature and purpose of processing
Ingesting, storing, analyzing, and returning athletic film and derived analysis (play breakdowns, tendencies, reports, grades) at the direction and for the sole benefit of the Educational Agency and its students.

## 3. Types of personal data
Student names (as entered by the Agency), jersey numbers, gameplay video, and performance statistics derived from film. No faceprints or biometric identifiers are captured (see Terms §5).

## 4. Categories of data subjects
Student-athletes and coaching/athletic staff of the Educational Agency.

## 5. Provider obligations (AB 1584 / SOPIPA — nine clauses)
CoachLenz affirms, mirroring the Terms: (1) student data remains the Agency's property; (2) no targeted advertising using student data; (3) no sale of student data; (4) no unauthorized student profiling; (5) reasonable security safeguards (Section 6); (6) support for student access and correction; (7) deletion or return of student data (Section 7); (8) breach notification (Section 8); (9) compliance with FERPA and applicable state student-privacy laws.

## 6. Security obligations (NIST CSF 2.0)
CoachLenz aligns its security program to the NIST Cybersecurity Framework 2.0 (Govern, Identify, Protect, Detect, Respond, Recover) and maintains, at minimum: TLS in transit; film encrypted at rest in Cloudflare R2 (AES-256); additional field-level encryption for sensitive stored data (Fernet, AES-128-CBC + HMAC); SSRF-guarded URL fetching; rate-limited authentication; a default-deny administrative gate; refresh-token revocation on logout/password change; and a documented credential-rotation schedule. CoachLenz limits access to student data to personnel with a need to know.

## 7. Deletion and Deletion Certificate
CoachLenz retains student data for the active contract plus 90 days, and upon termination or the Agency's written request deletes all student data (including backups) within **30 days**, providing a **Deletion Certificate** (date, categories, method, backup-purge confirmation). Student-uploaded film (non-Agency accounts) is deleted within 14 days of closure/request.

## 8. Breach notification
CoachLenz notifies the Educational Agency of any breach or unauthorized release of student PII **without unreasonable delay and no later than 7 calendar days after discovery**, in writing, and cooperates with the Agency's legal notification obligations (including NY Education Law §2-d / 8 NYCRR Part 121 where applicable).

## 9. Sub-processors
CoachLenz uses the sub-processors listed in the Privacy Policy (Supabase, Cloudflare R2, Anthropic, Stripe, Resend, Twilio, Railway, Sentry) and remains responsible for their compliance with this DPA. CoachLenz will give the Agency notice of a new sub-processor that will process student data and an opportunity to object.

## 10. NY Education Law §2-d — Appendix / Supplemental Information
Where the Educational Agency is a New York agency, the CoachLenz Parents' Bill of Rights and the §2-d supplemental information (exclusive purposes for data use; sub-processor oversight; contract term and post-term data handling; challenge of data accuracy; storage and encryption) are incorporated by reference and provided at `parents-bill-of-rights.md`.

## 11. Audit rights
Once per year, on at least **30 days'** written notice, the Educational Agency may audit CoachLenz's compliance with this DPA (or request a summary of CoachLenz's most recent independent security assessment), subject to confidentiality and without unreasonably disrupting CoachLenz's operations.

## 12. Signatures
**Educational Agency**
Name: `[FILL-IN]` · Title: `[FILL-IN]` · Signature: ___________________ · Date: __________

**Cosby AI Solutions LLC**
Name: Jason L. Cosby · Title: Founder & CEO · Signature: ___________________ · Date: __________

*Prepared as a draft for attorney review. legal@coachlenz.com*
