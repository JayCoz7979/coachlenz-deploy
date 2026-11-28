// Free printable Halftime Sheet form on /live-tracker: copy and form-contract guards.
// Run: `npm test`. Reads source files; no browser needed.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const form = readFileSync(new URL('../components/live/HalftimePdfForm.tsx', import.meta.url), 'utf8')
const page = readFileSync(new URL('../app/live-tracker/page.tsx', import.meta.url), 'utf8')
const backend = readFileSync(new URL('../../backend/routers/lead_magnet.py', import.meta.url), 'utf8')

test('consent line shown to the visitor matches the text stored with the lead', () => {
  const fe = /HALFTIME_PDF_CONSENT =\s*'([^']+)'/.exec(form)?.[1]
  const block = /CONSENT_TEXT = \(([\s\S]*?)\)\n/.exec(backend)?.[1] ?? ''
  const be = [...block.matchAll(/"([^"]*)"/g)].map(m => m[1]).join('')
  assert.ok(fe && be)
  assert.equal(fe, be)
  // The rendered sentence (split around the Privacy Policy link) says the same thing.
  assert.ok(form.includes('I agree that CoachLenz may email me the Halftime Sheet and follow-up about CoachLenz. See the'))
  assert.ok(form.includes('href="/privacy"'))
})

test('phone is optional: labeled optional and never required', () => {
  const phoneInput = /<input id="hs-phone"[\s\S]*?\/>/.exec(form)?.[0] ?? ''
  assert.ok(phoneInput, 'phone input exists')
  assert.ok(!/\brequired\b/.test(phoneInput))
  assert.ok(form.includes('(optional)'))
  assert.ok(form.includes("phone: phone.trim() || null"))
})

test('honeypot field is present, hidden from people, and sent to the server', () => {
  assert.ok(form.includes('name="website"'))
  assert.ok(form.includes('tabIndex={-1}'))
  assert.ok(form.includes('aria-hidden="true"'))
  assert.ok(/consent, website,/.test(form))
})

// Visitor-facing copy only: drop code comments (they list the banned phrases on purpose).
const stripComments = (src) => src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')

test('no SMS or "free forever" copy; the $7 offer stays the gold primary CTA', () => {
  for (const src of [form, page]) {
    const low = stripComments(src).toLowerCase()
    for (const banned of ['sms', 'text message', 'free forever', 'no card', '$0']) {
      assert.ok(!low.includes(banned), `found "${banned}"`)
    }
  }
  assert.ok(!form.includes("var(--gold)', color: '#1c1c1c'"), 'PDF button must not look like the $7 CTA')
  assert.ok(page.includes('<HalftimePdfForm />'))
})

test('form controls are at least 44px tall for phone use', () => {
  for (const m of form.matchAll(/minHeight: (\d+)/g)) assert.ok(Number(m[1]) >= 44, `minHeight ${m[1]}`)
})
