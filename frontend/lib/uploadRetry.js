// Retry policy for POST /upload/multipart/complete.
//
// Only the "busy" 409 is retried: another tab or request holds this upload's
// lock and the same call will succeed once it finishes. The "incomplete" 409
// (a chunk is missing) and every other error go straight back to the coach.
// Older backends send no code; their 409s are never retried.

export const BUSY_CODE = 'upload_busy'
export const MAX_BUSY_RETRIES = 3
const DEFAULT_WAIT_SECONDS = 5
const MAX_WAIT_SECONDS = 30

function headerValue(headers, name) {
  if (!headers) return undefined
  if (typeof headers.get === 'function') return headers.get(name) ?? undefined
  return headers[name] ?? headers[name.toLowerCase()]
}

export function isBusyConflict(err) {
  const res = err && err.response
  if (!res || res.status !== 409) return false
  const code = (res.data && res.data.code) || headerValue(res.headers, 'x-upload-error')
  return code === BUSY_CODE
}

export function busyWaitMs(err) {
  const res = (err && err.response) || {}
  const raw = (res.data && res.data.retry_after_seconds) ?? headerValue(res.headers, 'retry-after')
  const seconds = Number(raw)
  const safe = Number.isFinite(seconds) && seconds > 0 ? seconds : DEFAULT_WAIT_SECONDS
  return Math.min(safe, MAX_WAIT_SECONDS) * 1000
}

// Calls fn, retrying only a busy 409, at most MAX_BUSY_RETRIES times.
export async function withBusyRetry(fn, { sleep, onWait } = {}) {
  const pause = sleep || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)))
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await fn()
    } catch (err) {
      if (!isBusyConflict(err) || attempt >= MAX_BUSY_RETRIES) throw err
      const ms = busyWaitMs(err)
      if (onWait) onWait(ms, attempt + 1)
      await pause(ms)
    }
  }
}
