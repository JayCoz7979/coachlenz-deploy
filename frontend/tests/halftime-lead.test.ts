// Free Halftime Sheet PDF (double opt-in) form helpers. Run: `npm test` (Node >= 22.18 strips types natively).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  CONSENT_LINE, clientLeadError, leadPayload, confirmErrorView, detailMessage,
} from '../components/live/halftimeLead.ts'

const ok = { name: 'Test Coach', email: 'qa.coach@example.com', phone: '', consent: true, company: '' }

test('name, valid email, and consent are required; phone is optional', () => {
  assert.equal(clientLeadError(ok), '')
  assert.match(clientLeadError({ ...ok, name: ' ' }), /name/)
  assert.match(clientLeadError({ ...ok, email: 'nope' }), /valid email/)
  assert.match(clientLeadError({ ...ok, consent: false }), /tick the box/)
  assert.equal(leadPayload(ok).phone, null)
  assert.equal(leadPayload({ ...ok, phone: ' 555 010 0000 ' }).phone, '555 010 0000')
})

test('honeypot is passed through so the server can drop bots', () => {
  assert.equal(leadPayload({ ...ok, company: 'bot' }).company, 'bot')
})

test('expired and used links offer a one-tap resend; unknown links ask for the email', () => {
  assert.deepEqual(confirmErrorView(410, { code: 'token_expired', message: 'expired' }),
    { kind: 'expired', message: 'expired', canResendWithToken: true })
  assert.equal(confirmErrorView(410, { code: 'token_used', message: 'used' }).kind, 'used')
  assert.equal(confirmErrorView(502, { code: 'pdf_send_failed', message: 'x' }).kind, 'pdf_failed')
  const inv = confirmErrorView(400, { code: 'token_invalid', message: 'bad' })
  assert.equal(inv.kind, 'invalid')
  assert.equal((inv as any).canResendWithToken, false)
  assert.match(detailMessage({ response: { status: 429 } }, 'x'), /wait a minute/)
})

test('consent copy is honest: no SMS promises, phone never texted', () => {
  assert.match(CONSENT_LINE, /never texted/)
  assert.doesNotMatch(CONSENT_LINE.toLowerCase(), /\bsms\b|free forever/)
})

test('the PDF is never offered as a browser download, and confirm needs a click', () => {
  const form = readFileSync(new URL('../components/live/HalftimePdfForm.tsx', import.meta.url), 'utf8')
  const page = readFileSync(new URL('../app/live-tracker/halftime-sheet/confirm/page.tsx', import.meta.url), 'utf8')
  for (const src of [form, page]) {
    assert.doesNotMatch(src, /download=|\.pdf['"]|application\/pdf/)
  }
  assert.match(form, /href="\/privacy"/)
  // Confirm is POSTed from a button, not fired on page load (scanner-safe single use).
  assert.match(page, /onClick=\{confirm\}/)
  assert.doesNotMatch(page, /useEffect\(\(\) => \{\s*confirm\(\)/)
})

test('primary form controls are at least 44px tall', () => {
  const form = readFileSync(new URL('../components/live/HalftimePdfForm.tsx', import.meta.url), 'utf8')
  for (const m of form.matchAll(/minHeight: (\d+)/g)) assert.ok(Number(m[1]) >= 44, m[0])
})
