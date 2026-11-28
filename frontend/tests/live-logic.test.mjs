// Live Game Logger unit tests. Run: `npm test` (Node >= 22.18 / 23.6 strips the
// TypeScript types of logic.ts natively; no extra dependency). Fictional data only.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import {
  TAP_MIN, resetEntry, stripForeign, switchPlayType, scoreDelta, applyScore,
  playSummary, restoreFromPlays, paywallFromError, PAYWALL_CODE,
} from '../components/live/logic.ts'

const here = path.dirname(fileURLToPath(import.meta.url))
const src = (rel) => readFileSync(path.join(here, '..', rel), 'utf8')

// ── Play Log display (bug: "play · null yd" after reload) ────────────────────
test('opponent play from the server shows its play type, never null', () => {
  // Shape GET /live/session returns after the backend fix (opp fields promoted).
  const p = { side: 'defense', possession: 'them', down: 2, distance: 7, play_type: null,
    yards_gained: null, opp_play_type: 'Run', result: 'Stop at Line', extra: { opp_play_type: 'Run' } }
  const s = playSummary(p, false)
  assert.match(s, /Run/)
  assert.doesNotMatch(s, /null|undefined/)
})

test('opponent play still readable when the detail only lives under extra', () => {
  const p = { side: 'defense', play_type: null, yards_gained: null,
    extra: { opp_play_type: 'Pass', opp_route: 'Slant', opp_target: '10' } }
  const s = playSummary(p, false)
  assert.match(s, /Pass/)
  assert.match(s, /Slant/)
  assert.doesNotMatch(s, /null/)
})

test('special teams row shows the unit and its own result', () => {
  const s = playSummary({ side: 'special_teams', st_unit: 'Punt', st_result: 'Downed', st_yards: 38 }, false)
  assert.equal(s, 'Punt · 38 yd · Downed')
})

test('basketball row', () => {
  const s = playSummary({ ball_entry: 'Pick and Roll', shot_zone: 'top3', possession_result: '3 pts', shooter_jersey: '1' }, true)
  assert.equal(s, 'Pick and Roll · top3 · 3 pts · #1')
})

// ── Special Teams leak (bug: "Run · Returned") ───────────────────────────────
test('special teams right after a Their Ball run logs no opp fields', () => {
  const afterRun = { down: '2', distance: '6', field_position: 'OWN 30',
    opp_formation: 'Spread', opp_play_type: 'Run', opp_run_gap: 'A', result: 'Stop at Line' }
  const cur = resetEntry(afterRun)               // what a mode switch does
  assert.deepEqual(cur, { down: '2', distance: '6', field_position: 'OWN 30' })
  const st = stripForeign('st', { ...afterRun, st_unit: 'Kickoff Return', st_result: 'Returned' })
  assert.equal(st.opp_formation, undefined)
  assert.equal(st.opp_play_type, undefined)
  assert.equal(st.opp_run_gap, undefined)
  assert.equal(st.st_unit, 'Kickoff Return')
  assert.doesNotMatch(playSummary({ side: 'special_teams', ...st }, false), /Run/)
})

test('special teams right after an Our Ball pass logs no offense fields', () => {
  const st = stripForeign('st', { play_type: 'Pass', route: 'Post', target_jersey: '7', st_unit: 'Punt' })
  assert.deepEqual(st, { st_unit: 'Punt' })
})

test('Our Ball never carries opponent or special teams fields', () => {
  const us = stripForeign('us', { play_type: 'Run', opp_play_type: 'Pass', st_unit: 'Punt', coverage: 'Zone' })
  assert.deepEqual(us, { play_type: 'Run' })
})

test('switching run -> pass clears run-only fields', () => {
  const next = switchPlayType({ play_type: 'Run', run_gap: 'B', ball_carrier_jersey: '22', down: '1' }, 'play_type', 'Pass')
  assert.deepEqual(next, { play_type: 'Pass', down: '1' })
  const back = switchPlayType({ opp_play_type: 'Pass', opp_route: 'Out', opp_target: '10' }, 'opp_play_type', 'Run')
  assert.deepEqual(back, { opp_play_type: 'Run' })
})

