import test from 'node:test'
import assert from 'node:assert/strict'
import { isBusyConflict, busyWaitMs, withBusyRetry, MAX_BUSY_RETRIES } from './uploadRetry.js'

const busy = (extra = {}) => ({ response: { status: 409, data: { detail: 'busy', code: 'upload_busy', retry_after_seconds: 5 }, headers: {}, ...extra } })
const incomplete = { response: { status: 409, data: { detail: 'The upload stopped before every chunk arrived.', code: 'upload_incomplete' }, headers: {} } }
const legacy409 = { response: { status: 409, data: { detail: 'This upload is still finishing in another tab or request.' }, headers: {} } }

test('only the busy 409 is retryable', () => {
  assert.equal(isBusyConflict(busy()), true)
  assert.equal(isBusyConflict(incomplete), false)
  assert.equal(isBusyConflict(legacy409), false)
  assert.equal(isBusyConflict({ response: { status: 500, data: { code: 'upload_busy' } } }), false)
  assert.equal(isBusyConflict(new Error('network')), false)
})

test('the header code alone also marks busy', () => {
  assert.equal(isBusyConflict({ response: { status: 409, data: {}, headers: { 'x-upload-error': 'upload_busy' } } }), true)
})

test('wait follows Retry-After, with a default and a 30 s cap', () => {
  assert.equal(busyWaitMs(busy()), 5000)
  assert.equal(busyWaitMs({ response: { status: 409, data: {}, headers: { 'retry-after': '12' } } }), 12000)
  assert.equal(busyWaitMs({ response: { status: 409, data: { retry_after_seconds: 999 } } }), 30000)
  assert.equal(busyWaitMs({ response: { status: 409, data: {} } }), 5000)
})

test('busy is retried, then succeeds', async () => {
  let calls = 0
  const waits = []
  const out = await withBusyRetry(async () => { calls += 1; if (calls < 3) throw busy(); return 'ok' }, { sleep: async (ms) => { waits.push(ms) } })
  assert.equal(out, 'ok')
  assert.equal(calls, 3)
  assert.deepEqual(waits, [5000, 5000])
})

test('busy retries are bounded', async () => {
  let calls = 0
  await assert.rejects(withBusyRetry(async () => { calls += 1; throw busy() }, { sleep: async () => {} }))
  assert.equal(calls, MAX_BUSY_RETRIES + 1)
})

test('incomplete and other errors are not retried', async () => {
  for (const err of [incomplete, legacy409, new Error('boom')]) {
    let calls = 0
    await assert.rejects(withBusyRetry(async () => { calls += 1; throw err }, { sleep: async () => {} }))
    assert.equal(calls, 1)
  }
})
