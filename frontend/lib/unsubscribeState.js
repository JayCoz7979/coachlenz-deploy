// Result of the "Confirm unsubscribe" click on /unsubscribe.
//
// "done" only for a 2xx from POST /auth/unsubscribe. Anything else (a 400 for a
// malformed link, a 5xx, a network error) is "error", so the page never tells
// someone they are unsubscribed when nothing changed.

export async function confirmUnsubscribe(post, token) {
  try {
    const res = await post('/auth/unsubscribe', { token })
    const status = res && Number(res.status)
    return status >= 200 && status < 300 ? 'done' : 'error'
  } catch {
    return 'error'
  }
}
