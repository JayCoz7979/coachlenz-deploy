import test from 'node:test'
import assert from 'node:assert/strict'
import { trialDaysLeftText } from './trialText.js'

test('a trial with a day count shows one wording everywhere', () => {
  assert.equal(trialDaysLeftText({ is_trial: true, trial_days_remaining: 13 }), '13 days left')
  assert.equal(trialDaysLeftText({ is_trial: true, trial_days_remaining: 1 }), '1 day left')
  assert.equal(trialDaysLeftText({ is_trial: true, trial_days_remaining: 0 }), '0 days left')
  assert.equal(trialDaysLeftText({ is_trial: true, trial_days_remaining: 2.7 }), '2 days left')
})

test('no trial or no usable count shows nothing', () => {
  assert.equal(trialDaysLeftText(null), null)
  assert.equal(trialDaysLeftText({ is_trial: false, trial_days_remaining: 5 }), null)
  assert.equal(trialDaysLeftText({ is_trial: true }), null)
  assert.equal(trialDaysLeftText({ is_trial: true, trial_days_remaining: null }), null)
  assert.equal(trialDaysLeftText({ is_trial: true, trial_days_remaining: 'x' }), null)
  assert.equal(trialDaysLeftText({ is_trial: true, trial_days_remaining: -1 }), null)
})

test('the sidebar and the OS shell both render the helper, not their own wording', async () => {
  const { readFile } = await import('node:fs/promises')
  for (const file of ['../components/layout/Sidebar.tsx', '../components/os/OSShell.tsx']) {
    const src = await readFile(new URL(file, import.meta.url), 'utf8')
    assert.match(src, /trialDaysLeftText\(/, file)
    assert.doesNotMatch(src, /days left`|d left`/, file)
  }
})
