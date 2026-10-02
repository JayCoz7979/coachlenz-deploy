import { defineConfig } from '@playwright/test'

// CoachLenz QA regression gate. Target is configurable; defaults to the local dev
// server. See README.md for the safety model (public specs are safe anywhere;
// write/auth specs require QA_ALLOW_WRITES=1 + a local dry-run stack).
export default defineConfig({
  testDir: '.',
  timeout: 60_000,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: {
    baseURL: process.env.QA_BASE_URL || 'http://localhost:3000',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
})
