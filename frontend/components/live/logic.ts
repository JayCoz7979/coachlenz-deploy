// Pure Live Game Logger logic, kept free of React and imports so it can be unit tested
// with `node --test` (see frontend/tests/live-logic.test.ts).
//
// What lives here, and why:
//  - resetEntry / stripForeign: one `cur` object backs every entry mode. Switching
//    Our Ball -> Special Teams used to keep the previous play's opp_formation /
//    opp_play_type, so a punt showed as "Run · Returned". Every mode switch, play-type
//    switch, Quick Log toggle and logged play now starts from a clean entry, and the
//    play that is logged only carries fields that belong to its unit.
//  - scoreDelta: tapping Touchdown / Made / 2 pts etc. now moves the score boxes the
//    report's Score & Momentum section reads (it used to stay 0-0).
//  - playSummary: the Play Log line, which reads opponent fields too, so an opponent
//    play no longer shows "play · null yd" after a reload.

export type LoggerMode = 'us' | 'them' | 'st'
export type Entry = Record<string, any>

// The minimum touch target for primary sideline controls (Apple HIG / WCAG 2.5.5).
export const TAP_MIN = 44

// Situational fields that carry across plays and mode switches (football down &
// distance and the ball spot). Everything else is per-play and is cleared.
const SITUATIONAL = ['down', 'distance', 'field_position'] as const

// Mirrors backend/routers/live_game.py _OUR_OFFENSE_KEYS / _ST_KEYS (the server
// enforces the same rule as a backstop).
const OUR_OFFENSE_KEYS = new Set([
  'passer_jersey', 'ball_carrier_jersey', 'target_jersey', 'run_category', 'run_gap',
  'run_gap_label', 'route', 'target_area', 'rush_lane', 'rush_type', 'pass_result',
  'custom_route', 'formation', 'play_type',
  'ball_handler_jersey', 'ball_entry', 'primary_action', 'shooter_jersey', 'shot_zone',
  'shot_result', 'turnover_type', 'turnover_jersey', 'offensive_rebound', 'second_chance',
  'foul_drawn_jersey', 'possession_result', 'intended_outcome',
])
const DEFENSE_KEYS = new Set([
  'defensive_front', 'blitz', 'coverage', 'stop_maker_jersey', 'pass_rush',
  'defensive_set', 'pressure_applied', 'help_defense', 'shot_zone_allowed',
  'fouled_by_jersey', 'defensive_rebound',
])
const ST_KEYS = new Set(['st_unit', 'kicker_jersey', 'returner_jersey', 'st_result', 'st_yards'])

// Run-only and pass-only fields, cleared when the play type flips between them.
const RUN_KEYS = ['run_gap', 'run_gap_label', 'rush_lane', 'rush_type', 'ball_carrier_jersey', 'run_category',
  'opp_run_gap', 'opp_ball_carrier', 'opp_run_concept']
const PASS_KEYS = ['passer_jersey', 'target_jersey', 'route', 'custom_route', 'target_area', 'pass_result',
  'opp_passer_jersey', 'opp_target', 'opp_route']

/** A fresh entry for the next play: keeps only down / distance / ball spot. */
export function resetEntry(cur: Entry, keepSituational = true): Entry {
  const next: Entry = {}
  if (keepSituational) for (const k of SITUATIONAL) if (cur[k] !== undefined) next[k] = cur[k]
  if (next.down === undefined) next.down = '1'
  if (next.distance === undefined) next.distance = '10'
  if (next.field_position === undefined) next.field_position = ''
  return next
}

/** True when `key` belongs to a different unit than `mode` (would leak). */
export function isForeignKey(mode: LoggerMode, key: string, quick = false): boolean {
  if (quick) return false
  const isOpp = key.startsWith('opp_')
  if (mode === 'us') return isOpp || ST_KEYS.has(key) || DEFENSE_KEYS.has(key)
  if (mode === 'them') return ST_KEYS.has(key) || OUR_OFFENSE_KEYS.has(key)
  return isOpp || OUR_OFFENSE_KEYS.has(key) || DEFENSE_KEYS.has(key)
}

/** The entry with every field that belongs to another unit removed. */
export function stripForeign(mode: LoggerMode, cur: Entry, quick = false): Entry {
  const out: Entry = {}
  for (const [k, v] of Object.entries(cur)) if (!isForeignKey(mode, k, quick)) out[k] = v
  return out
}

const isRunType = (t: unknown) => /run|sneak|scramble/i.test(String(t || ''))
const isPassType = (t: unknown) => /pass|rpo/i.test(String(t || ''))

/** Set the (opp_)play_type and clear the other play type's detail fields. */
export function switchPlayType(cur: Entry, key: 'play_type' | 'opp_play_type', value: string): Entry {
  const next: Entry = { ...cur, [key]: value }
  if (!isRunType(value)) for (const k of RUN_KEYS) delete next[k]
  if (!isPassType(value)) for (const k of PASS_KEYS) delete next[k]
  return next
}

export type ScoreDelta = { us: number; them: number }

/**
 * Points a logged play puts on the board, from the sport's own result vocabulary.
 * Returns {us, them}. Conservative: only unambiguous scoring results count. The coach
 * can always correct the score boxes by hand.
 */
