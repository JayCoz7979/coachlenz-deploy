// Coach-facing text for a failed Live Game report request.
// String detail is shown as-is (including the thin-log and empty-scope sentences).
// Validation errors contribute their msg fields. Objects contribute message or
// detail when those are strings. Stack traces, driver errors, and constraint
// names stay off the screen.

export const REPORT_FAILURE_FALLBACK = 'Could not generate the report.'

function detailText(detail: unknown): string {
  if (typeof detail === 'string') return detail.trim()
  if (Array.isArray(detail)) {
    return detail.map(item => {
      if (typeof item === 'string') return item.trim()
      if (item && typeof item === 'object' && typeof (item as { msg?: unknown }).msg === 'string') {
        return (item as { msg: string }).msg.trim()
      }
      return ''
    }).filter(Boolean).join(' ')
  }
  if (detail && typeof detail === 'object') {
    const obj = detail as { message?: unknown; detail?: unknown }
    if (typeof obj.message === 'string') return obj.message.trim()
    if (typeof obj.detail === 'string') return obj.detail.trim()
  }
  return ''
}

function looksLikeTrace(text: string): boolean {
  if (text.length > 400) return true
  return /traceback|file "|sqlalchemy|asyncpg|psycopg|integrityerror|check constraint/i.test(text)
}

export function reportFailureMessage(error: unknown): string {
  const response = (error as { response?: { data?: unknown } } | null)?.response
  const data = response?.data
  const raw = data && typeof data === 'object' && data !== null && 'detail' in data
    ? (data as { detail?: unknown }).detail
    : (typeof data === 'string' ? data : undefined)
  const text = detailText(raw)
  if (!text || looksLikeTrace(text)) return REPORT_FAILURE_FALLBACK
  return text
}
