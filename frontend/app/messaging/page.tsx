'use client'
/**
 * Staff Messaging - ports the approved demo's #page-messaging layout into the
 * CoachLenz analysis OS. Wired to the real comms layer (/threads, /assignments,
 * /packages) with tolerant accessors and honest empty states, since the exact
 * JSON field names vary by tier and backend version.
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import OSShell from '@/components/os/OSShell'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'

const ATHLETIC_TIERS = ['athletic_dept', 'district', 'enterprise']

// Map a free-text status onto the scoped tag classes.
// Done -> tg (green), In Review -> tw (amber), Pending -> tq (neutral).
function tagClass(status: string): string {
  const s = (status || '').toLowerCase()
  if (s.includes('done') || s.includes('ready') || s.includes('complete') || s.includes('sign')) return 'tg'
  if (s.includes('review') || s.includes('build') || s.includes('progress')) return 'tw'
  return 'tq'
}

// Turn a name into 2-letter avatar initials.
function initials(name: string): string {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return 'ST'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

function timeAgo(raw: any): string {
  if (!raw) return ''
  const d = new Date(raw)
  if (isNaN(d.getTime())) return ''
  const secs = Math.floor((Date.now() - d.getTime()) / 1000)
  if (secs < 60) return 'just now'
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins} min ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

export default function MessagingPage() {
  const { user } = useAuth()
  const [threads, setThreads] = useState<any[]>([])
  const [assignments, setAssignments] = useState<any[]>([])
  const [packages, setPackages] = useState<any[]>([])

  useEffect(() => {
    if (!user) return
    api.get('/threads')
      .then(r => setThreads(Array.isArray(r.data) ? r.data : (r.data?.items || [])))
      .catch(() => setThreads([]))
    api.get('/assignments')
      .then(r => setAssignments(Array.isArray(r.data) ? r.data : (r.data?.items || [])))
      .catch(() => setAssignments([]))
    api.get('/packages')
      .then(r => setPackages(Array.isArray(r.data) ? r.data : (r.data?.items || [])))
      .catch(() => setPackages([]))
  }, [user])

  const tier = user?.organization?.subscription_tier || ''
  const playlistsUnlocked = ATHLETIC_TIERS.includes(tier)

  return (
    <OSShell title="Staff Messaging">
      <div className="sec-title" style={{ marginBottom: 16 }}>💬 Staff Communication</div>
      <div className="g2">
        {/* LEFT COLUMN */}
        <div>
          <div className="card" style={{ marginBottom: 14 }}>
            <div className="card-hdr"><div className="card-title">💬 Active Threads</div></div>
            <div className="card-body" style={{ padding: '10px 14px' }}>
              {threads.length === 0 && (
                <div style={{ padding: '18px 4px', fontSize: 12, color: 'var(--text2)' }}>
                  No staff threads yet.
                </div>
              )}
              {threads.map((t, i) => {
                const sender = t.author || t.sender || t.user?.name || t.created_by_name || t.title || 'Staff'
                const body = t.body || t.message || t.text || t.last_message || (t.title && sender !== t.title ? t.title : '') || ''
                const pin = t.pinned || t.clip
                  || (t.context_type ? `${t.context_type}${t.context_id ? ' · ' + t.context_id : ''}` : '')
                const when = timeAgo(t.updated_at || t.created_at || t.last_activity)
                return (
                  <div className="msg-thread" key={t.id || i}>
                    <div className="msg-hdr">
                      <div className="msg-av">{initials(sender)}</div>
                      <div className="msg-sender">{sender}</div>
                      {when && <div className="msg-time">{when}</div>}
                    </div>
                    {pin && <div className="msg-clip">📎 Pinned to: {pin}</div>}
                    {body && <div className="msg-body">{body}</div>}
                    <div className="msg-reply-row">
                      <div className="msg-reply-av">{initials(user?.name || 'HC')}</div>
                      <div className="msg-input">Reply to {String(sender).split(/\s+/)[0]}…</div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="card">
            <div className="card-hdr"><div className="card-title">📦 Film Packages</div></div>
            <div className="card-body" style={{ padding: 0 }}>
              {packages.length === 0 ? (
                <div style={{ padding: '18px', fontSize: 12, color: 'var(--text2)' }}>
                  No film packages yet.
                </div>
              ) : (
                <table className="tbl">
                  <thead><tr><th>Package</th><th>Status</th><th>Share</th></tr></thead>
                  <tbody>
                    {packages.map((p, i) => {
                      const name = p.name || p.title || 'Untitled package'
                      const shareable = p.share || p.link || p.share_token || p.slug
                      const status = p.status || (shareable ? 'Ready' : 'Building…')
                      return (
                        <tr key={p.id || i}>
                          <td>{name}</td>
                          <td><span className={'tag ' + tagClass(status)}>{status}</span></td>
                          <td>
                            {shareable
                              ? <span style={{ fontSize: 10, color: 'var(--green3)', cursor: 'pointer' }}>Copy Link ↗</span>
                              : <span style={{ fontSize: 10, color: 'var(--text3)' }}>-</span>}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN */}
        <div>
          <div className="card" style={{ marginBottom: 14 }}>
            <div className="card-hdr"><div className="card-title">📋 Assignments</div></div>
            <div className="card-body" style={{ padding: 0 }}>
              {assignments.length === 0 ? (
                <div style={{ padding: '18px', fontSize: 12, color: 'var(--text2)' }}>
                  No assignments yet.
                </div>
              ) : (
                <table className="tbl">
                  <thead><tr><th>Task</th><th>Assigned</th><th>Status</th></tr></thead>
                  <tbody>
                    {assignments.map((a, i) => {
                      const task = a.task || a.title || a.name || a.note || 'Clip assignment'
                      const who = a.assignee || a.assigned_to_name || a.coach || a.assigned_to || 'Unassigned'
                      const status = a.status || (a.completed_at ? 'Done' : 'Pending')
                      return (
                        <tr key={a.id || i}>
                          <td>{task}</td>
                          <td>{who}</td>
                          <td><span className={'tag ' + tagClass(status)}>{status}</span></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {playlistsUnlocked ? (
            <div className="card">
              <div className="card-hdr"><div className="card-title">🎞️ Playlists</div></div>
              <div className="card-body">
                <div style={{ fontSize: 12, color: 'var(--text2)' }}>
                  Playlists enabled on your plan. Build shareable film playlists with coaching notes.
                </div>
              </div>
            </div>
          ) : (
            <div className="tier-lock">
              <div style={{ fontSize: 22, marginBottom: 6 }}>🔒</div>
              <div style={{ fontFamily: 'var(--display)', fontSize: 13, fontWeight: 700, marginBottom: 4 }}>
                Playlists - Athletic Dept Plan
              </div>
              <div style={{ fontSize: 11, color: 'var(--text2)', marginBottom: 10 }}>
                Create shareable film playlists with coaching notes for parents, scouts, and college recruiters.
              </div>
              <Link href="/settings/billing" className="tl-btn">Upgrade to Athletic Dept →</Link>
            </div>
          )}
        </div>
      </div>

      <div className="powered">
        Powered by <a href="https://cosbyaisolutions.com" target="_blank" rel="noreferrer">Cosby AI Solutions</a>
      </div>
    </OSShell>
  )
}
