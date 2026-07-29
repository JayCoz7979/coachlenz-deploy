# Student Data Deletion Certificate — Template

> **⚠️ DRAFT — ATTORNEY REVIEW REQUIRED. Not legal advice.**
> The `{{DOUBLE_BRACE}}` fields are **template variables** filled programmatically
> when a certificate is generated (they are not blanks to complete by hand). The
> deletion request/certificate flow (spec 2.3.G) is not yet wired in the product.

---

## STUDENT DATA DELETION CERTIFICATE

**Cosby AI Solutions LLC — CoachLenz**

| Field | Value |
|---|---|
| Certificate ID | {{CERTIFICATE_ID}} |
| Date of deletion | {{DELETION_DATE}} |
| School / district | {{SCHOOL_NAME}} |
| Contract end date | {{CONTRACT_END_DATE}} |
| Deletion request received | {{REQUEST_DATE}} |
| Requested by | {{REQUESTER_NAME}} ({{REQUESTER_ROLE}}) |

**Data categories deleted**
- Student-athlete game film
- Player profile data
- Analysis reports and tendencies
- Performance statistics / grades
- Roster data
{{ADDITIONAL_CATEGORIES}}

**Deletion method:** {{DELETION_METHOD}}  *(secure overwrite or cryptographic erasure)*
**Backup systems purged:** {{BACKUPS_PURGED}}  *(Yes / No)*
**Date backups purged:** {{BACKUP_PURGE_DATE}}

We certify that the student data described above has been deleted from CoachLenz
production systems and backups in accordance with the CoachLenz Data Privacy
Agreement and applicable law, and is not recoverable.

**Certified by:** Jason L. Cosby
**Title:** Founder & CEO, Cosby AI Solutions LLC
**Date certified:** {{CERT_DATE}}
**Contact:** privacy@coachlenz.com

---

*Retain this certificate for your records. Questions: privacy@coachlenz.com.*
