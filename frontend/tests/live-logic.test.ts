// Live Game logger logic tests. Run: `npm test` (Node >= 22.18 strips TS types natively).
// Kept out of the Next typecheck (tsconfig "exclude": ["tests"]).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  normalizeServerPlay, playSummary, stripForMode, clearAfterLog, autoPoints,
  resolvePoints, needsScoreEntry, applyPoints, lastScore, TAP_MIN,
} from '../components/live/logic.ts'
import { safeNext } from '../lib/postAuth.ts'

// ── Play Log display after reload ────────────────────────────────────────────
test('reloaded opponent play shows its play type, never "null yd"', () => {
  // Exactly what GET /live/session/{id} returned before the backend fix.
  const server = {
    event_id: 'e1', side: 'defense', possession: 'them', down: 2, distance: 7,
    play_type: null, yards_gained: null, result: 'Stop at Line', player: null,
    extra: { possession: 'them', opp_play_type: 'Pass', opp_route: 'Slant', opp_formation: 'Shotgun' },
  }
  const p = normalizeServerPlay(server)
  assert.equal(p.opp_play_type, 'Pass')
  assert.equal(p.synced, true)
  assert.equal(p.client_uid, 'e1')
  const s = playSummary(p, false)
  assert.ok(s.includes('Pass'), s)
  assert.ok(!/null|undefined/.test(s), s)
  assert.ok(!s.includes(' yd'), s)
  assert.equal(s, '2&7 · Pass · Slant · Stop at Line')
})

test('zero yards still renders, null yards does not', () => {
  assert.ok(playSummary({ play_type: 'Run', yards_gained: 0 }, false).includes('0 yd'))
  assert.ok(!playSummary({ play_type: 'Run', yards_gained: null }, false).includes('yd'))
  assert.ok(!playSummary({ play_type: 'Run', yards_gained: '' }, false).includes('yd'))
})

test('special teams row reads its unit, not a leaked opponent play type', () => {
  const legacy = { side: 'special_teams', st_unit: 'Punt Return', opp_play_type: 'Run', result: 'Returned', st_yards: 12 }
  assert.equal(playSummary(legacy, false), 'Punt Return · 12 yd · Returned')
})

// ── Special Teams does not inherit the previous play ─────────────────────────
test('special teams play strips the previous defensive play fields', () => {
  const afterDefense = {
    down: '2', distance: '7', opp_formation: 'Shotgun', opp_play_type: 'Run', coverage: 'Cover 3',
    st_unit: 'Punt Return', st_result: 'Returned', result: 'Returned', returner_jersey: '5',
  }
  const st = stripForMode(afterDefense, 'st', false, false)
  assert.equal(st.opp_formation, undefined)
  assert.equal(st.opp_play_type, undefined)
  assert.equal(st.coverage, undefined)
  assert.equal(st.down, undefined)
  assert.equal(st.st_unit, 'Punt Return')
  assert.equal(st.returner_jersey, '5')
})

test('offense play drops opponent fields; defense play drops offense fields', () => {
  const mixed = { play_type: 'Run', route: 'Slant', opp_play_type: 'Pass', opp_formation: 'Spread', down: '1' }
  assert.deepEqual(stripForMode(mixed, 'us', false, false), { play_type: 'Run', route: 'Slant', down: '1' })
  assert.deepEqual(stripForMode(mixed, 'them', false, false), { opp_play_type: 'Pass', opp_formation: 'Spread', down: '1' })
})

test('after logging, only down / distance / ball-on carry over', () => {
  assert.deepEqual(clearAfterLog({ down: '3', distance: '4', field_position: 'OWN 40', opp_play_type: 'Run', result: 'x' }),
    { down: '3', distance: '4', field_position: 'OWN 40' })
})

// ── score taps update the score the report reads ─────────────────────────────
test('Touchdown on our ball adds 6 to us', () => {
  const pts = resolvePoints('football', 'us', { result: 'Touchdown' })
  assert.deepEqual(pts, { team: 'us', points: 6 })
  assert.deepEqual(applyPoints(0, 0, pts), { us: 6, them: 0 })
})

test('Touchdown Allowed on defense adds 6 to them (flag football too)', () => {
  assert.deepEqual(resolvePoints('flag_football', 'them', { result: 'Touchdown Allowed' }), { team: 'them', points: 6 })
  assert.deepEqual(resolvePoints('football', 'them', { opp_outcome: 'Touchdown Allowed' }), { team: 'them', points: 6 })
})

test('field goal and extra point made', () => {
  assert.deepEqual(resolvePoints('football', 'st', { st_unit: 'Field Goal Attempt', st_result: 'Made' }), { team: 'us', points: 3 })
  assert.deepEqual(resolvePoints('football', 'st', { st_unit: 'Extra Point', st_result: 'Made', points_team: 'them' }), { team: 'them', points: 1 })
})

test('basketball possession results and points allowed', () => {
  assert.deepEqual(autoPoints('basketball', 'us', { possession_result: '3 pts' }), { team: 'us', points: 3 })
  assert.deepEqual(autoPoints('basketball', 'them', { result: 'Gave Up 2' }), { team: 'them', points: 2 })
})

test('Quick Log "Score" requires a points pick (football), and a pick wins', () => {
  const cur = { result: 'Score', play_type: 'Run' }
  assert.equal(resolvePoints('football', 'us', cur, true), null)
  assert.equal(needsScoreEntry('football', 'us', cur, true), true)
  const picked = { ...cur, points_scored: 6, points_team: 'us' }
  assert.equal(needsScoreEntry('football', 'us', picked, true), false)
  assert.deepEqual(resolvePoints('football', 'us', picked, true), { team: 'us', points: 6 })
  // explicit 0 = "no score" also satisfies the prompt
  assert.equal(needsScoreEntry('football', 'us', { ...cur, points_scored: 0 }, true), false)
  assert.equal(resolvePoints('football', 'us', { ...cur, points_scored: 0 }, true), null)
})

test('basketball quick Score uses the Points field', () => {
  assert.deepEqual(resolvePoints('basketball', 'us', { result: 'Score', yards_gained: '3' }, true), { team: 'us', points: 3 })
})

test('undo subtracts and never goes negative; reload restores last score', () => {
  assert.deepEqual(applyPoints(6, 3, { team: 'us', points: 6 }, -1), { us: 0, them: 3 })
  assert.deepEqual(applyPoints(0, 0, { team: 'them', points: 3 }, -1), { us: 0, them: 0 })
  assert.deepEqual(lastScore([{ score_us: 6, score_them: 0 }, { score_us: 6, score_them: 7 }, {}]), { us: 6, them: 7 })
  assert.deepEqual(lastScore([]), { us: 0, them: 0 })
})

test('non-scoring plays add nothing', () => {
  assert.equal(resolvePoints('football', 'us', { result: 'First Down' }), null)
  assert.equal(needsScoreEntry('football', 'us', { result: 'First Down' }), false)
})

// ── tap targets ──────────────────────────────────────────────────────────────
test('sideline tap minimum is 44px', () => {
  assert.equal(TAP_MIN, 44)
})

// ── post-auth return path ────────────────────────────────────────────────────
test('safeNext only allows same-site paths', () => {
  assert.equal(safeNext('/live-tracker?checkout=1'), '/live-tracker?checkout=1')
  assert.equal(safeNext('//evil.example'), null)
  assert.equal(safeNext('https://evil.example'), null)
  assert.equal(safeNext('/\\evil.example'), null)
  assert.equal(safeNext(''), null)
})
