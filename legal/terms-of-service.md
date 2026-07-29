# CoachLenz Organization Terms of Service (School / District)

> **⚠️ DRAFT — ATTORNEY REVIEW REQUIRED. Not legal advice. Do not execute until reviewed by counsel and `[FILL-IN]` fields are completed.**

**Provider:** Cosby AI Solutions LLC, a limited liability company ("CoachLenz," "we," "us"), for its CoachLenz AI film-analysis service (the "Service").
**Customer:** the educational agency (school, district, or institution) accepting these Terms (the "School").
**Effective date:** `[FILL-IN EFFECTIVE DATE]` · **Last updated:** `[FILL-IN]`

These Terms govern the School's use of the Service. By creating an organization account or accepting these Terms, the School agrees to them through its authorized representative.

## 1. FERPA — School Official Exception
CoachLenz processes student "education records" solely as a "school official" with a "legitimate educational interest" under the Family Educational Rights and Privacy Act, 20 U.S.C. §1232g, and 34 C.F.R. §99.31(a)(1)(i)(B). CoachLenz:
(a) performs an institutional service (athletic film analysis) for which the School would otherwise use employees;
(b) acts under the **direct control** of the School with respect to the use and maintenance of education records;
(c) uses education records **only** for the authorized educational purpose of athletic film analysis and the features the School enables; and
(d) does **not** re-disclose education records to any third party without the prior written consent of the eligible student or parent, except as permitted by FERPA or required by law. CoachLenz remains subject to 34 C.F.R. §99.33(a)'s limits on re-disclosure.

## 2. COPPA — Delegated Consent
The Service is not directed to children as a consumer product; it is provided to the School for a school-authorized educational purpose. For any student under 13, the School represents and warrants that it has obtained, or will obtain before that student uses the Service, all parental consents required under the Children's Online Privacy Protection Act, 15 U.S.C. §6501 et seq., and will maintain those consents on file and produce them to CoachLenz within **5 business days** of a written request. The School's provision of the Service to students is "solely for the benefit of the school and students" and for no commercial purpose beyond the educational service, consistent with the FTC's COPPA school-consent guidance. CoachLenz does not condition a student's participation on the disclosure of more information than is reasonably necessary, and does not use or disclose student information for its own commercial purposes.

