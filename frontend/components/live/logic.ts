// Live Game Logger, pure logic (no React, no imports) so it can be unit-tested with
// `node --test` and shared by the logger page. Covers the Nov 24 sideline bugs:
//   - Play Log after reload ("play · null yd"): normalizeServerPlay + playSummary
//   - Special Teams inheriting the previous play's fields: cleanForMode
//   - Score taps not updating the score the report reads: scoreForPlay
//   - Halftime Sheet as a first-class action: REPORT_ACTIONS

export type Mode = 'us' | 'them' | 'st'
export type AnyPlay = Record<string, any>

/** Smallest tap target (CSS px) for primary sideline controls. */
export const MIN_TAP = 44

// ── reload: flatten server extra_data so the Play Log can read it ────────────
/**
 * The API returns first-class Event columns at the top level and everything else
 * (opp_play_type, st_unit, shot_zone, score_us, ...) under `extra`. Locally logged
 * plays carry those keys at the top level. Merge `extra` up so a reloaded play and a
 * freshly logged one look the same. A real top-level value always wins; a null or
 * missing one is filled from `extra`.
 */
export function normalizeServerPlay(p: AnyPlay): AnyPlay {
  const extra = (p && typeof p.extra === 'object' && p.extra) || {}
  const out: AnyPlay = { ...p }
  for (const k of Object.keys(extra)) {
    if (out[k] === null || out[k] === undefined || out[k] === '') out[k] = extra[k]
  }
  return out
}

const present = (v: unknown) => v !== null && v !== undefined && v !== '' && !(typeof v === 'number' && Number.isNaN(v))

function sideOf(p: AnyPlay): 'offense' | 'defense' | 'special_teams' {
  if (p.side === 'special_teams' || p.side === 'defense' || p.side === 'offense') return p.side
  return p.possession === 'them' ? 'defense' : 'offense'
}

/** One-line summary for the Play Log. Never prints "null" or "undefined". */
export function playSummary(p: AnyPlay, isBB: boolean): string {
  const parts: string[] = []
  const side = sideOf(p)
  if (!isBB) {
    if (side !== 'special_teams' && present(p.down)) parts.push(`${p.down}&${present(p.distance) ? p.distance : ''}`)
    const kind = side === 'special_teams'
      ? (p.st_unit || p.play_type)
      : side === 'defense'
        ? (p.opp_play_type || p.play_type)
        : (p.play_type || p.opp_play_type)
    parts.push(present(kind) ? String(kind) : 'play')
    const route = side === 'defense' ? p.opp_route : p.route
    if (present(route)) parts.push(String(route))
    const concept = side === 'defense' ? p.opp_run_concept : p.run_category
    if (side !== 'special_teams' && present(concept)) parts.push(String(concept))
    const yards = side === 'special_teams' ? (present(p.st_yards) ? p.st_yards : p.yards_gained) : p.yards_gained
    if (present(yards)) parts.push(`${yards} yd`)
  } else {
    const action = side === 'defense'
      ? (p.opp_primary_action || p.play_type)
      : (p.ball_entry || p.primary_action || p.play_type)
    parts.push(present(action) ? String(action) : 'poss')
    const zone = side === 'defense' ? p.shot_zone_allowed : p.shot_zone
    if (present(zone)) parts.push(String(zone))
    const res = p.possession_result || p.shot_result
    if (present(res)) parts.push(String(res))
  }
  const jersey = p.player || (side === 'special_teams'
    ? (p.returner_jersey || p.kicker_jersey)
    : side === 'defense'
      ? (p.stop_maker_jersey || p.opp_ball_carrier || p.opp_target || p.opp_shooter)
      : (p.ball_carrier_jersey || p.shooter_jersey || p.target_jersey))
  if (present(jersey)) parts.push(`#${jersey}`)
  if (present(p.result) && !parts.includes(String(p.result))) parts.push(String(p.result))
  return parts.filter(Boolean).join(' · ')
}

// ── unit isolation: only the active panel's fields ride on a play ───────────
const SITUATIONAL = ['down', 'distance', 'field_position']
const FB_US = ['formation', 'play_type', 'run_gap', 'rush_lane', 'ball_carrier_jersey', 'run_category',
  'passer_jersey', 'target_jersey', 'route', 'target_area', 'pass_result', 'yards_gained', 'result']
const FB_THEM = ['defensive_front', 'blitz', 'coverage', 'opp_formation', 'opp_play_type', 'opp_run_gap',
  'opp_ball_carrier', 'opp_run_concept', 'opp_passer_jersey', 'opp_target', 'opp_route',
  'stop_maker_jersey', 'result', 'yards_gained', 'opp_outcome']
const FB_ST = ['st_unit', 'kicker_jersey', 'returner_jersey', 'st_result', 'st_yards', 'result']
const BB_US = ['ball_handler_jersey', 'shooter_jersey', 'ball_entry', 'primary_action', 'shot_zone', 'shot_x',
  'shot_y', 'shot_result', 'result', 'turnover_type', 'offensive_rebound', 'possession_result', 'intended_outcome']
const BB_THEM = ['defensive_set', 'pressure_applied', 'help_defense', 'opp_ball_handler', 'opp_shooter',
  'opp_primary_action', 'shot_zone_allowed', 'shot_x', 'shot_y', 'result', 'defensive_rebound']
const QUICK = ['play_type', 'result', 'yards_gained']

