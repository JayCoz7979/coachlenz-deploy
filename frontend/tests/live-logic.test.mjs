// Live Game Logger pure logic. Run: npm test  (Node >= 22.18 strips TS types natively)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  normalizeServerPlay, playSummary, cleanForMode, resetForMode, scoreForPlay, scoreFromPlays,
  pointChips, REPORT_ACTIONS, MIN_TAP,
} from '../components/live/logic.ts'

// ── Play Log after reload ────────────────────────────────────────────────────
// Shape returned by GET /live/session/{id} for a defensive play.
const reloadedDefense = {
  event_id: 'e1', side: 'defense', possession: 'them', down: 2, distance: 7,
  play_type: null, yards_gained: null, result: 'Stop at Line', player: null,
  extra: { possession: 'them', quarter: 1, opp_play_type: 'Run', opp_formation: 'Shotgun', opp_run_concept: 'Sweep' },
}

test('reloaded opponent play shows its play type, never "play · null yd"', () => {
  const s = playSummary(normalizeServerPlay(reloadedDefense), false)
  assert.equal(s, '2&7 · Run · Sweep · Stop at Line')
  assert.doesNotMatch(s, /null|undefined/)
  assert.doesNotMatch(s, /^play\b/)
})

test('normalizeServerPlay fills nulls from extra but never overrides a real column', () => {
  const p = normalizeServerPlay({ play_type: 'Pass', yards_gained: null, extra: { play_type: 'Run', yards_gained: 5, st_unit: 'Punt' } })
  assert.equal(p.play_type, 'Pass')
  assert.equal(p.yards_gained, 5)
  assert.equal(p.st_unit, 'Punt')
})

test('summary skips missing yards and shows real ones', () => {
  assert.equal(playSummary({ side: 'offense', play_type: 'Run', yards_gained: null }, false), 'Run')
  assert.equal(playSummary({ side: 'offense', play_type: 'Run', yards_gained: 0 }, false), 'Run · 0 yd')
  assert.equal(playSummary({ side: 'offense', play_type: 'Run', yards_gained: -3 }, false), 'Run · -3 yd')
})

test('special teams summary uses the unit, not a stale play type', () => {
  const s = playSummary({ side: 'special_teams', st_unit: 'Kickoff Return', st_result: 'Returned', result: 'Returned', play_type: 'Run', down: 1, distance: 10 }, false)
  assert.equal(s, 'Kickoff Return · Returned')
})

test('basketball reloaded defense play reads opponent action and zone', () => {
  const p = normalizeServerPlay({ side: 'defense', possession: 'them', result: 'Gave Up 2', extra: { opp_primary_action: 'Drive', shot_zone_allowed: 'paint', opp_shooter: '3' } })
  assert.equal(playSummary(p, true), 'Drive · paint · #3 · Gave Up 2')
})

// ── Special Teams must not inherit the previous play ─────────────────────────
test('switching to Special Teams drops the previous defensive fields', () => {
  const afterDefense = { down: '3', distance: '4', field_position: 'OWN 30', opp_formation: 'Shotgun', opp_play_type: 'Run', coverage: 'Cover 3', result: 'Stop at Line' }
  assert.deepEqual(resetForMode(afterDefense, 'st', false), {})
  const st = cleanForMode({ ...afterDefense, st_unit: 'Kickoff Return', st_result: 'Returned', result: 'Returned' }, 'st', false, false)
  assert.deepEqual(st, { st_unit: 'Kickoff Return', st_result: 'Returned', result: 'Returned' })
  assert.equal(playSummary({ side: 'special_teams', ...st }, false), 'Kickoff Return · Returned')
})

test('switching offense <-> defense keeps only down/distance/ball-on', () => {
  const cur = { down: '2', distance: '6', field_position: 'OPP 40', play_type: 'Pass', route: 'Slant', target_jersey: '80' }
  assert.deepEqual(resetForMode(cur, 'them', false), { down: '2', distance: '6', field_position: 'OPP 40' })
  const def = cleanForMode({ ...cur, opp_play_type: 'Run' }, 'them', false, false)
  assert.equal(def.play_type, undefined)
  assert.equal(def.route, undefined)
  assert.equal(def.opp_play_type, 'Run')
})

