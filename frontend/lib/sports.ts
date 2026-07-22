// Single source of truth for the sports the coach-facing portal offers.
// Mirrors the backend CHOOSABLE_SPORTS (backend/services/sports.py). To add a
// sport later, ship its analysis engine and add it here once - it then surfaces
// everywhere (onboarding, team creation, film upload, the sport tabs).
export const SPORTS = ['football', 'flag_football', 'basketball'] as const
export type Sport = (typeof SPORTS)[number]

export const SPORT_META: Record<string, { label: string; emoji: string }> = {
  football: { label: 'Football', emoji: '🏈' },
  flag_football: { label: 'Flag Football', emoji: '🚩' },
  basketball: { label: 'Basketball', emoji: '🏀' },
}