/** The entry fields the panel for this unit actually shows. */
export function fieldsForMode(mode: Mode, isBB: boolean, quick: boolean): string[] {
  if (quick) return isBB || mode === 'st' ? QUICK : [...SITUATIONAL, ...QUICK]
  if (isBB) return mode === 'them' ? BB_THEM : BB_US
  if (mode === 'st') return FB_ST
  return [...SITUATIONAL, ...(mode === 'them' ? FB_THEM : FB_US)]
}

/** Keep only this unit's fields (drops e.g. a previous defensive play's opp_* on a
 *  Special Teams play, which used to show as "Run · Returned"). */
export function cleanForMode(cur: AnyPlay, mode: Mode, isBB: boolean, quick: boolean): AnyPlay {
  const keep = new Set(fieldsForMode(mode, isBB, quick))
  const out: AnyPlay = {}
  for (const k of Object.keys(cur || {})) if (keep.has(k) && present(cur[k])) out[k] = cur[k]
  return out
}

/** The entry state to start from after a unit switch: situational context only. */
export function resetForMode(cur: AnyPlay, mode: Mode, isBB: boolean): AnyPlay {
  if (isBB || mode === 'st') return {}
  const out: AnyPlay = {}
  for (const k of SITUATIONAL) if (present(cur?.[k])) out[k] = cur[k]
  if (!present(out.down)) out.down = '1'
  if (!present(out.distance)) out.distance = '10'
  return out
}

// ── score: keep the score boxes (what the report reads) in sync ──────────────
export type ScoreCall =
  | { team: 'us' | 'them'; points: number; needsEntry: false }
  | { team: 'us' | 'them'; points: 0; needsEntry: true }
  | null

const BB_US_POINTS: Record<string, number> = { '2 pts': 2, '3 pts': 3, '1 pt FT': 1, '2 pt FT': 2 }
const BB_THEM_POINTS: Record<string, number> = { 'Gave Up 2': 2, 'Gave Up 3': 3 }

/**
 * Points a logged play puts on the board, when the entry says so unambiguously.
 * Ambiguous scoring plays (a quick-log "Score" in football, an and-one, a made shot
 * with no possession result) return needsEntry so the UI asks for the points instead
 * of guessing. Non-scoring plays return null.
 */
export function scoreForPlay(p: AnyPlay, mode: Mode, isBB: boolean, quick: boolean): ScoreCall {
  const team: 'us' | 'them' = mode === 'them' ? 'them' : 'us'
  const result = String(p.result || '')
  if (quick) {
    if (result !== 'Score') return null
    if (isBB) {
      const pts = Number(p.yards_gained)
      if (Number.isInteger(pts) && pts >= 1 && pts <= 4) return { team, points: pts, needsEntry: false }
    }
    return { team, points: 0, needsEntry: true }
  }
  if (isBB) {
    if (mode === 'them') {
      if (BB_THEM_POINTS[result]) return { team, points: BB_THEM_POINTS[result], needsEntry: false }
      if (result === 'And-1 Allowed' || result === 'Fouled - FT Allowed') return { team, points: 0, needsEntry: true }
      return null
    }
    const pr = String(p.possession_result || '')
    if (BB_US_POINTS[pr]) return { team, points: BB_US_POINTS[pr], needsEntry: false }
    if (/^(Made|And-1)$/.test(String(p.shot_result || ''))) return { team, points: 0, needsEntry: true }
    return null
  }
  if (mode === 'st') {
    // ST units are OUR units (Kickoff Return / Punt Return are the receiving ones),
    // so a made Field Goal Attempt / Extra Point is our kick. Anything else on ST is
    // entered by hand with the point chips.
    const made = String(p.st_result || '') === 'Made'
    if (made && p.st_unit === 'Field Goal Attempt') return { team: 'us', points: 3, needsEntry: false }
    if (made && p.st_unit === 'Extra Point') return { team: 'us', points: 1, needsEntry: false }
    return null
  }
  if (mode === 'them') {
    if (result === 'Touchdown Allowed' || p.opp_outcome === 'Touchdown Allowed') return { team, points: 6, needsEntry: false }
    return null
  }
  if (result === 'Touchdown') return { team, points: 6, needsEntry: false }
  return null
}

/** Quick-add point chips for the "add the points" prompt. */
export function pointChips(isBB: boolean): number[] {
  return isBB ? [1, 2, 3] : [1, 2, 3, 6]
}

/** The score to show after a reload: the highest score any logged play carried. */
export function scoreFromPlays(plays: AnyPlay[]): { us: number; them: number } {
  let us = 0, them = 0
  for (const p of plays || []) {
    const u = Number(p.score_us ?? p.extra?.score_us), t = Number(p.score_them ?? p.extra?.score_them)
    if (Number.isFinite(u)) us = Math.max(us, u)
    if (Number.isFinite(t)) them = Math.max(them, t)
  }
  return { us, them }
}

// ── reports: the Halftime Sheet is the first-class action ───────────────────
export type ReportAction = { scope: 'halftime' | 'full'; label: string; hint: (isBB: boolean) => string; primary: boolean }
export const REPORT_ACTIONS: ReportAction[] = [
  { scope: 'halftime', label: 'Halftime Sheet', primary: true,
    hint: isBB => (isBB ? 'First-half plays only.' : 'First-half plays only (Q1 and Q2).') },
  { scope: 'full', label: 'Full-Game Breakdown', primary: false, hint: () => 'Everything logged so far.' },
]