test('basketball unit switch clears the other side', () => {
  const cur = { ball_entry: 'Transition', shooter_jersey: '11', possession_result: '2 pts' }
  assert.deepEqual(resetForMode(cur, 'them', true), {})
  assert.deepEqual(cleanForMode({ ...cur, defensive_set: 'Man' }, 'them', true, false), { defensive_set: 'Man' })
})

test('quick log keeps only quick fields', () => {
  assert.deepEqual(cleanForMode({ play_type: 'Run', result: 'Score', yards_gained: '7', route: 'Post', down: '1' }, 'us', true, true),
    { play_type: 'Run', result: 'Score', yards_gained: '7' })
})

// ── score taps update the score the report reads ─────────────────────────────
test('football Touchdown adds 6 to us', () => {
  assert.deepEqual(scoreForPlay({ result: 'Touchdown' }, 'us', false, false), { team: 'us', points: 6, needsEntry: false })
})

test('Touchdown Allowed (result or outcome) adds 6 to them', () => {
  assert.deepEqual(scoreForPlay({ result: 'Touchdown Allowed' }, 'them', false, false), { team: 'them', points: 6, needsEntry: false })
  assert.deepEqual(scoreForPlay({ opp_outcome: 'Touchdown Allowed' }, 'them', false, false), { team: 'them', points: 6, needsEntry: false })
})

test('made field goal and extra point score for us', () => {
  assert.equal(scoreForPlay({ st_unit: 'Field Goal Attempt', st_result: 'Made' }, 'st', false, false).points, 3)
  assert.equal(scoreForPlay({ st_unit: 'Extra Point', st_result: 'Made' }, 'st', false, false).points, 1)
  assert.equal(scoreForPlay({ st_unit: 'Field Goal Attempt', st_result: 'Missed' }, 'st', false, false), null)
})

test('quick-log "Score" asks for the points in football instead of guessing', () => {
  assert.deepEqual(scoreForPlay({ result: 'Score' }, 'us', false, true), { team: 'us', points: 0, needsEntry: true })
  assert.deepEqual(scoreForPlay({ result: 'Score' }, 'them', false, true), { team: 'them', points: 0, needsEntry: true })
})

test('basketball points come from the possession result', () => {
  assert.equal(scoreForPlay({ possession_result: '3 pts' }, 'us', true, false).points, 3)
  assert.equal(scoreForPlay({ possession_result: '1 pt FT' }, 'us', true, false).points, 1)
  assert.equal(scoreForPlay({ result: 'Gave Up 2' }, 'them', true, false).points, 2)
  assert.equal(scoreForPlay({ shot_result: 'Made' }, 'us', true, false).needsEntry, true)
  assert.equal(scoreForPlay({ result: 'Score', yards_gained: '3' }, 'us', true, true).points, 3)
})

test('non-scoring plays do not touch the score', () => {
  for (const [p, m] of [[{ result: 'First Down' }, 'us'], [{ result: 'Stop at Line' }, 'them'], [{ possession_result: 'Missed' }, 'us']]) {
    assert.equal(scoreForPlay(p, m, m === 'us' && 'possession_result' in p, false), null)
  }
})

test('score boxes restore from logged plays after reload', () => {
  assert.deepEqual(scoreFromPlays([{ score_us: 0, score_them: 0 }, { score_us: 6, score_them: 0 }, { extra: { score_us: 6, score_them: 7 } }]), { us: 6, them: 7 })
  assert.deepEqual(scoreFromPlays([]), { us: 0, them: 0 })
})

test('point chips include a touchdown for football only', () => {
  assert.deepEqual(pointChips(false), [1, 2, 3, 6])
  assert.deepEqual(pointChips(true), [1, 2, 3])
})

// ── Halftime Sheet is the first-class action ─────────────────────────────────
test('the first, primary report action is the Halftime Sheet (scope halftime)', () => {
  assert.equal(REPORT_ACTIONS[0].scope, 'halftime')
  assert.equal(REPORT_ACTIONS[0].label, 'Halftime Sheet')
  assert.equal(REPORT_ACTIONS[0].primary, true)
  assert.equal(REPORT_ACTIONS.filter(a => a.primary).length, 1)
  assert.ok(REPORT_ACTIONS.some(a => a.scope === 'full'))
})

test('minimum tap target is 44px', () => {
  assert.equal(MIN_TAP, 44)
})
