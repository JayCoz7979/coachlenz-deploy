// Live Game Play Logger, sport-specific field vocabularies.
// Central source of truth for the tappable option lists the logger renders, plus
// the run-gap terminology systems (Feature 1). Kept framework-free so both the
// setup screen and the logger read the same lists.

export type Sport = 'football' | 'flag_football' | 'basketball'

// ── run gap / hole terminology systems (football + flag football) ────────────
// Each gap has a stable normalized `value` (report-consistent regardless of the
// system the coach picked) and a per-system display `label`.
export type TermSystem = 'gap_letters' | 'hole_numbers' | 'zones'

export const TERM_SYSTEMS: { value: TermSystem; label: string }[] = [
  { value: 'gap_letters', label: 'Gap Letters (A/B/C/D)' },
  { value: 'hole_numbers', label: 'Hole Numbers (1–8)' },
  { value: 'zones', label: 'Simplified Zones' },
]

// Left-to-right across the line. `value` is the normalized internal key.
export type Gap = { value: string; letters: string; holes: string; zones: string }
export const GAPS: Gap[] = [
  { value: 'left_d', letters: 'D (L)', holes: '9', zones: 'Left End' },
  { value: 'left_c', letters: 'C (L)', holes: '7', zones: 'Left End' },
  { value: 'left_b', letters: 'B (L)', holes: '5', zones: 'Left Interior' },
  { value: 'left_a', letters: 'A (L)', holes: '3', zones: 'Left Interior' },
  { value: 'right_a', letters: 'A (R)', holes: '2', zones: 'Right Interior' },
  { value: 'right_b', letters: 'B (R)', holes: '4', zones: 'Right Interior' },
  { value: 'right_c', letters: 'C (R)', holes: '6', zones: 'Right End' },
  { value: 'right_d', letters: 'D (R)', holes: '8', zones: 'Right End' },
]

export function gapLabel(value: string, sys: TermSystem): string {
  const g = GAPS.find(x => x.value === value)
  if (!g) return value
  return sys === 'hole_numbers' ? g.holes : sys === 'zones' ? g.zones : g.letters
}

// Flag football rush lanes (no interior blocking, replaces the OL gap diagram).
export const RUSH_LANES = [
  { value: 'left_outside', label: 'Left Outside' },
  { value: 'left_inside', label: 'Left Inside' },
  { value: 'middle', label: 'Middle' },
  { value: 'right_inside', label: 'Right Inside' },
  { value: 'right_outside', label: 'Right Outside' },
]

// ── football / flag football option lists ────────────────────────────────────
export const FB_FORMATIONS = ['Shotgun', 'Under Center', 'Pistol', 'Wildcat', 'Custom']
export const FB_PLAY_TYPES = ['Run', 'Pass', 'RPO', 'QB Scramble', 'Kneel', 'Spike']
export const FB_RUN_CATEGORIES = ['Inside Run', 'Outside Run', 'Draw', 'Counter', 'Sweep', 'Option', 'QB Sneak']
export const FLAG_RUSH_TYPES = ['QB Rush', 'HB Rush', 'End Around', 'Option Pitch', 'Sweep']
export const FB_PASS_RESULTS = ['Completion', 'Incompletion', 'Interception', 'Sack', 'Scramble', 'Penalty']
export const FB_OUTCOMES = ['First Down', 'Continues Drive', 'Turnover on Downs', 'Touchdown', 'Turnover', 'Penalty']

export const DEF_FRONTS = ['3-4', '4-3', '4-2-5', '3-3-5', 'Nickel', 'Dime', 'Custom']
export const DEF_COVERAGES = ['Man', 'Zone', 'Cover 0', 'Cover 1', 'Cover 2', 'Cover 3', 'Cover 4', 'Tampa 2', 'Custom']
export const OPP_FORMATIONS = ['Shotgun', 'Under Center', 'Pistol', 'Spread', 'Power-I', 'Wishbone', 'Custom']
export const OPP_PLAY_TYPES = ['Run', 'Pass', 'RPO', 'QB Scramble']
export const DEF_RESULTS = [
  'Stop for Loss', 'Stop at Line', 'Gain of 1–3', 'Gain of 4–6', 'Gain of 7–9', 'Gain of 10+',
  'Touchdown Allowed', 'Interception', 'Forced Fumble', 'Sack', 'Penalty',
]
export const DEF_OUTCOMES = ['First Down Allowed', 'Forced Punt', 'Turnover', 'Touchdown Allowed', 'Penalty']

