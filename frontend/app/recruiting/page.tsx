'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Sidebar from '@/components/layout/Sidebar'
import { useAuth, usePermission } from '@/lib/auth'
import api from '@/lib/api'
import { Star, Trash2, Copy, Send, Plus } from 'lucide-react'
import ConfirmModal from '@/components/ConfirmModal'

interface Team { id: string; name: string; sport: string; season: string | null }
interface Player { id: string; jersey_number: string; first_name: string; last_name: string | null; position: string | null }
interface Highlight { id: string; title: string | null; start_time: number; end_time: number; url: string | null }
interface Profile {
  player: { id: string; name: string; position: string | null; grade_year: string | null; jersey_number: string }
  recruiting_enabled: boolean
  recruiting_expires_at: string | null
  share_path: string | null
  highlights: Highlight[]
  stats: { highlights_count: number; plays: number; primary_plays: number; total_yards: number; games: number }
  top_play_types: { play_type: string; count: number }[]
}
interface Clip { id: string; game_id: string; title: string | null; start_time: number; end_time: number }

export default function RecruitingPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()
  const canManage = usePermission('can_manage_roster')

  const [teams, setTeams] = useState<Team[]>([])
  const [teamId, setTeamId] = useState('')
  const [players, setPlayers] = useState<Player[]>([])
  const [playerId, setPlayerId] = useState('')
  const [profile, setProfile] = useState<Profile | null>(null)
  const [clips, setClips] = useState<Clip[]>([])
  const [addClip, setAddClip] = useState('')
  const [scoutEmail, setScoutEmail] = useState('')
  const [copied, setCopied] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  // #17: when the backend requires directory-disclosure consent, hold the
  // attestation to show a checkbox before the link can be minted.
  const [consentReq, setConsentReq] = useState<{ attestation: string; message: string } | null>(null)
  const [confirmReq, setConfirmReq] = useState<{ title: string; message: string; confirmLabel?: string; danger?: boolean; onConfirm: () => void } | null>(null)
  const [consentChecked, setConsentChecked] = useState(false)

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => {
    if (!user) return
    api.get('/teams').then(r => { setTeams(r.data); if (r.data[0]) setTeamId(r.data[0].id) }).catch(() => {})
    api.get('/clips').then(r => setClips(r.data)).catch(() => {})
  }, [user])
  useEffect(() => {
    if (!teamId) return
    api.get(`/rosters/${teamId}`).then(r => {
      setPlayers(r.data.players || [])
      setPlayerId(r.data.players?.[0]?.id || '')
    }).catch(() => { setPlayers([]); setPlayerId('') })
  }, [teamId])
  useEffect(() => { if (playerId) loadProfile(playerId); else setProfile(null) }, [playerId])

  function flash(setter: (s: string) => void, t: string) { setter(t); setTimeout(() => setter(''), 3500) }
  async function loadProfile(pid: string) {
    try { const r = await api.get(`/recruiting/players/${pid}`); setProfile(r.data) } catch { setProfile(null) }
  }
  const shareUrl = profile?.share_path ? `${typeof window !== 'undefined' ? window.location.origin : ''}${profile.share_path}` : ''
  const isBball = teams.find(t => t.id === teamId)?.sport === 'basketball'  // "Yards" is a football stat

  async function enable(withConsent = false) {
    setErr('')
    try {
      await api.post(`/recruiting/players/${playerId}/enable`, { expires_in_days: 30, disclosure_consent: withConsent })
      setConsentReq(null); setConsentChecked(false)
      await loadProfile(playerId)
    } catch (e: any) {
      const d = e.response?.data?.detail
      // #17: backend asks for directory-disclosure consent -> show the checkbox panel.
      if (d && typeof d === 'object' && d.code === 'recruiting_consent_required') {
        setConsentReq({ attestation: d.attestation, message: d.message }); return
      }
      flash(setErr, (typeof d === 'string' ? d : '') || 'Could not enable recruiting.')
    }
  }
  function disable() {
    setConfirmReq({
      title: 'Turn off public profile?',
      message: 'Turn off this player’s public recruiting profile? The share link will stop working.',
      confirmLabel: 'Turn off',
      onConfirm: async () => {
        try { await api.delete(`/recruiting/players/${playerId}`); await loadProfile(playerId) } catch {}
        setConfirmReq(null)
      },
    })
  }
  async function sendScout() {
    if (!scoutEmail) return
    setErr('')
    try { await api.post(`/recruiting/players/${playerId}/send`, { scout_email: scoutEmail }); flash(setMsg, `Profile sent to ${scoutEmail}.`); setScoutEmail('') }
    catch (e: any) { flash(setErr, e.response?.data?.detail || 'Could not send.') }
  }
  async function markHighlight() {
    if (!addClip) return
    try { await api.post('/recruiting/highlights', { clip_id: addClip, player_id: playerId }); setAddClip(''); await loadProfile(playerId) }
    catch (e: any) { flash(setErr, e.response?.data?.detail || 'Could not add highlight.') }
  }
  async function unmark(clipId: string) {
    try { await api.delete(`/recruiting/highlights/${clipId}`); await loadProfile(playerId) } catch {}
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-2xl font-bold mb-1">Recruiting Board</h2>
          <p className="text-gray-400 text-sm mb-6">Build a shareable highlight profile for a player and send it to college scouts.</p>

          {msg && <div className="mb-4 text-sm bg-brand-500/10 border border-brand-500/30 text-brand-400 rounded p-2">{msg}</div>}
          {err && <div className="mb-4 text-sm bg-red-400/10 border border-red-400/30 text-red-400 rounded p-2">{err}</div>}

          {teams.length === 0 ? (
            <div className="card text-center text-gray-400">
              Create a <Link href="/teams" className="text-brand-400 hover:underline">team</Link> and <Link href="/roster" className="text-brand-400 hover:underline">roster</Link> first.
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-4 mb-6">
                <div>
                  <label className="label">Team</label>
                  <select className="input" value={teamId} onChange={e => setTeamId(e.target.value)}>
                    {teams.map(t => <option key={t.id} value={t.id}>{t.name}{t.season ? ` · ${t.season}` : ''}</option>)}
                  </select>
                </div>
                <div>
                  <label className="label">Player</label>
                  <select className="input" value={playerId} onChange={e => setPlayerId(e.target.value)} disabled={players.length === 0}>
                    {players.length === 0 && <option>No players on this roster</option>}
                    {players.map(p => <option key={p.id} value={p.id}>#{p.jersey_number} {p.first_name} {p.last_name || ''}</option>)}
                  </select>
                </div>
              </div>

              {profile && (
                <>
                  {/* Sharing */}
                  <div className="card mb-6">
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <div className="text-lg font-semibold">{profile.player.name}</div>
                        <div className="text-sm text-gray-400">{[profile.player.position, profile.player.grade_year && `Class of ${profile.player.grade_year}`].filter(Boolean).join(' · ') || '—'}</div>
                      </div>
                      <span className={`text-xs px-2 py-1 rounded ${profile.recruiting_enabled ? 'bg-brand-500/15 text-brand-400' : 'bg-gray-700 text-gray-400'}`}>
                        {profile.recruiting_enabled ? 'Shared' : 'Private'}
                      </span>
                    </div>

                    {!canManage ? (
                      <p className="text-sm text-gray-500">You don&apos;t have permission to manage recruiting.</p>
                    ) : !profile.recruiting_enabled ? (
                      consentReq ? (
                        <div className="space-y-2 border border-brand-500/30 rounded p-3 bg-brand-500/5">
                          <p className="text-sm text-gray-300">{consentReq.message}</p>
                          <label className="flex items-start gap-2 text-xs text-gray-400">
                            <input type="checkbox" className="mt-0.5" checked={consentChecked} onChange={e => setConsentChecked(e.target.checked)} />
                            <span>{consentReq.attestation}</span>
                          </label>
                          <button onClick={() => enable(true)} disabled={!consentChecked} className="btn-primary flex items-center gap-2 disabled:opacity-40"><Star size={15} /> Enable &amp; publish</button>
                        </div>
                      ) : (
                        <button onClick={() => enable()} className="btn-primary flex items-center gap-2"><Star size={15} /> Enable recruiting profile</button>
                      )
                    ) : (
                      <div className="space-y-3">
                        <div>
                          <label className="label">Public link (no login required)</label>
                          <div className="flex gap-2">
                            <input readOnly value={shareUrl} onFocus={e => e.currentTarget.select()} className="input text-xs" />
                            <button onClick={() => { navigator.clipboard.writeText(shareUrl); setCopied(true); setTimeout(() => setCopied(false), 2000) }} className="btn-secondary flex items-center gap-1"><Copy size={14} />{copied ? 'Copied' : 'Copy'}</button>
                          </div>
                          {profile.recruiting_expires_at && <p className="text-xs text-gray-500 mt-1">Expires {new Date(profile.recruiting_expires_at).toLocaleDateString()}</p>}
                        </div>
                        <div className="flex gap-2 items-end">
                          <div className="flex-1"><label className="label">Send to a scout</label><input type="email" className="input" placeholder="scout@school.edu" value={scoutEmail} onChange={e => setScoutEmail(e.target.value)} /></div>
                          <button onClick={sendScout} className="btn-primary flex items-center gap-2" disabled={!scoutEmail}><Send size={14} /> Send</button>
                        </div>
                        <button onClick={disable} className="text-xs text-red-400 hover:underline">Turn off public profile</button>
                      </div>
                    )}
                  </div>

                  {/* Season stats */}
                  <div className="card mb-6">
                    <div className="font-semibold mb-3">Season stats</div>
                    <div className={`grid ${isBball ? 'grid-cols-3' : 'grid-cols-4'} gap-3 text-center`}>
                      <div><div className="text-2xl font-bold tabular-nums">{profile.stats.plays}</div><div className="text-xs text-gray-400">Plays</div></div>
                      <div><div className="text-2xl font-bold tabular-nums">{profile.stats.primary_plays}</div><div className="text-xs text-gray-400">Primary</div></div>
                      {!isBball && <div><div className="text-2xl font-bold tabular-nums">{profile.stats.total_yards}</div><div className="text-xs text-gray-400">Yards</div></div>}
                      <div><div className="text-2xl font-bold tabular-nums">{profile.stats.games}</div><div className="text-xs text-gray-400">Games</div></div>
                    </div>
                    {profile.top_play_types.length > 0 && (
                      <p className="text-xs text-gray-500 mt-3">Most involved on: {profile.top_play_types.map(t => `${t.play_type} (${t.count})`).join(', ')}</p>
                    )}
                    <p className="text-xs text-gray-600 mt-2">Derived from tagged plays across this team&apos;s analyzed games.</p>
                  </div>

                  {/* Highlights */}
                  <div className="card">
                    <div className="flex items-center justify-between mb-3">
                      <div className="font-semibold">Highlights <span className="text-gray-500 text-sm">({profile.stats.highlights_count})</span></div>
                    </div>
                    {canManage && (
                      <div className="flex gap-2 mb-4">
                        <select className="input" value={addClip} onChange={e => setAddClip(e.target.value)}>
                          <option value="">Add a clip as a highlight…</option>
                          {clips.map(c => <option key={c.id} value={c.id}>{c.title || 'Clip'} ({Math.round(c.end_time - c.start_time)}s)</option>)}
                        </select>
                        <button onClick={markHighlight} className="btn-secondary flex items-center gap-1" disabled={!addClip}><Plus size={14} /> Add</button>
                      </div>
                    )}
                    <div className="space-y-2">
                      {profile.highlights.map(h => (
                        <div key={h.id} className="flex items-center justify-between border-b border-gray-800/60 pb-2">
                          <div>
                            <div className="text-sm text-gray-100">{h.title || 'Highlight'}</div>
                            <div className="text-xs text-gray-500">{Math.round(h.end_time - h.start_time)}s clip</div>
                          </div>
                          <div className="flex items-center gap-3">
                            {h.url && <a href={h.url} target="_blank" rel="noopener noreferrer" className="text-brand-400 text-sm hover:underline">Watch</a>}
                            {canManage && <button onClick={() => unmark(h.id)} className="text-gray-500 hover:text-red-400"><Trash2 size={14} /></button>}
                          </div>
                        </div>
                      ))}
                      {profile.highlights.length === 0 && <p className="text-sm text-gray-500">No highlights yet{canManage ? '. Add a clip above.' : '.'}</p>}
                    </div>
                  </div>
                </>
              )}
            </>
          )}
        </div>
        <ConfirmModal
          open={!!confirmReq}
          title={confirmReq?.title || ''}
          message={confirmReq?.message || ''}
          confirmLabel={confirmReq?.confirmLabel}
          danger={confirmReq?.danger ?? true}
          onConfirm={() => confirmReq?.onConfirm()}
          onCancel={() => setConfirmReq(null)}
        />
      </main>
    </div>
  )
}
