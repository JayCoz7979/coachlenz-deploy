// Refresh app/sitemap-data.json with each public route's real last-content-change date
// (the git commit date of its source file), merged over the committed values. If git is
// unavailable (e.g. a container build with no history), the committed dates are kept, so
// sitemap lastmod is always a real content date and never one build timestamp across
// every URL. Wired into `npm run build`; safe to run anytime. Never fails the build.
import { execSync } from 'node:child_process'
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

try {
  const here = dirname(fileURLToPath(import.meta.url))
  const frontend = join(here, '..')
  const outFile = join(frontend, 'app', 'sitemap-data.json')

  // route -> the source file whose history is the content's last-change signal
  const ROUTES = {
    '/': 'app/HomeView.tsx',
    '/tools/film-time-saved': 'app/tools/film-time-saved/page.tsx',
    '/sample/football': 'app/sample/[sport]/page.tsx',
    '/sample/flag': 'app/sample/[sport]/page.tsx',
    '/sample/basketball': 'app/sample/[sport]/page.tsx',
    '/terms': 'app/terms/page.tsx',
    '/privacy': 'app/privacy/page.tsx',
  }

  const existing = existsSync(outFile) ? JSON.parse(readFileSync(outFile, 'utf8')) : {}
  const out = { ...existing }

  for (const [route, file] of Object.entries(ROUTES)) {
    try {
      const d = execSync(`git log -1 --follow --format=%cs -- "${file}"`, {
        cwd: frontend,
        stdio: ['ignore', 'pipe', 'ignore'],
      })
        .toString()
        .trim()
      if (/^\d{4}-\d{2}-\d{2}$/.test(d)) out[route] = d
    } catch {
      // git missing or file unknown here: keep the committed date
    }
  }

  writeFileSync(outFile, JSON.stringify(out, null, 2) + '\n')
  console.log('[gen-sitemap-dates] updated', outFile)
} catch (e) {
  console.warn('[gen-sitemap-dates] skipped:', e && e.message)
  process.exit(0)
}