export const ST_UNITS = ['Kickoff', 'Kickoff Return', 'Punt', 'Punt Return', 'Field Goal Attempt', 'Extra Point', 'Onside Kick', 'Safety']
export const ST_RESULTS = ['Made', 'Missed', 'Blocked', 'Returned', 'Downed', 'Touchback', 'Fair Catch', 'Fumble', 'Penalty']

// Standard route tree (custom routes append at setup).
export const ROUTES = [
  'Hitch / Curl', 'Slant', 'Out', 'In (Dig)', 'Comeback', 'Post', 'Corner', 'Wheel',
  'Flat / Angle', 'Seam / Go', 'Screen', 'Crossing / Drag', 'Option Route',
]

// ── basketball option lists ──────────────────────────────────────────────────
export const BB_BALL_ENTRY = ['Post Entry', 'Wing Entry', 'Pick and Roll', 'Dribble Handoff', 'Transition', 'Isolation', 'BLOB', 'SLOB', 'ATO', 'Free Throw']
export const BB_PRIMARY_ACTION = ['Drive', 'Kick Out', 'Post Up', 'Spot Up', 'Off Screen', 'Pull Up', 'Lob', 'Transition Layup']
export const BB_SHOT_RESULT = ['Made', 'Missed', 'Blocked', 'And-1', 'Fouled No Shot', 'Turnover Before Shot']
export const BB_TURNOVER_TYPE = ['Travel', 'Charge', 'Bad Pass', 'Ball Handling', '5-Second', 'Shot Clock']
export const BB_POSS_RESULT = ['2 pts', '3 pts', '1 pt FT', '2 pt FT', 'Missed', 'Turnover', 'Foul Drawn']
export const BB_DEF_SET = ['Man', 'Zone 2-3', 'Zone 3-2', 'Zone 1-3-1', 'Press Full Court', 'Press Half Court', 'Matchup Zone', 'Custom']
export const BB_OPP_ACTION = ['Drive', 'Post Up', 'Pick and Roll', 'Spot Up', 'Off Screen', 'Transition', 'Isolation']
export const BB_DEF_RESULT = ['Stop - Missed', 'Stop - Turnover', 'Block', 'Steal', 'Gave Up 2', 'Gave Up 3', 'And-1 Allowed', 'Foul - No Shot', 'Fouled - FT Allowed']
export const BB_SPECIAL = ['BLOB', 'SLOB', 'ATO']
export const BB_INTENDED = ['Run Clock', 'Score', 'Foul', 'Advance']

// Half-court shot zones. `value` is stable; the court diagram positions each by id.
export const SHOT_ZONES = [
  { value: 'paint', label: 'Paint' },
  { value: 'mid_left', label: 'Mid-Range Left' },
  { value: 'mid_right', label: 'Mid-Range Right' },
  { value: 'mid_center', label: 'Mid-Range Center' },
  { value: 'corner3_left', label: 'Corner 3 Left' },
  { value: 'corner3_right', label: 'Corner 3 Right' },
  { value: 'wing3_left', label: 'Wing 3 Left' },
  { value: 'wing3_right', label: 'Wing 3 Right' },
  { value: 'top3', label: 'Top of Key 3' },
  { value: 'ft', label: 'Free Throw' },
]

export const GAME_TYPES = [
  { value: 'regular_season', label: 'Regular Season' },
  { value: 'playoff', label: 'Playoff' },
  { value: 'scrimmage', label: 'Scrimmage' },
]
export const WEATHER = ['Clear', 'Overcast', 'Rain', 'Wind', 'Cold']
export const SURFACES = ['Grass', 'Turf']
export const LEAGUE_FORMATS = ['5-on-5', '7-on-7', '8-on-8']
