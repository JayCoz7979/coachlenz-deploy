import { test } from 'node:test'
import assert from 'node:assert/strict'
import { safeNext } from '../lib/nextPath.ts'

test('allows same-site paths, including the Live Tracker checkout return', () => {
  assert.equal(safeNext('/live-tracker?buy=1'), '/live-tracker?buy=1')
  assert.equal(safeNext(encodeURIComponent('/live-tracker?buy=1')), '/live-tracker?buy=1')
  assert.equal(safeNext('/live'), '/live')
})

test('refuses anything that could leave the site', () => {
  for (const bad of ['//evil.example', 'https://evil.example', 'javascript:alert(1)', '/\\evil.example', 'live', '', null, undefined, '%2F%2Fevil.example', '/x\n/y']) {
    assert.equal(safeNext(bad), null, String(bad))
  }
})
