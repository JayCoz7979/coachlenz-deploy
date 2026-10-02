import { test, expect, Page } from '@playwright/test'

// Read-only public-surface health. SAFE against any target: every non-GET request is
// aborted (belt-and-suspenders so no telemetry/lead write fires), and we only assert
// page health (no uncaught console errors, no 4xx/5xx, no broken images).

const PUBLIC_ROUTES = ['/', '/book', '/login', '/privacy', '/terms', '/tools/film-time-saved']
const PROTECTED_ROUTES = ['/dashboard', '/games', '/reports', '/settings/billing']

async function guard(page: Page, errors: string[], netErrors: string[]) {
  // Block any write the browser would make (public QA must not mutate anything).
  await page.route('**/*', (route) => {
    const m = route.request().method()
    if (m !== 'GET' && m !== 'HEAD') return route.abort()
    return route.continue()
  })
  page.on('console', (msg) => { if (msg.type() === 'error') errors.push(msg.text()) })
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('response', (r) => { if (r.status() >= 400 && r.request().method() === 'GET') netErrors.push(`${r.status()} ${r.url()}`) })
}

for (const route of PUBLIC_ROUTES) {
  test(`public ${route} renders clean`, async ({ page }) => {
    const errors: string[] = []
    const netErrors: string[] = []
    await guard(page, errors, netErrors)
    await page.goto(route, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(1500)
    // No application console errors. (API calls aborted/blocked by the guard are
    // expected when there is no backend; filter those so the gate tests real bugs.)
    const appErrors = errors.filter(e =>
      !/ERR_CONNECTION_REFUSED|Failed to load resource|ERR_FAILED|net::ERR_ABORTED/i.test(e))
    expect(appErrors, `console errors on ${route}`).toEqual([])
    // No broken same-origin GET assets (ignore blocked cross-origin writes).
    const assetErrors = netErrors.filter(e => !/cal\.com|analytics|funnel|track/i.test(e))
    expect(assetErrors, `failed GET requests on ${route}`).toEqual([])
    // Page actually painted something.
    expect(await page.locator('body').innerText()).not.toEqual('')
  })
}

for (const route of PROTECTED_ROUTES) {
  test(`protected ${route} redirects a logged-out visitor to login (no data leak)`, async ({ page }) => {
    const errors: string[] = []
    const netErrors: string[] = []
    await guard(page, errors, netErrors)
    await page.goto(route, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(1500)
    // Must land on /login (or show the login form), never render the protected app.
    const url = page.url()
    const onLogin = /\/login/.test(url) || (await page.locator('input[type="password"]').count()) > 0
    expect(onLogin, `${route} should redirect a logged-out user to login, got ${url}`).toBeTruthy()
  })
}
