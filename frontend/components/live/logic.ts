// Pure Live Game logger logic: no React, no DOM, no imports. Kept separate so it can be
// unit-tested with `node --test` (see frontend/tests/live-logic.test.ts).
//
// Fixes covered here:
//  * Play Log after reload showed "play · null yd" for opponent plays: the server keeps
//    sport fields in `extra`, and yards can be null. normalizeServerPlay + playSummary.
//  * Special Teams inherited the previous play's opp_formation / opp_play_type:
//    stripForMode keeps only the fields that belong to the play type being logged, and
//    clearAfterLog resets everything except down / distance / ball-on.
//  * Tapping Touchdown / Score never moved the score boxes the report reads:
//    resolvePoints + applyPoints keep score_us / score_them in sync with each play.

export type Mode = 'us' | 'them' | 'st'
export type Team = 'us' | 'them'
export type Points = { team: Team; points: number }
export type AnyPlay = Record<string, any>

// Minimum touch target for primary sideline controls (Apple HIG / WCAG 2.5.5).
export const TAP_MIN = 44

// ── reload / display ─────────────────────────────────────────────────────────
const isBlank = (v: unknown) => v === null || v === undefined || v === ''

/** Flatten a server play's `extra` (sport fields) onto the play, the same shape the
 *  logger built it in. Top-level values win unless they are null/undefined. */
export function normalizeServerPlay(p: AnyPlay): AnyPlay {
  const extra = (p && typeof p.extra === 'object' && p.extra) || {}
  const out: AnyPlay = { ...extra }
  for (const [k, v] of Object.entries(p || {})) {
    if (v !== null && v !== undefined) out[k] = v
    else if (!(k in out)) out[k] = v
  }
  out.synced = true
  out.client_uid = p.client_uid || p.event_id
  return out
}

/** One-line summary for the Play Log row. Never renders "null"/"undefined". */
export function playSummary(p: AnyPlay, isBB: boolean): string {
  const parts: string[] = []
  const push = (v: unknown) => { if (!isBlank(v)) parts.push(String(v)) }
  if (!isBB) {
    const isST = p.side === 'special_teams'
    if (!isST && !isBlank(p.down)) parts.push(`${p.down}&${isBlank(p.distance) ? '' : p.distance}`)
    push(isST ? (p.st_unit || p.play_type || 'Special teams')
      : (p.play_type || p.opp_play_type || p.st_unit || 'play'))
    if (!isST) {
      push(p.route || p.opp_route)
      push(p.run_category || p.opp_run_concept)
    }
    const yards = isST ? p.st_yards : p.yards_gained
    if (!isBlank(yards) && !Number.isNaN(Number(yards))) parts.push(`${Number(yards)} yd`)
  } else {
    push(p.ball_entry || p.opp_primary_action || p.primary_action || 'poss')
    push(p.shot_zone || p.shot_zone_allowed)
    push(p.possession_result || p.shot_result)
  }
  const jersey = p.player || p.ball_carrier_jersey || p.shooter_jersey || p.target_jersey || p.returner_jersey
  if (!isBlank(jersey)) parts.push(`#${jersey}`)
  const result = p.result || p.st_result
  if (!isBlank(result) && !parts.includes(String(result))) parts.push(String(result))
  if (typeof p.points_scored === 'number' && p.points_scored > 0) {
    parts.push(`+${p.points_scored} ${p.points_team === 'them' ? 'them' : 'us'}`)
  }
  return parts.join(' · ')
}

// ── which fields belong to which play type ───────────────────────────────────
const SITUATIONAL = ['down', 'distance', 'field_position']
const COMMON = ['note', 'primary_player_jersey', 'points_scored', 'points_team', 'is_coaching_point']
const FB_OFF = ['formation', 'play_type', 'run_gap', 'rush_lane', 'ball_carrier_jersey', 'run_category',
  'passer_jersey', 'target_jersey', 'route', 'target_area', 'pass_result', 'yards_gained', 'result']
const FB_DEF = ['defensive_front', 'blitz', 'coverage', 'opp_formation', 'opp_play_type', 'opp_run_gap',
  'opp_ball_carrier', 'opp_run_concept', 'opp_passer_jersey', 'opp_target', 'opp_route',
  'stop_maker_jersey', 'result', 'yards_gained', 'opp_outcome']
const FB_ST = ['st_unit', 'kicker_jersey', 'returner_jersey', 'st_result', 'result', 'st_yards']
const BB_OFF = ['ball_handler_jersey', 'shooter_jersey', 'ball_entry', 'primary_action', 'shot_zone',
  'shot_x', 'shot_y', 'shot_result', 'result', 'turnover_type', 'offensive_rebound',
  'possession_result', 'intended_outcome']
const BB_DEF = ['defensive_set', 'pressure_applied', 'help_defense', 'opp_ball_handler', 'opp_shooter',
  'opp_primary_action', 'shot_zone_allowed', 'shot_x', 'shot_y', 'result', 'defensive_rebound']
const QUICK = ['play_type', 'result', 'yards_gained']

export function fieldsForMode(mode: Mode, isBB: boolean, quick: boolean): string[] {
  if (quick) return [...QUICK, ...COMMON, ...(!isBB && mode !== 'st' ? SITUATIONAL : [])]
  if (isBB) return [...(mode === 'them' ? BB_DEF : BB_OFF), ...COMMON]
  if (mode === 'st') return [...FB_ST, ...COMMON]
  return [...SITUATIONAL, ...(mode === 'them' ? FB_DEF : FB_OFF), ...COMMON]
}

