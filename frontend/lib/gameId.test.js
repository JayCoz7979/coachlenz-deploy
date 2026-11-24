import test from 'node:test'
import assert from 'node:assert/strict'
import { isGameId, gameLoadError } from './gameId.js'

test('only a UUID is a game id', () => {
  assert.equal(isGameId('df42236a-9453-405d-a3a8-81d0d8ca74a8'), true)
  assert.equal(isGameId('DF42236A-9453-405D-A3A8-81D0D8CA74A8'), true)
  for (const bad of ['', 'df42236a', 'abc', 'df42236a-9453-405d-a3a8-81d0d8ca74a8x', '../x', undefined, null, 5]) {
    assert.equal(isGameId(bad), false, String(bad))
  }
})

test('404, 400 and 422 render not found; other failures are retryable', () => {
  assert.equal(gameLoadError({ response: { status: 404 } }), 'not_found')
  assert.equal(gameLoadError({ response: { status: 422 } }), 'not_found')
  assert.equal(gameLoadError({ response: { status: 400 } }), 'not_found')
  assert.equal(gameLoadError({ response: { status: 500 } }), 'error')
  assert.equal(gameLoadError(new Error('network')), 'error')
})