test('quick log keeps its own fields', () => {
  assert.deepEqual(stripForeign('us', { play_type: 'Special Teams', result: 'Score' }, true),
    { play_type: 'Special Teams', result: 'Score' })
})

// ── Score taps (bug: score boxes stayed 0-0) ─────────────────────────────────
test('football touchdown / allowed / FG / PAT move the right side', () => {
  assert.deepEqual(scoreDelta('football', 'us', { result: 'Touchdown' }), { us: 6, them: 0 })
  assert.deepEqual(scoreDelta('flag_football', 'us', { result: 'Touchdown' }), { us: 6, them: 0 })
  assert.deepEqual(scoreDelta('football', 'them', { result: 'Touchdown Allowed' }), { us: 0, them: 6 })
  assert.deepEqual(scoreDelta('football', 'them', { opp_outcome: 'Touchdown Allowed' }), { us: 0, them: 6 })
  assert.deepEqual(scoreDelta('football', 'st', { st_unit: 'Field Goal Attempt', st_result: 'Made' }), { us: 3, them: 0 })
  assert.deepEqual(scoreDelta('football', 'st', { st_unit: 'Extra Point', st_result: 'Made' }), { us: 1, them: 0 })
  assert.deepEqual(scoreDelta('football', 'st', { st_unit: 'Field Goal Attempt', st_result: 'Missed' }), { us: 0, them: 0 })
  assert.deepEqual(scoreDelta('football', 'us', { result: 'First Down' }), { us: 0, them: 0 })
})

test('basketball made shots and allowed scores', () => {
  assert.deepEqual(scoreDelta('basketball', 'us', { possession_result: '3 pts' }), { us: 3, them: 0 })
  assert.deepEqual(scoreDelta('basketball', 'us', { possession_result: '1 pt FT' }), { us: 1, them: 0 })
  assert.deepEqual(scoreDelta('basketball', 'us', { shot_result: 'Made', shot_zone: 'corner3_left' }), { us: 3, them: 0 })
  assert.deepEqual(scoreDelta('basketball', 'us', { shot_result: 'Made', shot_zone: 'paint' }), { us: 2, them: 0 })
  assert.deepEqual(scoreDelta('basketball', 'us', { shot_result: 'Missed', shot_zone: 'paint' }), { us: 0, them: 0 })
  assert.deepEqual(scoreDelta('basketball', 'them', { result: 'Gave Up 3' }), { us: 0, them: 3 })
  assert.deepEqual(scoreDelta('basketball', 'them', { result: 'Stop - Missed' }), { us: 0, them: 0 })
})

test('quick log Score: football 6, basketball uses the Points box', () => {
  assert.deepEqual(scoreDelta('football', 'us', { result: 'Score' }, true), { us: 6, them: 0 })
  assert.deepEqual(scoreDelta('football', 'them', { result: 'Score' }, true), { us: 0, them: 6 })
  assert.deepEqual(scoreDelta('basketball', 'us', { result: 'Score', yards_gained: '3' }, true), { us: 3, them: 0 })
  assert.deepEqual(scoreDelta('basketball', 'us', { result: 'Positive' }, true), { us: 0, them: 0 })
})

test('score taps add on top of a manual edit', () => {
  // Coach hand-corrected 7-0 (TD + PAT), then a field goal is tapped.
  const d = scoreDelta('football', 'st', { st_unit: 'Field Goal Attempt', st_result: 'Made' })
  assert.deepEqual(applyScore('7', '0', d), ['10', '0'])
  assert.deepEqual(applyScore('', 'x', { us: 6, them: 0 }), ['6', '0'])
})

