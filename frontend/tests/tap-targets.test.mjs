// Static guard: no live-logger / Live Tracker control may declare a minHeight below
// 44px (the Nov 24 phone pass found 32-42px score, clock, filter, and toggle
// controls). Large non-control values (textareas, 100vh) are fine.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const DIRS = ['app/live', 'app/live-tracker', 'components/live']

function files(dir) {
  const out = []
  for (const name of readdirSync(join(root, dir))) {
    const rel = join(dir, name)
    if (statSync(join(root, rel)).isDirectory()) out.push(...files(rel))
    else if (/\.tsx$/.test(name)) out.push(rel)
  }
  return out
}

test('every numeric minHeight on logger and offer controls is at least 44px', () => {
  const offenders = []
  for (const f of DIRS.flatMap(files)) {
    const src = readFileSync(join(root, f), 'utf8')
    for (const m of src.matchAll(/minHeight:\s*(\d+)/g)) {
      if (Number(m[1]) < 44) offenders.push(`${f}: minHeight ${m[1]}`)
    }
  }
  assert.deepEqual(offenders, [])
})

test('the Situational Down chips get their own full-width row', () => {
  const src = readFileSync(join(root, 'app/live/[id]/page.tsx'), 'utf8')
  assert.doesNotMatch(src, /gridTemplateColumns: 'repeat\(3, 1fr\)'[^\n]*\n\s*<Field label="Down">/)
})

test('the logger renders the Halftime Sheet from REPORT_ACTIONS', () => {
  const src = readFileSync(join(root, 'app/live/[id]/page.tsx'), 'utf8')
  assert.match(src, /REPORT_ACTIONS\.map/)
  assert.match(src, /report\(a\.scope\)/)
})

test('offer page copy stays inside the fact lock', () => {
  // Check the rendered copy, not code comments.
  const src = readFileSync(join(root, 'app/live-tracker/page.tsx'), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '').replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
  assert.match(src, /\$7/)
  assert.match(src, /one time/i)
  for (const sport of ['Football', 'Flag Football', 'Basketball']) assert.match(src, new RegExp(sport))
  for (const banned of [/free forever/i, /no card, ever/i, /\$0 forever/i, /\bSMS\b/i, /text message/i, /testimonial/i, /offline/i]) {
    assert.doesNotMatch(src, banned)
  }
  // Only one dollar amount on the page.
  const amounts = new Set([...src.matchAll(/\$(\d+)/g)].map(m => m[1]))
  assert.deepEqual([...amounts], ['7'])
})
