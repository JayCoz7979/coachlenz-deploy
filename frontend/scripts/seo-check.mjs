// SEO release check for app.coachlenz.com. Fetches every sitemap route from a local
// build and fails if any of these is true: status is not 200; the raw HTML is missing
// the route's expected main content; the <title> is missing, empty, or duplicated; the
// canonical is missing or not the absolute production URL; or robots.txt / sitemap.xml
// is missing or invalid. Prints a pass/fail table. Run it before every release.
//
//   SEO_BASE_URL=http://localhost:3100 node scripts/seo-check.mjs
//
// Pages are fetched from the local base, but canonical is validated against the real
// production host, so a local run proves the production URLs without touching the live site.

const BASE = (process.env.SEO_BASE_URL || 'http://localhost:3000').replace(/\/+$/, '')
const CANON_HOST = (process.env.SEO_CANONICAL_HOST || 'https://app.coachlenz.com').replace(/\/+$/, '')

// route -> a distinctive main-content string that must appear in the raw HTML (its H1 or
// a unique line). Legitimately short pages still carry a documented, specific string.
const ROUTES = {
  '/': 'You lose hours breaking down film',
  '/tools/film-time-saved': 'Film Breakdown',
  '/sample/football': 'This is a real CoachLenz game breakdown',
  '/sample/flag': 'This is a real CoachLenz game breakdown',
  '/sample/basketball': 'This is a real CoachLenz game breakdown',
  '/terms': 'Terms of Service',
  '/privacy': 'Privacy Policy',
}

const rows = []
let failed = 0
function record(name, pass, detail) {
  rows.push({ name, pass, detail })
  if (!pass) failed++
}

async function get(path) {
  const res = await fetch(BASE + path, { redirect: 'manual' })
  return { status: res.status, body: await res.text() }
}
function pickTitle(html) {
  const m = html.match(/<title[^>]*>([^<]*)<\/title>/i)
  return m ? m[1].trim() : ''
}
function pickCanonical(html) {
  const m = html.match(/<link[^>]+rel=["']canonical["'][^>]*>/i)
  if (!m) return ''
  const h = m[0].match(/href=["']([^"']+)["']/i)
  return h ? h[1] : ''
}
const norm = (u) => u.replace(/\/+$/, '')

const seenTitles = new Map()

for (const [path, expect] of Object.entries(ROUTES)) {
  try {
    const { status, body } = await get(path)
    const title = pickTitle(body)
    const canon = pickCanonical(body)
    const expectedCanon = norm(CANON_HOST + (path === '/' ? '' : path))
    const problems = []
    if (status !== 200) problems.push(`status ${status}`)
    if (!body.includes(expect)) problems.push(`missing content "${expect}"`)
    if (!title) problems.push('no <title>')
    else if (seenTitles.has(title)) problems.push(`duplicate title (also ${seenTitles.get(title)})`)
    if (title) seenTitles.set(title, path)
    if (!canon) problems.push('no canonical')
    else if (!canon.startsWith(CANON_HOST) || norm(canon) !== expectedCanon)
      problems.push(`canonical not absolute/expected: ${canon}`)
    record(path, problems.length === 0, problems.join('; ') || `200 | "${title}" | ${canon}`)
  } catch (e) {
    record(path, false, `fetch error: ${e.message}`)
  }
}

try {
  const r = await get('/robots.txt')
  const ok = r.status === 200 && /sitemap:/i.test(r.body) && /user-agent/i.test(r.body)
  record('/robots.txt', ok, ok ? 'valid (User-Agent + Sitemap present)' : `status ${r.status} / invalid`)
} catch (e) {
  record('/robots.txt', false, e.message)
}
try {
  const s = await get('/sitemap.xml')
  const ok = s.status === 200 && /<urlset/i.test(s.body) && /<loc>/i.test(s.body)
  record('/sitemap.xml', ok, ok ? 'valid (<urlset> + <loc> present)' : `status ${s.status} / invalid`)
} catch (e) {
  record('/sitemap.xml', false, e.message)
}

const pad = (s, n) => (s + ' '.repeat(n)).slice(0, n)
console.log('\nSEO RELEASE CHECK')
console.log(`fetch base: ${BASE}   canonical host: ${CANON_HOST}`)
console.log(pad('ROUTE', 28) + pad('RESULT', 8) + 'DETAIL')
console.log('-'.repeat(96))
for (const r of rows) console.log(pad(r.name, 28) + pad(r.pass ? 'PASS' : 'FAIL', 8) + r.detail)
console.log('-'.repeat(96))
console.log(`${rows.length - failed}/${rows.length} passed`)
process.exit(failed ? 1 : 0)