export function scoreDelta(sport: string, mode: LoggerMode, play: Entry, quick = false): ScoreDelta {
  const zero = { us: 0, them: 0 }
  const isBB = sport === 'basketball'
  const forSide = (pts: number): ScoreDelta => (mode === 'them' ? { us: 0, them: pts } : { us: pts, them: 0 })
  if (quick) {
    if (!/^score$/i.test(String(play.result || ''))) return zero
    if (isBB) {
      const pts = Number(play.yards_gained)
      return forSide(Number.isFinite(pts) && pts > 0 && pts <= 4 ? pts : 2)
    }
    return forSide(6)
  }
  if (isBB) {
    if (mode === 'them') {
      const r = String(play.result || '')
      if (/gave up 3|and-1 allowed/i.test(r)) return { us: 0, them: 3 }
      if (/gave up 2/i.test(r)) return { us: 0, them: 2 }
      return zero
    }
    const pr = String(play.possession_result || '')
    const m = pr.match(/^(\d)\s*pts?\b/i)
    if (m) return { us: Number(m[1]), them: 0 }
    if (/^and-1$/i.test(String(play.shot_result || ''))) {
      return { us: /3/.test(String(play.shot_zone || '')) ? 4 : 3, them: 0 }
    }
    if (/^made$/i.test(String(play.shot_result || ''))) {
      const zone = String(play.shot_zone || '')
      if (zone === 'ft') return { us: 1, them: 0 }
      return { us: /3/.test(zone) ? 3 : 2, them: 0 }
    }
    return zero
  }
  // football / flag football
  if (mode === 'st') {
    if (!/^made$/i.test(String(play.st_result || ''))) return zero
    if (/field goal/i.test(String(play.st_unit || ''))) return { us: 3, them: 0 }
    if (/extra point/i.test(String(play.st_unit || ''))) return { us: 1, them: 0 }
    return zero
  }
  if (mode === 'them') {
    const txt = `${play.result || ''} ${play.opp_outcome || ''}`
    return /touchdown allowed/i.test(txt) ? { us: 0, them: 6 } : zero
  }
  return /^touchdown$/i.test(String(play.result || '')) ? { us: 6, them: 0 } : zero
}

/** Apply a delta to the score-box strings. Non-numeric boxes count as 0. */
export function applyScore(scoreUs: string, scoreThem: string, d: ScoreDelta): [string, string] {
  const n = (s: string) => (Number.isFinite(Number(s)) ? Number(s) : 0)
  return [String(n(scoreUs) + d.us), String(n(scoreThem) + d.them)]
}

const present = (v: unknown) => v !== undefined && v !== null && v !== ''

/** One-line Play Log summary. Never prints "null" or "undefined". */
export function playSummary(p: Entry, isBB: boolean): string {
  const parts: string[] = []
  // Tolerate rows that still carry the opponent detail only under `extra`.
  const x: Entry = { ...(p.extra || {}), ...Object.fromEntries(Object.entries(p).filter(([, v]) => present(v))) }
  if (!isBB) {
    if (present(x.down)) parts.push(`${x.down}&${present(x.distance) ? x.distance : ''}`)
    parts.push(String(x.st_unit || x.play_type || x.opp_play_type || 'play'))
    if (present(x.route) || present(x.opp_route)) parts.push(String(x.route || x.opp_route))
    if (present(x.run_category)) parts.push(String(x.run_category))
    const yd = x.st_unit ? (present(x.st_yards) ? x.st_yards : x.yards_gained) : x.yards_gained
    if (present(yd)) parts.push(`${yd} yd`)
  } else {
    parts.push(String(x.ball_entry || x.opp_primary_action || x.primary_action || 'poss'))
    if (present(x.shot_zone) || present(x.shot_zone_allowed)) parts.push(String(x.shot_zone || x.shot_zone_allowed))
    if (present(x.possession_result) || present(x.shot_result)) parts.push(String(x.possession_result || x.shot_result))
  }
  const jersey = x.player || x.ball_carrier_jersey || x.shooter_jersey || x.target_jersey || x.opp_ball_carrier || x.opp_shooter
  if (present(jersey)) parts.push(`#${jersey}`)
  const result = x.st_unit ? (x.st_result || x.result) : x.result
  if (present(result) && !parts.includes(String(result))) parts.push(String(result))
  return parts.filter(Boolean).join(' · ')
}

/** Score / period / possession to restore after a reload, from the last logged play. */
export function restoreFromPlays(plays: Entry[], isBB: boolean): { scoreUs: string; scoreThem: string; period: string | null; mode: LoggerMode | null } {
  const last = plays[plays.length - 1]
  if (!last) return { scoreUs: '0', scoreThem: '0', period: null, mode: null }
  const per = isBB ? last.half : last.quarter
  let period: string | null = null
  if (present(per)) {
    const n = Number(per)
    period = (isBB ? n >= 3 : n >= 5) ? 'OT' : String(n)
  }
  const side = last.side
  const mode: LoggerMode = side === 'special_teams' ? 'st' : (last.possession === 'them' || side === 'defense') ? 'them' : 'us'
  return {
    scoreUs: String(Number(last.score_us) || 0),
    scoreThem: String(Number(last.score_them) || 0),
    period,
    mode,
  }
}

// ── $7 Live Tracker paywall ──────────────────────────────────────────────────
// Every /live write route returns 403 with detail.code === this for an unpaid org
// (backend/services/live_tracker.py). Reads stay open, so past games stay viewable.
export const PAYWALL_CODE = 'live_tracker_payment_required'

export type PaywallInfo = { message: string; checkoutUrl: string }

/** The paywall body if this axios-style error is the Live Tracker 403, else null. */
export function paywallFromError(e: unknown): PaywallInfo | null {
  const resp = (e as { response?: { status?: number; data?: any } } | null)?.response
  const d = resp?.data?.detail
  if (resp?.status !== 403 || !d || typeof d !== 'object' || d.code !== PAYWALL_CODE) return null
  return {
    message: typeof d.message === 'string' ? d.message : 'The Live Tracker is a $7 one-time unlock.',
    checkoutUrl: typeof d.checkout_url === 'string' && d.checkout_url.startsWith('/') ? d.checkout_url : '/live-tracker',
  }
}
