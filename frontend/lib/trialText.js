// Days-left text for a trial org. The one source for every trial card: the
// sidebar's top pill and footer card, and the OS shell's plan card (dashboard
// and the other OS pages). Returns null when there is nothing true to show (not
// a trial, or no usable day count), and callers then hide the text.

export function trialDaysLeftText(org) {
  if (!org || !org.is_trial) return null
  const days = Number(org.trial_days_remaining)
  if (org.trial_days_remaining === null || org.trial_days_remaining === undefined || !Number.isFinite(days) || days < 0) return null
  const n = Math.floor(days)
  return `${n} ${n === 1 ? 'day' : 'days'} left`
}

// Plan card title, the same on the sidebar card and the OS shell plan card:
// "Trial Plan", "Coach Plan", and so on. Unknown tiers read "CoachLenz Plan".
export const TIER_LABELS = {
  trial: 'Trial', coach: 'Coach', athletic_dept: 'Athletic Dept', district: 'District', enterprise: 'Enterprise',
}

export function planTitle(tier) {
  return `${TIER_LABELS[tier] || 'CoachLenz'} Plan`
}
