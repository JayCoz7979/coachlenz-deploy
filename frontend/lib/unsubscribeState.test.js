import test from 'node:test'
import assert from 'node:assert/strict'
import { confirmUnsubscribe } from './unsubscribeState.js'

test('only a 2xx counts as unsubscribed', async () => {
  const calls = []
  const ok = async (path, body) => { calls.push([path, body]); return { status: 200 } }
  assert.equal(await confirmUnsubscribe(ok, 'tok'), 'done')
  assert.deepEqual(calls, [['/auth/unsubscribe', { token: 'tok' }]])
  assert.equal(await confirmUnsubscribe(async () => ({ status: 204 }), 'tok'), 'done')
})

test('a rejected request, a non-2xx, or no response is an error', async () => {
  const rejects = async () => { const e = new Error('400'); e.response = { status: 400 }; throw e }
  assert.equal(await confirmUnsubscribe(rejects, 'bad'), 'error')
  assert.equal(await confirmUnsubscribe(async () => { throw new Error('network') }, 'tok'), 'error')
  assert.equal(await confirmUnsubscribe(async () => ({ status: 500 }), 'tok'), 'error')
  assert.equal(await confirmUnsubscribe(async () => ({ status: 302 }), 'tok'), 'error')
  assert.equal(await confirmUnsubscribe(async () => undefined, 'tok'), 'error')
})
