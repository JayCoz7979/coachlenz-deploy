import test from 'node:test'
import assert from 'node:assert/strict'
import { trialDaysLeftText } from './trialText.js'

test('a trial with a day count shows the same short text', () => {
  assert.equal(trialDaysLeftText({ is_trial: true, trial_days_remaining: 13 }), '13d left')
  assert.equal(trialDaysLeftText({ is_trial: true, trial_days_remaining: 0 }), '0d left')
})

test('no trial or no usable count shows nothing', () => {
  assert.equal(trialDaysLeftText(null), null)
  assert.equal(trialDaysLeftText({ is_trial: false, trial_days_remaining: 5 }), null)
  assert.equal(trialDaysLeftText({ is_trial: true }), null)
  assert.equal(trialDaysLeftText({ is_trial: true, trial_days_remaining: null }), null)
  assert.equal(trialDaysLeftText({ is_trial: true, trial_days_remaining: 'x' }), null)
  assert.equal(trialDaysLeftText({ is_trial: true, trial_days_remaining: -1 }), null)
})
