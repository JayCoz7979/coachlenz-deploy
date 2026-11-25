// How one film chunk is sent.
//
// 'direct' is a browser PUT to the presigned storage URL (R2).
// 'relay' is the same chunk posted to the API, used when that PUT cannot
// leave the browser (bucket CORS missing, or the connection dropped).
// Once a direct PUT fails, later chunks stay on the relay so we do not pay
// for a failed preflight on every part.

export function shouldTryDirect(directOk) {
  return directOk !== false
}

export function transportAfterDirectAttempt(succeeded) {
  return succeeded ? 'direct' : 'relay'
}
