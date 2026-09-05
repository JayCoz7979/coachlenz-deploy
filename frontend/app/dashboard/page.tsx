'use client'
import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth'
import api from '@/lib/api'
import OSShell from '@/components/os/OSShell'

/* ---------- small view helpers (scoped .clz classes from os.css) ---------- */
function Pbar({ label, value, pct, kind = 'g' }: { label: string; value: string; pct: number; kind?: 'g' | 'o' | 'r' }) {
  return (
    <div className="pb-wrap">
      <div className="pb-top"><span>{label}</span><b>{value}</b></div>
      <div className="pb"><div className={'pf pf-' + kind} style={{ width: Math.max(0, Math.min(100, pct)) + '%' }} /></div>
    </div>
  )
}
function confTag(c?: string) {
  const k = (c || '').toUpperCase()
  if (k === 'HIGH') return <span className="tag tg">High</span>
  if (k === 'MEDIUM') return <span className="tag tgo">Medium</span>
  return <span className="tag tq">{k ? k[0] + k.slice(1).toLowerCase() : 'Low'}</span>
}
function Section({ id, icon, title, sub, open, onToggle, children }: any) {
  return (
    <div className={'expand-section' + (open ? ' open' : '')}>
      <div className="expand-hdr" onClick={onToggle}>
        <div className="expand-hdr-left">
          <span className="expand-hdr-icon">{icon}</span>
          <div>
            <div className="expand-hdr-title">{title}</div>
            {sub && <div className="expand-hdr-sub">{sub}</div>}
          </div>
        </div>
        <span className="expand-chevron">▶</span>
      </div>
      <div className="expand-body">{children}</div>
    </div>
  )
}

const asArray = (x: any): any[] => (Array.isArray(x) ? x : x && typeof x === 'object' ? Object.entries(x).map(([k, v]) => ({ key: k, ...(typeof v === 'object' ? v : { value: v }) })) : [])
const pct = (n: any) => (typeof n === 'number' ? Math.round(n > 1 ? n : n * 100) : null)

