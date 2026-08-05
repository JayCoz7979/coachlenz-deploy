'use client'
/**
 * Live Game Play Logger, Game Setup (Feature 1) + resume list.
 * A mobile-first, full-screen sideline tool. Consumes the existing CoachLenz CSS
 * design tokens only; it does not modify any global styles or existing pages.
 */
import { useEffect, useState, type CSSProperties } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import { SPORT_META } from '@/lib/sports'
import {
  TERM_SYSTEMS, GAME_TYPES, WEATHER, SURFACES, LEAGUE_FORMATS, type Sport, type TermSystem,
} from '@/components/live/fields'
import { Zap, Loader2, ChevronRight } from 'lucide-react'

const LIVE_SPORTS: Sport[] = ['football', 'flag_football', 'basketball']

const wrap: CSSProperties = { maxWidth: 640, margin: '0 auto', padding: '20px 16px 60px' }
const lbl: CSSProperties = { fontSize: 11, color: 'var(--text3)', fontWeight: 700, letterSpacing: '0.06em', marginBottom: 6, display: 'block', textTransform: 'uppercase' }
const input: CSSProperties = { width: '100%', background: 'var(--bg3)', border: '1px solid var(--border2)', borderRadius: 8, color: 'var(--text)', padding: '11px 12px', fontSize: 15, minHeight: 44 }
const card: CSSProperties = { background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: 16, marginBottom: 14 }
const section: CSSProperties = { fontSize: 12, fontWeight: 800, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12 }

function Chips({ options, value, onChange }: { options: { value: string; label: string }[]; value: string; onChange: (v: string) => void }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
      {options.map(o => (
        <button key={o.value} type="button" onClick={() => onChange(o.value)} style={{
          minHeight: 44, padding: '9px 14px', borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: 'pointer',
          border: '1px solid ' + (value === o.value ? 'var(--gold)' : 'var(--border2)'),
          background: value === o.value ? 'rgba(201,168,76,0.18)' : 'var(--bg3)',
          color: value === o.value ? 'var(--gold)' : 'var(--text2)',
        }}>{o.label}</button>
      ))}
    </div>
  )
}

// Parse pasted roster lines: "12 Smith" / "12, Smith" / "12" per line.
function parseRoster(text: string): { jersey: string; name?: string }[] {
  return text.split('\n').map(l => l.trim()).filter(Boolean).map(l => {
    const m = l.match(/^(\d{1,3})[\s,.-]*(.*)$/)
    if (!m) return null
    return { jersey: m[1], name: (m[2] || '').trim() || undefined }
  }).filter(Boolean) as { jersey: string; name?: string }[]
}

type Session = { session_id: string; sport: string; team_name?: string; opponent: string; play_count: number; game_date?: string; game_type?: string }

