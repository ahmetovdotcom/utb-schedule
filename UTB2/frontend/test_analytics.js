import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
const source = (await readFile(new URL('./src/services/analytics.js', import.meta.url), 'utf8')).replace('import.meta.env', '{}')
const storage = new Map()
globalThis.localStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) }
Object.defineProperty(globalThis, 'navigator', { value: { userAgent: 'iPhone Safari', doNotTrack: '0' }, configurable: true })
globalThis.document = { referrer: 'https://example.org/private/path?secret=hidden' }
globalThis.location = { hostname: 'okak.asia' }
const events = []
globalThis.fetch = async (url, options) => { events.push(JSON.parse(options.body)); return {} }
const { track } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'))
const realNow = Date.now
let now = realNow()
Date.now = () => now
try {
  track('open', 'student')
  now += 60000
  track('schedule', 'student', 12)
  assert.equal(events[0].visitor, events[1].visitor)
  assert.equal(events[0].visit, events[1].visit)
  assert.equal(events[0].referrer, 'example.org')
  assert.equal(events[0].device, 'phone')
  now += 31 * 60000
  track('open', 'teacher')
  assert.equal(events[0].visitor, events[2].visitor)
  assert.notEqual(events[0].visit, events[2].visit)
  navigator.doNotTrack = '1'
  track('open', 'student')
  assert.equal(events.length, 3)
  navigator.doNotTrack = '0'
  navigator.globalPrivacyControl = true
  track('open', 'student')
  assert.equal(events.length, 3)
  navigator.globalPrivacyControl = false
  localStorage.getItem = () => { throw new Error('Storage denied') }
  assert.doesNotThrow(() => track('open', 'student'))
  console.log('OK: browser identity, visit expiry, referrer minimization, privacy signals, unavailable storage')
} finally { Date.now = realNow }
