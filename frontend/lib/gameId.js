// Game ids are UUIDs. Anything else in /games/<id> can never load, so the page
// shows "not found" at once instead of calling the API with it.
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function isGameId(id) {
  return typeof id === 'string' && UUID_RE.test(id)
}

// How a failed GET /games/<id> should render: a missing or foreign game is
// "not_found" (the API answers 404 for both, so nothing leaks); anything else
// is a retryable "error".
export function gameLoadError(err) {
  const status = err && err.response && Number(err.response.status)
  return status === 404 || status === 400 || status === 422 ? 'not_found' : 'error'
}
