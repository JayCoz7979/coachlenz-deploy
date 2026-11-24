import test from 'node:test'
import assert from 'node:assert/strict'
import { shouldTryDirect, transportAfterDirectAttempt } from './chunkTransport.js'

test('the first chunk tries storage directly', () => {
  assert.equal(shouldTryDirect(null), true)
})

test('a CORS or network failure on the storage PUT switches that chunk to the relay', () => {
  assert.equal(transportAfterDirectAttempt(false), 'relay')
  assert.equal(shouldTryDirect(false), false)
})

test('a successful storage PUT keeps later chunks on the direct path', () => {
  assert.equal(transportAfterDirectAttempt(true), 'direct')
  assert.equal(shouldTryDirect(true), true)
})