// ── Reload restores score / period / possession ──────────────────────────────
test('reload restores the last play state', () => {
  const plays = [
    { quarter: 1, possession: 'us', score_us: 0, score_them: 0 },
    { quarter: 2, possession: 'them', side: 'defense', score_us: 6, score_them: 7 },
  ]
  assert.deepEqual(restoreFromPlays(plays, false), { scoreUs: '6', scoreThem: '7', period: '2', mode: 'them' })
  assert.deepEqual(restoreFromPlays([{ half: 3, score_us: 40, score_them: 41 }], true),
    { scoreUs: '40', scoreThem: '41', period: 'OT', mode: 'us' })
  assert.deepEqual(restoreFromPlays([], false), { scoreUs: '0', scoreThem: '0', period: null, mode: null })
})

// ── Paywall ──────────────────────────────────────────────────────────────────
test('paywall 403 is recognised, other errors are not', () => {
  const pw = paywallFromError({ response: { status: 403, data: { detail: {
    code: PAYWALL_CODE, message: 'The Live Tracker is a $7 one-time unlock.', checkout_url: '/live-tracker' } } } })
  assert.deepEqual(pw, { message: 'The Live Tracker is a $7 one-time unlock.', checkoutUrl: '/live-tracker' })
  assert.equal(paywallFromError({ response: { status: 403, data: { detail: { code: 'student_consent_required' } } } }), null)
  assert.equal(paywallFromError({ response: { status: 500, data: {} } }), null)
  assert.equal(paywallFromError(null), null)
  // An off-site checkout link from a bad response is never followed.
  assert.equal(paywallFromError({ response: { status: 403, data: { detail: { code: PAYWALL_CODE, checkout_url: 'https://evil.example' } } } }).checkoutUrl, '/live-tracker')
})

// ── Halftime CTA + tap targets (static source checks) ────────────────────────
test('logger page has a first-class Halftime Sheet button that sends scope halftime', () => {
  const page = src('app/live/[id]/page.tsx')
  assert.match(page, /data-testid="halftime-sheet" onClick=\{\(\) => report\('halftime'\)\}/)
  assert.match(page, /\/>\}\s*Halftime Sheet\s*\n/)
})

test('primary sideline controls are at least 44px tall', () => {
  assert.equal(TAP_MIN, 44)
  for (const rel of ['app/live/[id]/page.tsx', 'app/live/page.tsx', 'components/live/Selectors.tsx', 'app/live-tracker/page.tsx']) {
    const text = src(rel)
    for (const m of text.matchAll(/minHeight:\s*(\d+)/g)) {
      assert.ok(Number(m[1]) >= 44, `${rel}: minHeight ${m[1]} < 44`)
    }
  }
  const page = src('app/live/[id]/page.tsx')
  // score boxes, clock, filter, and the back link use TAP_MIN
  assert.match(page, /aria-label="Our score"[^\n]*minHeight: TAP_MIN/)
  assert.match(page, /aria-label="Their score"[^\n]*minHeight: TAP_MIN/)
  assert.match(page, /aria-label="Game clock"[^\n]*minHeight: TAP_MIN/)
  assert.match(page, /← games/)
  assert.match(page, /href="\/live" style=\{\{[^}]*minHeight: TAP_MIN/)
  // Down 1-4 sits on its own full-width row (no 3-column squeeze at 390px)
  assert.doesNotMatch(page, /gridTemplateColumns: 'repeat\(3, 1fr\)', gap: 10, marginBottom: 12 \}\}>\s*<Field label="Down"/)
  // Yards is no longer squeezed into a 1fr/2fr grid
  assert.doesNotMatch(page, /'1fr 2fr'/)
})

test('no SMS copy and no "free forever" on the logger or landing page', () => {
  for (const rel of ['app/live/[id]/page.tsx', 'app/live/page.tsx', 'app/live-tracker/page.tsx', 'components/live/Paywall.tsx']) {
    // Rendered copy only: drop comments (which document what NOT to say).
    const text = src(rel).replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
    assert.doesNotMatch(text, /\bSMS\b|text message/i, rel)
    assert.doesNotMatch(text, /free forever|no card, ever|\$0 forever/i, rel)
  }
})
