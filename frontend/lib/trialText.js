// Days-left text for a trial org, shared by the sidebar's top pill and its
// footer card so they always agree. Returns null when there is nothing true to
// show (not a trial, or no usable day count), and callers then hide the text.

export function trialDaysLeftText(org) {
  if (!org || !org.is_trial) return null
  const days = Number(org.trial_days_remaining)
  if (org.trial_days_remaining === null || org.trial_days_remaining === undefined || !Number.isFinite(days) || days < 0) return null
  return `${Math.floor(days)}d left`
}