export default function DashboardPage() {
  const { user } = useAuth()
  const router = useRouter()
  const [games, setGames] = useState<any[]>([])
  const [report, setReport] = useState<any | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [open, setOpen] = useState<string | null>('games')
  const [sport, setSport] = useState<string>('')

  // Onboarding gate + the org's locked sport (drives sport-aware labels below).
  useEffect(() => {
    if (!user) return
    api.get('/onboarding/status').then(s => {
      if (!s.data?.onboarding_completed) router.push('/onboarding')
      setSport((s.data?.chosen_sports || [])[0] || '')
    }).catch(() => {})
  }, [user])

  useEffect(() => {
    if (!user) return
    Promise.all([
      api.get('/games').catch(() => ({ data: [] })),
      api.get('/reports').catch(() => ({ data: [] })),
    ]).then(async ([g, r]) => {
      setGames(g.data || [])
      const finished = (r.data || []).filter((x: any) => x.generated_at).sort((a: any, b: any) => (b.generated_at || '').localeCompare(a.generated_at || ''))
      if (finished.length) {
        try { const d = await api.get(`/reports/${finished[0].id}`); setReport(d.data) } catch {}
      }
      setLoaded(true)
    })
  }, [user])

  const s = report?.summary || null
  const off = s?.offense || {}
  const scouting = s?.scouting || {}

  const tendencies = useMemo(() => asArray(scouting.situational_tendencies).slice(0, 8), [report])
  const priorities = useMemo(() => asArray(scouting?.game_plan?.head_coach_priorities || s?.head_coach_priorities), [report])
  const formations = useMemo(() => asArray(off.top_formations).slice(0, 8), [report])
  const players = useMemo(() => asArray(s?.player_tendencies).slice(0, 8), [report])
  const keys = useMemo(() => asArray(scouting.scouting_keys).slice(0, 6), [report])

  const totalPlays = s?.total_plays ?? null
  const confidence = report ? (scouting.report_status === 'FINAL' || s?.report_status === 'FINAL' ? 'FINAL' : 'PRELIM') : null

  // Sport-aware labels: "formations" and "pre-snap" are football-only terms.
  const resolvedSport = sport || report?.sport || games[0]?.sport || 'football'
  const isBball = resolvedSport === 'basketball'

  const briefText = useMemo(() => {
    if (!report) return null
    const bits: string[] = []
    if (tendencies[0]?.statement) bits.push(tendencies[0].statement)
    if (tendencies[1]?.statement) bits.push(tendencies[1].statement)
    if (keys[0] && typeof keys[0] === 'string') bits.push(keys[0])
    else if (keys[0]?.statement) bits.push(keys[0].statement)
    return bits.length ? bits.join(' ') : 'Your analysis room is live. Expand any section below for the full breakdown.'
  }, [report, tendencies, keys])

  const t = (id: string) => setOpen(open === id ? null : id)

  // Primary next action. One dominant step: the free Live Game Logger is the way in;
  // a returning coach is pointed at their next game and latest breakdown.
  const hasGames = games.length > 0
  const hero = {
    title: hasGames ? 'Ready for your next opponent?' : 'Turn your next game into a coordinator breakdown',
    sub: hasGames
      ? 'Chart a live game from the sideline and get the tendencies, player keys, and adjustments, or open your latest breakdown.'
      : 'Chart your game from the sideline and CoachLenz writes the tendencies, player keys, and adjustments. The Live Game Logger is free, no credit card.',
    ctaHref: '/live',
    ctaLabel: hasGames ? 'Start a live game' : 'Log your first game free',
    ghostHref: report ? '/tendencies' : '/examples',
    ghostLabel: report ? 'Open latest breakdown' : 'See a sample report',
  }

  return (
    <OSShell title="Dashboard">
      {/* ── PRIMARY ACTION HERO ── */}
      <div className="hero">
        <div className="hero-main">
          <div className="hero-eyebrow">▶ Live Game Logger · Free</div>
          <div className="hero-title">{hero.title}</div>
          <div className="hero-sub">{hero.sub}</div>
        </div>
        <div className="hero-actions">
          <Link href={hero.ctaHref} className="hero-cta">{hero.ctaLabel}</Link>
          <Link href={hero.ghostHref} className="hero-ghost">{hero.ghostLabel}</Link>
        </div>
      </div>

      {/* ── FIRST-SESSION ACTIVATION CHECKLIST ── */}
      <Setup sport={sport} hasGames={hasGames} hasReport={!!report} />

      {/* ── AI COACH BRIEF (only once a real report exists; the hero owns the empty state) ── */}
      {report ? (
        <div className="ai-brief">
          <div className="ai-brief-hdr">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <div className="ai-pill"><div className="ai-dot" />AI Coach Brief</div>
              <div className="ai-title">{report.title || `${scouting.opponent || 'Opponent'} - Pre-Game Scout`}</div>
            </div>
            <div className="ai-time">{report.generated_at ? new Date(report.generated_at).toLocaleString() : ''}</div>
          </div>
          <div className="ai-summary-text">{briefText}</div>
          {!!priorities.length && (
            <div className="ai-flags">
              {priorities.slice(0, 4).map((p: any, i: number) => (
                <Link key={i} href="/tendencies" className="ai-flag" style={{ textDecoration: 'none' }}>
                  <div className={'ai-flag-dot ' + ['af-g', 'af-gold', 'af-r', 'af-w'][i % 4]} />
                  <div className="ai-flag-info">
                    <div className="ai-flag-title">{p.phase || p.priority || 'Priority'}</div>
                    <div className="ai-flag-sub">{p.call || p.statement || ''}</div>
                  </div>
                  <div className="ai-flag-arrow">→</div>
                </Link>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {/* ── KPI ROW ── */}
      <div className="sec-hdr"><div className="sec-title">📊 Season Overview</div></div>
      <div className="kpi-row" style={{ marginBottom: 16 }}>
        <div className="kpi" onClick={() => t('games')}>
          <div className="kpi-accent" />
          <div className="kpi-lbl">Games Analyzed</div>
          <div className="kpi-val">{games.length}</div>
          <div className="kpi-sub">{games[0]?.opponent ? `Latest: ${games[0].opponent}` : 'Film library'}</div>
          <div className="kpi-hint">↕ Click to see game list</div>
        </div>
        <div className="kpi" onClick={() => t('tendencies')}>
          <div className="kpi-accent" />
          <div className="kpi-lbl">Total Plays Tagged</div>
          <div className="kpi-val">{totalPlays != null ? totalPlays.toLocaleString() : '-'}</div>
          <div className="kpi-sub">{report ? 'From latest scout report' : 'Tag film to populate'}</div>
          <div className="kpi-hint">↕ Click for tendencies</div>
        </div>
        {isBball ? (
          <div className="kpi" onClick={() => t('tendencies')}>
            <div className="kpi-accent" />
            <div className="kpi-lbl">Situations Tracked</div>
            <div className="kpi-val">{tendencies.length || '-'}</div>
            <div className="kpi-sub">{tendencies[0]?.category || 'Sets, actions & tendencies'}</div>
            <div className="kpi-hint">↕ Click for tendencies</div>
          </div>
        ) : (
          <div className="kpi" onClick={() => t('formations')}>
            <div className="kpi-accent" />
            <div className="kpi-lbl">Formations Tracked</div>
            <div className="kpi-val">{formations.length || '-'}</div>
            <div className="kpi-sub">{formations[0]?.formation || formations[0]?.key || 'Formation matrix'}</div>
            <div className="kpi-hint">↕ Click for formation detail</div>
          </div>
        )}
        <div className="kpi" onClick={() => t('tendencies')}>
          <div className="kpi-accent" style={{ background: 'var(--gold)' }} />
          <div className="kpi-lbl">Report Status</div>
          <div className="kpi-val" style={{ color: 'var(--gold)' }}>{confidence || '-'}</div>
          <div className="kpi-sub">{report ? `${scouting.games_scouted ?? '-'} games scouted` : 'No report yet'}</div>
          <div className="kpi-hint">↕ Click for tendencies</div>
        </div>
        <div className="kpi" onClick={() => t('players')}>
          <div className="kpi-accent" style={{ background: 'var(--green4)' }} />
          <div className="kpi-lbl">Player Intel Profiles</div>
          <div className="kpi-val" style={{ color: 'var(--green4)' }}>{players.length || '-'}</div>
          <div className="kpi-sub">{isBball ? 'Player tendencies' : 'Pre-snap tells'}</div>
          <div className="kpi-hint">↕ Click for player tells</div>
        </div>
      </div>

      {/* New-coach helper: see what a Live Game report looks like before logging one. */}
      <div style={{ margin: '0 0 16px', fontSize: 12.5, color: 'var(--text3)' }}>
        New to the <Link href="/live" style={{ color: 'var(--green3)' }}>Live Game Logger</Link>?{' '}
        <Link href="/examples" style={{ color: 'var(--gold)', fontWeight: 600 }}>See example reports →</Link>
      </div>

      {/* ── EXPANDABLE SECTIONS ── */}
      <Section icon="📅" title={`${games.length} Games Analyzed`} sub="Your film library" open={open === 'games'} onToggle={() => t('games')}>
        {games.length ? (
          <table className="tbl">
            <thead><tr><th>Opponent</th><th>Date</th><th>Sport</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {games.map(g => (
                <tr key={g.id}>
                  <td style={{ fontWeight: 500 }}>{g.opponent || g.title}</td>
                  <td className="mono" style={{ color: 'var(--text2)' }}>{g.game_date ? new Date(g.game_date).toLocaleDateString() : '-'}</td>
                  <td style={{ textTransform: 'capitalize', color: 'var(--text2)' }}>{g.sport}</td>
                  <td>{g.status === 'ready' ? <span className="tag tg">Ready</span> : g.status === 'manual' ? <span className="tag tgo">Scout</span> : <span className="tag tq">{g.status}</span>}</td>
                  <td style={{ textAlign: 'right' }}><Link href={`/games/${g.id}`} className="tag tq" style={{ textDecoration: 'none' }}>Open film →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div style={{ color: 'var(--text3)', fontSize: 12 }}>No games yet. <Link href="/games/upload?tab=url" style={{ color: 'var(--green3)' }}>Import your first film →</Link></div>}
      </Section>

      {!isBball && (
      <Section icon="🏈" title="Formation Breakdown" sub={formations.length ? `${formations.length} formations` : 'Populates from tagged film'} open={open === 'formations'} onToggle={() => t('formations')}>
        {formations.length ? (
          <div className="form-grid">
            {formations.map((f: any, i: number) => {
              const runp = pct(f.run_pct), passp = pct(f.pass_pct)
              return (
                <div className="form-card" key={i}>
                  <div className="form-name">{f.formation || f.key || `Formation ${i + 1}`}</div>
                  <div className="form-snaps">{f.count != null ? `${f.count} snaps` : ''}</div>
                  {runp != null && <Pbar label="Run" value={runp + '%'} pct={runp} kind="g" />}
                  {passp != null && <Pbar label="Pass" value={passp + '%'} pct={passp} kind="o" />}
                </div>
              )
            })}
          </div>
        ) : <Empty />}
      </Section>
      )}

      <Section icon="🎯" title="Top Tendencies" sub={tendencies.length ? `${tendencies.length} ranked patterns` : 'Populates from scout report'} open={open === 'tendencies'} onToggle={() => t('tendencies')}>
        {tendencies.length ? tendencies.map((td: any, i: number) => (
          <div className="tend-row" key={i} style={{ cursor: 'default' }}>
            <div className="tend-sit">{td.category || 'Tendency'}</div>
            <div className="tend-call" style={{ width: 'auto', flex: 2 }}>{td.statement}</div>
            <div className="tend-n">{td.sample ? `${td.sample} reps` : ''}</div>
            {confTag(td.confidence)}
          </div>
        )) : <Empty />}
        {!!keys.length && (
          <div className="ai-box" style={{ marginTop: 12 }}>
            <strong>Auto Scouting Keys:</strong> {keys.map((k: any, i: number) => (typeof k === 'string' ? k : k.statement)).filter(Boolean).join(' · ')}
          </div>
        )}
      </Section>

      <Section icon="👤" title="Player Intelligence" sub={players.length ? `${players.length} profiles` : 'Populates as players are tagged'} open={open === 'players'} onToggle={() => t('players')}>
        {players.length ? (
          <div className="g3" style={{ marginBottom: 0 }}>
            {players.map((p: any, i: number) => (
              <div key={i} style={{ background: 'var(--bg3)', border: '1px solid var(--border)', borderRadius: 9, padding: 13 }}>
                <div style={{ fontFamily: 'var(--display)', fontSize: 12, fontWeight: 700, marginBottom: 6 }}>{p.player || p.key || `Player ${i + 1}`}</div>
                {asArray(p.tells || p.tendencies).slice(0, 4).map((tl: any, j: number) => {
                  const v = pct(tl.pct ?? tl.rate ?? tl.value)
                  return <Pbar key={j} label={tl.tell || tl.label || tl.key || 'Tell'} value={v != null ? v + '%' : ''} pct={v || 0} kind="o" />
                })}
              </div>
            ))}
          </div>
        ) : <Empty note="Player-level tells appear here once plays are tagged with jersey numbers." />}
      </Section>

      <div className="powered">Powered by <a href="https://cosbyaisolutions.com" target="_blank" rel="noreferrer">Cosby AI Solutions</a></div>
    </OSShell>
  )
}

function Setup({ sport, hasGames, hasReport }: { sport: string; hasGames: boolean; hasReport: boolean }) {
  // Honest, verifiable steps. Endowed progress: account + sport start checked, so a
  // fresh coach opens at 2 of 4 and feels pulled to finish, not starting from zero.
  const steps = [
    { label: 'Account created', done: true },
    { label: 'Sport locked in', done: !!sport },
    { label: 'Log your first game', done: hasGames, href: '/live', cta: 'Log a game free' },
    { label: 'Get your first breakdown', done: hasReport, href: '/live', cta: 'Open the logger' },
  ]
  const doneCount = steps.filter(s => s.done).length
  const total = steps.length
  const complete = doneCount === total
  const nextIdx = steps.findIndex(s => !s.done)

  const [dismissed, setDismissed] = useState(false)
  useEffect(() => {
    try { setDismissed(localStorage.getItem('clz_setup_dismissed') === '1') } catch {}
  }, [])
  function dismiss() {
    try { localStorage.setItem('clz_setup_dismissed', '1') } catch {}
    setDismissed(true)
  }

  if (complete && dismissed) return null
  if (complete) {
    return (
      <div className="setup-done">
        <span>✓ You are all set up. {doneCount} of {total} done, your analysis room is live.</span>
        <button className="setup-x" onClick={dismiss} aria-label="Dismiss">×</button>
      </div>
    )
  }
  return (
    <div className="setup">
      <div className="setup-top">
        <div className="setup-title">Get to your first breakdown</div>
        <div className="setup-count">{doneCount} of {total}</div>
      </div>
      <div className="setup-bar"><div className="setup-fill" style={{ width: `${(doneCount / total) * 100}%` }} /></div>
      <div className="setup-steps">
        {steps.map((s, i) => (
          <div key={i} className={'setup-step' + (s.done ? ' done' : i === nextIdx ? ' next' : '')}>
            <span className="setup-check">{s.done ? '✓' : ''}</span>
            <span>{s.label}</span>
            {i === nextIdx && s.href && <Link href={s.href} className="setup-cta">{s.cta}</Link>}
          </div>
        ))}
      </div>
    </div>
  )
}

function Empty({ note }: { note?: string }) {
  return (
    <div style={{ color: 'var(--text3)', fontSize: 12, padding: '4px 0' }}>
      {note || 'This activates automatically once your film is tagged and a scout report is generated.'}{' '}
      <Link href="/scout" style={{ color: 'var(--green3)' }}>Start a scout →</Link>
    </div>
  )
}