## 3. California — AB 1584 / SOPIPA
For students in California (and offered to all Schools as CoachLenz's baseline commitment), and pursuant to Cal. Ed. Code §49073.1 (AB 1584) and the Student Online Personal Information Protection Act (SOPIPA, Cal. B&P Code §22584):
1. **Ownership.** Student records/data are and remain the property of and under the control of the School/district.
2. **No targeted advertising.** CoachLenz will not use student data to engage in targeted advertising.
3. **No sale.** CoachLenz will not sell student data under any circumstances.
4. **No unauthorized profiles.** CoachLenz will not use student data to create a profile except in furtherance of the authorized educational purpose.
5. **Security safeguards.** CoachLenz maintains reasonable administrative, technical, and physical safeguards, including: TLS in transit; film encrypted at rest in Cloudflare R2 (AES-256); sensitive stored fields additionally encrypted (Fernet, AES-128-CBC + HMAC); SSRF-guarded server-side URL fetching; rate-limited authentication; a default-deny platform-administration gate; refresh-token revocation on logout and password change; and a documented credential-rotation schedule.
6. **Student access.** CoachLenz will support the School's obligation to provide a student (or parent) access to, and correction of, that student's data, by making such data available to the School on request.
7. **Deletion / return.** CoachLenz will delete or return student data as specified in Section 6 (Retention and Deletion).
8. **Breach notification.** CoachLenz will provide breach notification as specified in Section 6 and Section 4.
9. **Applicable law.** CoachLenz will comply with FERPA and applicable state student-privacy laws.

## 4. New York — Education Law §2-d
Where the School is a New York educational agency, the following apply and control for New York student data:

**(a) Parents' Bill of Rights.** CoachLenz adopts and supplements the School's Parents' Bill of Rights for Data Privacy and Security (see `parents-bill-of-rights.md`), affirming that: student data will not be sold or released for any commercial purpose; parents have the right to inspect, review, and correct student data by contacting the School; parents may opt out of the disclosure of directory information; complaints may be submitted to NYSED at the address in the Parents' Bill of Rights; and CoachLenz will supplement the School's §2-d supplemental information / annual report on request.

**(b) NIST CSF alignment.** CoachLenz aligns its data-security program to the NIST Cybersecurity Framework 2.0 functions: **Govern, Identify, Protect, Detect, Respond, Recover.**

**(c) Breach notification.** CoachLenz will notify the educational agency of any breach or unauthorized release of student personally identifiable information **without unreasonable delay and in no event later than 7 calendar days after discovery**, in writing, and will cooperate with the agency's notification obligations under §2-d and 8 NYCRR Part 121.

**(d) Civil penalties / indemnification.** CoachLenz acknowledges the civil penalties available under Education Law §2-d. The School indemnifies CoachLenz for penalties, claims, or losses arising from the School's failure to meet its own §2-d obligations (including obtaining required consents); CoachLenz indemnifies the School for penalties, claims, or losses arising from CoachLenz's breach of this Section.

## 5. Biometric Data — BIPA / CUBI / MHMDA
CoachLenz's EAGLE-EYE feature groups plays by **jersey number and general appearance** (e.g., clothing, hairstyle, general look). A coach or administrator confirms the match to a named player profile. CoachLenz does **not** capture, store, or use "biometric identifiers" or "biometric information" — including faceprints, retina/iris scans, or voiceprints — as defined under the Illinois Biometric Information Privacy Act (740 ILCS 14), the Texas Capture or Use of Biometric Identifier Act (Tex. Bus. & Com. Code §503.001), or Washington's biometric statute (RCW 19.375) and the Washington My Health My Data Act (RCW 19.373).

Jersey-number and general-appearance grouping does not constitute a "biometric identifier" because it is not a scan or measurement of a body part capable of uniquely identifying an individual. If CoachLenz ever introduces true facial recognition or faceprint capture, it will, before any such capture: (a) obtain separate written informed consent from each affected individual (or the parent of a minor); (b) publish a written retention and destruction schedule; (c) never sell or profit from biometric data; (d) destroy biometric data at the earlier of the fulfillment of the purpose or **3 years** after the individual's last interaction; and (e) keep the feature **geo-fenced OFF by default** in Illinois, Texas, and Washington.

## 6. Retention and Deletion
- **Retention Period.** CoachLenz retains student film and associated metadata for the duration of the active School contract plus **90 days** after termination.
- **Deletion on termination / request.** Upon contract termination or the School's written request, CoachLenz will delete all student data, **including backups**, within **30 days**, and will provide a written **Deletion Certificate** (see `deletion-certificate-template.md`) specifying the date of deletion, the categories deleted, the deletion method (secure overwrite or cryptographic erasure), and confirmation that backups were purged.
- **Student-uploaded film.** Film uploaded by a student directly (not through a School account) is deleted upon account closure or upon written request, within **14 days**.
- **Florida SB 7026 / 90-day rule.** For Florida Schools, any student safety-related data is deleted within **90 days** of the triggering event unless retention is required by law.

## 7. Governing Law; Dispute Resolution; Liability; Indemnification
- **Governing law.** These Terms are governed by the laws of the **State of Alabama**, without regard to conflict-of-laws rules.
- **Dispute resolution.** Any dispute will be resolved by binding arbitration administered under the rules of a recognized arbitration provider `[FILL-IN: e.g., JAMS or AAA]`, seated in `[FILL-IN county], Alabama`, **except** that either party may seek injunctive or equitable relief in a court of competent jurisdiction to protect its intellectual property or confidential information.
- **Limitation of liability.** Except for a party's indemnification obligations, breach of confidentiality, or a data breach caused by CoachLenz's gross negligence or willful misconduct, each party's aggregate liability is capped at the **fees paid by the School in the 12 months** preceding the claim. Neither party is liable for indirect, incidental, or consequential damages.
- **Indemnification.** Each party indemnifies the other for third-party claims arising from its own negligence or willful misconduct and, for the School, from its failure to obtain required parental/eligible-student consents.

## 8. General
CoachLenz processes data only per these Terms and the accompanying Data Privacy Agreement, which controls in the event of a conflict regarding student data. CoachLenz will not materially reduce the protections in these Terms without notice to the School. Sub-processors are listed in the Privacy Policy; CoachLenz remains responsible for their compliance.

*Prepared as a draft for attorney review. Cosby AI Solutions LLC · Jason L. Cosby, Founder & CEO · legal@coachlenz.com*
