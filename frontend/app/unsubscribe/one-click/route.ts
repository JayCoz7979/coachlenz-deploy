import { NextRequest, NextResponse } from 'next/server'

// RFC 8058 one-click unsubscribe. Mail providers POST here from the
// List-Unsubscribe header (body "List-Unsubscribe=One-Click"); the token is in
// the query string. This forwards it to the API's idempotent public
// /auth/unsubscribe and always answers 200, like that endpoint. A person who
// opens the link in a browser (GET) is sent to the normal /unsubscribe page.

export const dynamic = 'force-dynamic'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function tokenOf(req: NextRequest): string {
  return (req.nextUrl.searchParams.get('token') || '').trim()
}

export async function POST(req: NextRequest) {
  const token = tokenOf(req)
  if (token) {
    try {
      await fetch(`${API}/auth/unsubscribe`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ token }),
        cache: 'no-store',
      })
    } catch {
      // Best effort, same as the page: never show the provider an error.
    }
  }
  return new NextResponse('You are unsubscribed from CoachLenz marketing emails.', {
    status: 200,
    headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
  })
}

export async function GET(req: NextRequest) {
  // Relative Location, so the redirect stays on the public host behind the proxy.
  const token = tokenOf(req)
  const target = token ? `/unsubscribe?token=${encodeURIComponent(token)}` : '/unsubscribe'
  return new NextResponse(null, { status: 303, headers: { location: target, 'cache-control': 'no-store' } })
}