/** Keep only the entry fields that belong to this play type. A special-teams play can
 *  never carry the previous defensive play's opp_formation / opp_play_type. */
export function stripForMode(cur: AnyPlay, mode: Mode, isBB: boolean, quick: boolean): AnyPlay {
  const keep = new Set(fieldsForMode(mode, isBB, quick))
  const out: AnyPlay = {}
  for (const [k, v] of Object.entries(cur || {})) {
    if (keep.has(k) && !isBlank(v)) out[k] = v
  }
  return out
}

/** After a play is logged or the play type changes: keep down / distance / ball-on, drop
 *  every per-play tag so nothing leaks into the next play. */
export function clearAfterLog(cur: AnyPlay): AnyPlay {
  return { down: cur?.down ?? '1', distance: cur?.distance ?? '10', field_position: cur?.field_position ?? '' }
}

// ── score sync ───────────────────────────────────────────────────────────────
const BB_POSS_POINTS: Record<string, number> = { '2 pts': 2, '3 pts': 3, '1 pt FT': 1, '2 pt FT': 2 }
const BB_ALLOWED_POINTS: Record<string, number> = { 'Gave Up 2': 2, 'Gave Up 3': 3 }

/** Points the selected outcome clearly implies, or null when it is not a score or the
 *  amount is ambiguous (then the coach picks it in the score row). */
export function autoPoints(sport: string, mode: Mode, cur: AnyPlay, quick = false): Points | null {
  const isBB = sport === 'basketball'
  const result = String(cur?.result || '')
  if (quick) {
    if (result !== 'Score') return null
    const n = Number(cur?.yards_gained)
    // Basketball quick log labels this field "Points".
    if (isBB && [1, 2, 3].includes(n)) return { team: mode === 'them' ? 'them' : 'us', points: n }
    return null
  }
  if (isBB) {
    if (mode === 'them') {
      const n = BB_ALLOWED_POINTS[result]
      return n ? { team: 'them', points: n } : null
    }
    const n = BB_POSS_POINTS[String(cur?.possession_result || '')]
    return n ? { team: 'us', points: n } : null
  }
  if (mode === 'us') return /^touchdown$/i.test(result) ? { team: 'us', points: 6 } : null
  if (mode === 'them') {
    return (/touchdown allowed/i.test(result) || /touchdown allowed/i.test(String(cur?.opp_outcome || '')))
      ? { team: 'them', points: 6 } : null
  }
  // special teams: the kicking team isn't otherwise recorded, so default to us and let
  // the coach flip it in the score row.
  const team: Team = cur?.points_team === 'them' ? 'them' : 'us'
  if (cur?.st_result === 'Made' && cur?.st_unit === 'Field Goal Attempt') return { team, points: 3 }
  if (cur?.st_result === 'Made' && cur?.st_unit === 'Extra Point') return { team, points: 1 }
  return null
}

/** True when the selected outcome is a score whose points we can't infer. */
export function isScoringOutcome(sport: string, mode: Mode, cur: AnyPlay, quick = false): boolean {
  const result = String(cur?.result || '')
  if (quick) return result === 'Score'
  if (sport === 'basketball') {
    if (mode === 'them') return /gave up|and-1 allowed|ft allowed/i.test(result)
    return /^(made|and-1)$/i.test(String(cur?.shot_result || '')) || !!BB_POSS_POINTS[String(cur?.possession_result || '')]
  }
  if (mode === 'st') return cur?.st_result === 'Made' || cur?.st_unit === 'Safety'
  return /touchdown/i.test(result) || /touchdown/i.test(String(cur?.opp_outcome || ''))
}

/** The points this play puts on the board: an explicit pick in the score row wins
 *  (0 = explicitly no score), otherwise what the outcome implies. */
export function resolvePoints(sport: string, mode: Mode, cur: AnyPlay, quick = false): Points | null {
  if (typeof cur?.points_scored === 'number') {
    if (cur.points_scored <= 0) return null
    const team: Team = cur.points_team === 'them' ? 'them'
      : cur.points_team === 'us' ? 'us' : (mode === 'them' ? 'them' : 'us')
    return { team, points: cur.points_scored }
  }
  return autoPoints(sport, mode, cur, quick)
}

/** A scoring outcome is selected but the amount is unknown: ask before logging. */
export function needsScoreEntry(sport: string, mode: Mode, cur: AnyPlay, quick = false): boolean {
  if (typeof cur?.points_scored === 'number') return false
  return isScoringOutcome(sport, mode, cur, quick) && !autoPoints(sport, mode, cur, quick)
}

export function applyPoints(scoreUs: number, scoreThem: number, pts: Points | null, sign: 1 | -1 = 1) {
  const us = Math.max(0, (Number(scoreUs) || 0) + (pts && pts.team === 'us' ? sign * pts.points : 0))
  const them = Math.max(0, (Number(scoreThem) || 0) + (pts && pts.team === 'them' ? sign * pts.points : 0))
  return { us, them }
}

/** Restore the score boxes after a reload from the last play that recorded a score. */
export function lastScore(plays: AnyPlay[]): { us: number; them: number } {
  for (let i = plays.length - 1; i >= 0; i--) {
    const p = plays[i]
    if (!isBlank(p?.score_us) || !isBlank(p?.score_them)) {
      return { us: Number(p.score_us) || 0, them: Number(p.score_them) || 0 }
    }
  }
  return { us: 0, them: 0 }
}