export default function LiveSetupPage() {
  const { user, isLoading, fetchMe } = useAuth()
  const router = useRouter()

  const [sport, setSport] = useState<Sport>('football')
  // The logger is restricted to the sport the account chose at sign-up.
  const [lockedSports, setLockedSports] = useState<string[]>([])
  const [teamName, setTeamName] = useState('')
  const [opponent, setOpponent] = useState('')
  const [gameDate, setGameDate] = useState('')
  const [location, setLocation] = useState('')
  const [homeAway, setHomeAway] = useState('home')
  const [gameType, setGameType] = useState('regular_season')
  const [weather, setWeather] = useState('')
  const [surface, setSurface] = useState('')
  const [termSystem, setTermSystem] = useState<TermSystem>('gap_letters')
  const [customRoutes, setCustomRoutes] = useState('')
  const [leagueFormat, setLeagueFormat] = useState('7-on-7')
  const [ourRoster, setOurRoster] = useState('')
  const [oppRoster, setOppRoster] = useState('')

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sessions, setSessions] = useState<Session[]>([])
  // Set when the backend requires the one-time student-data (COPPA/FERPA)
  // attestation before a session can be created. `retry` re-runs start().
  const [consent, setConsent] = useState<{ attestation: string } | null>(null)

  useEffect(() => { fetchMe() }, [])
  useEffect(() => { if (!isLoading && !user) router.push('/login') }, [isLoading, user])
  useEffect(() => {
    if (!user) return
    api.get('/live/sessions').then(r => setSessions(r.data.sessions || [])).catch(() => {})
    // Restrict the logger to the sport the account chose at sign-up: default the
    // picker to it and limit the chips to it.
    api.get('/onboarding/status').then(r => {
      const chosen: string[] = r.data?.chosen_sports || []
      if (chosen.length) { setLockedSports(chosen); setSport(chosen[0] as Sport) }
    }).catch(() => {})
  }, [user])

  const isFootball = sport === 'football' || sport === 'flag_football'

  async function start() {
    if (!teamName.trim()) { setError('Enter your team name.'); return }
    if (!opponent.trim()) { setError('Enter the opponent name.'); return }
    setBusy(true); setError('')
    try {
      const r = await api.post('/live/session', {
        sport, team_name: teamName.trim(), opponent: opponent.trim(),
        game_date: gameDate || null, location: location || null,
        is_home: homeAway === 'home', game_type: gameType,
        weather: isFootball ? (weather || null) : null,
        field_surface: isFootball ? (surface || null) : null,
        terminology_system: isFootball ? termSystem : null,
        custom_routes: isFootball ? customRoutes.split(',').map(s => s.trim()).filter(Boolean) : [],
        league_format: sport === 'flag_football' ? leagueFormat : null,
        our_roster: parseRoster(ourRoster),
        opponent_roster: parseRoster(oppRoster),
      })
      router.push(`/live/${r.data.session_id}`)
    } catch (e: any) {
      const d = e?.response?.data?.detail
      // A student-consent 403 opens the one-time attestation panel (not a dead end).
      if (e?.response?.status === 403 && d && typeof d === 'object' && d.code === 'student_consent_required') {
        setConsent({ attestation: d.attestation })
      } else {
        setError(typeof d === 'string' ? d : (d?.message || 'Could not start the game session.'))
      }
      setBusy(false)
    }
  }

  // Record the one-time COPPA/FERPA attestation, then continue starting the game.
  async function attestConsent() {
    setError('')
    try {
      await api.post('/legal/student-consent')
      setConsent(null)
      await start()
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Could not record your confirmation.')
    }
  }

  if (isLoading || !user) return null

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}>
      <div style={wrap}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
          <Zap size={22} style={{ color: 'var(--gold)' }} />
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800 }}>Live Game Logger</h1>
        </div>
        <p style={{ color: 'var(--text3)', fontSize: 13, marginBottom: 18 }}>
          Chart every play from the sideline. Generate a halftime breakdown in one tap.
        </p>

        {error && <div style={{ background: 'var(--redl)', color: 'var(--red)', borderRadius: 8, padding: '10px 14px', marginBottom: 14, fontSize: 13 }}>{error}</div>}

        {consent && (
          <div style={{ ...card, border: '1px solid var(--gold)' }}>
            <div style={{ fontWeight: 800, marginBottom: 8, color: 'var(--gold)' }}>Confirm student-data consent</div>
            <p style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.5, marginBottom: 14 }}>{consent.attestation}</p>
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={attestConsent} disabled={busy} style={{
                flex: 1, minHeight: 46, borderRadius: 8, border: 'none', cursor: 'pointer',
                background: 'var(--gold)', color: '#1c1c1c', fontWeight: 800, fontSize: 14,
              }}>I confirm &amp; continue</button>
              <button onClick={() => setConsent(null)} style={{
                minHeight: 46, padding: '0 18px', borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 14,
                background: 'transparent', border: '1px solid var(--border2)', color: 'var(--text3)',
              }}>Cancel</button>
            </div>
          </div>
        )}

        {sessions.length > 0 && (
          <div style={card}>
            <div style={section}>Resume a game</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {sessions.map(s => (
                <Link key={s.session_id} href={`/live/${s.session_id}`} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between', textDecoration: 'none',
                  background: 'var(--bg3)', border: '1px solid var(--border2)', borderRadius: 8, padding: '12px 14px', color: 'var(--text)',
                }}>
                  <span>
                    <span style={{ fontSize: 15 }}>{SPORT_META[s.sport]?.emoji} {s.team_name || 'Us'} vs {s.opponent}</span>
                    <span style={{ display: 'block', fontSize: 12, color: 'var(--text3)' }}>{s.play_count} plays logged</span>
                  </span>
                  <ChevronRight size={18} style={{ color: 'var(--text3)' }} />
                </Link>
              ))}
            </div>
          </div>
        )}

        <div style={card}>
          <div style={section}>Sport</div>
          <Chips options={(lockedSports.length ? LIVE_SPORTS.filter(s => lockedSports.includes(s)) : LIVE_SPORTS).map(s => ({ value: s, label: `${SPORT_META[s].emoji} ${SPORT_META[s].label}` }))} value={sport} onChange={v => setSport(v as Sport)} />
        </div>

        <div style={card}>
          <div style={section}>Matchup</div>
          <div style={{ display: 'grid', gap: 12 }}>
            <div><span style={lbl}>Your team</span><input style={input} value={teamName} onChange={e => setTeamName(e.target.value)} placeholder="e.g. Tanner Rattlers" /></div>
            <div><span style={lbl}>Opponent</span><input style={input} value={opponent} onChange={e => setOpponent(e.target.value)} placeholder="e.g. Athens Golden Eagles" /></div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div><span style={lbl}>Date</span><input type="date" style={input} value={gameDate} onChange={e => setGameDate(e.target.value)} /></div>
              <div><span style={lbl}>Location</span><input style={input} value={location} onChange={e => setLocation(e.target.value)} placeholder="Stadium / city" /></div>
            </div>
            <div><span style={lbl}>Home / Away</span><Chips options={[{ value: 'home', label: 'Home' }, { value: 'away', label: 'Away' }]} value={homeAway} onChange={setHomeAway} /></div>
            <div><span style={lbl}>Game type</span><Chips options={GAME_TYPES} value={gameType} onChange={setGameType} /></div>
          </div>
        </div>

        {isFootball && (
          <div style={card}>
            <div style={section}>Field & Terminology</div>
            <div style={{ display: 'grid', gap: 12 }}>
              <div><span style={lbl}>Weather</span><Chips options={WEATHER.map(w => ({ value: w, label: w }))} value={weather} onChange={setWeather} /></div>
              <div><span style={lbl}>Field surface</span><Chips options={SURFACES.map(s => ({ value: s, label: s }))} value={surface} onChange={setSurface} /></div>
              <div><span style={lbl}>Run gap / hole terminology</span>
                <Chips options={TERM_SYSTEMS.map(t => ({ value: t.value, label: t.label }))} value={termSystem} onChange={v => setTermSystem(v as TermSystem)} />
              </div>
              <div><span style={lbl}>Custom routes (comma separated)</span><input style={input} value={customRoutes} onChange={e => setCustomRoutes(e.target.value)} placeholder="Sluggo, Smash, Dagger" /></div>
              {sport === 'flag_football' && (
                <div><span style={lbl}>League format</span><Chips options={LEAGUE_FORMATS.map(f => ({ value: f, label: f }))} value={leagueFormat} onChange={setLeagueFormat} /></div>
              )}
            </div>
          </div>
        )}

        <div style={card}>
          <div style={section}>Rosters (optional)</div>
          <p style={{ color: 'var(--text3)', fontSize: 12, marginTop: -4, marginBottom: 12 }}>
            One player per line, <code>jersey name</code> (e.g. <code>12 Smith</code>). New jerseys you tap during the game are saved automatically.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div><span style={lbl}>Our roster</span><textarea style={{ ...input, minHeight: 100, resize: 'vertical', fontFamily: 'monospace' }} value={ourRoster} onChange={e => setOurRoster(e.target.value)} placeholder={'7 Johnson\n12 Smith'} /></div>
            <div><span style={lbl}>Opponent roster</span><textarea style={{ ...input, minHeight: 100, resize: 'vertical', fontFamily: 'monospace' }} value={oppRoster} onChange={e => setOppRoster(e.target.value)} placeholder={'32 Davis\n11 Lee'} /></div>
          </div>
        </div>

        <button onClick={start} disabled={busy} style={{
          width: '100%', minHeight: 52, borderRadius: 10, border: 'none', cursor: 'pointer',
          background: 'var(--gold)', color: '#1c1c1c', fontSize: 16, fontWeight: 800,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
        }}>
          {busy ? <Loader2 size={18} className="animate-spin" /> : <Zap size={18} />} Start Logging
        </button>

        <div style={{ marginTop: 18, textAlign: 'center' }}>
          <Link href="/dashboard" style={{ fontSize: 13, color: 'var(--text3)' }}>← back to dashboard</Link>
        </div>
      </div>
    </div>
  )
}
