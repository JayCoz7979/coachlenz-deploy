'use client'
import { useEffect, useState } from 'react'

const SESSION_KEY = 'cl_intro_seen'

const AI_TAGS = [
  { text: 'RUN TENDENCY DETECTED', x: '62%', y: '38%', delay: 0.72 },
  { text: '3RD DOWN PATTERN: IDENTIFIED', x: '58%', y: '48%', delay: 0.92 },
  { text: 'COVERAGE WEAKNESS FOUND', x: '60%', y: '58%', delay: 1.08 },
  { text: 'FORMATION TELL EXPOSED', x: '55%', y: '67%', delay: 1.2 },
]

export default function IntroOverlay() {
  const [visible, setVisible] = useState(false)
  const [exiting, setExiting] = useState(false)

  useEffect(() => {
    // Respect prefers-reduced-motion
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) return

    // Show only once per session
    if (sessionStorage.getItem(SESSION_KEY)) return

    setVisible(true)
    sessionStorage.setItem(SESSION_KEY, '1')

    // Begin exit at 2.1s
    const exitTimer = setTimeout(() => setExiting(true), 2100)
    // Unmount at 2.6s (after fade completes)
    const unmountTimer = setTimeout(() => setVisible(false), 2650)

    return () => { clearTimeout(exitTimer); clearTimeout(unmountTimer) }
  }, [])

  if (!visible) return null

  return (
    <>
      <style>{`
        @keyframes cl-tunnel-glow {
          0%   { opacity: 0.3; transform: scale(0.85); }
          60%  { opacity: 1;   transform: scale(1.05); }
          100% { opacity: 1;   transform: scale(1); }
        }
        @keyframes cl-silo-rise {
          from { opacity: 0; transform: translateY(18px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes cl-tag-pop {
          0%   { opacity: 0; transform: translateX(-6px); }
          20%  { opacity: 1; transform: translateX(0); }
          80%  { opacity: 1; }
          100% { opacity: 0.85; }
        }
        @keyframes cl-logo-reveal {
          0%   { opacity: 0; letter-spacing: 0.4em; filter: blur(6px); }
          100% { opacity: 1; letter-spacing: 0.12em; filter: blur(0); }
        }
        @keyframes cl-scan {
          0%   { left: -100%; }
          100% { left: 200%; }
        }
        @keyframes cl-overlay-exit {
          0%   { opacity: 1; }
          100% { opacity: 0; }
        }
        @keyframes cl-light-burst {
          0%   { opacity: 0; transform: scale(0.6); }
          100% { opacity: 0.55; transform: scale(1.5); }
        }
        .cl-intro { animation: cl-overlay-exit 0.5s ease forwards; }
        .cl-tag-line { position: relative; overflow: hidden; }
        .cl-tag-line::after {
          content: '';
          position: absolute;
          top: 0; left: -100%; width: 40%; height: 100%;
          background: linear-gradient(90deg, transparent, rgba(201,168,76,0.4), transparent);
          animation: cl-scan 0.6s ease forwards;
        }
      `}</style>

      <div
        role="presentation"
        aria-hidden="true"
        className={exiting ? 'cl-intro' : ''}
        style={{
          position: 'fixed', inset: 0, zIndex: 9999,
          background: '#04060a',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          overflow: 'hidden',
          fontFamily: 'system-ui, sans-serif',
        }}
      >
        {/* ── TUNNEL WALLS ── */}
        <svg
          viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice"
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
        >
          <defs>
            <radialGradient id="stadiumLight" cx="50%" cy="42%" r="38%">
              <stop offset="0%"   stopColor="#e8f4e8" stopOpacity="1" />
              <stop offset="18%"  stopColor="#c8e8b0" stopOpacity="0.9" />
              <stop offset="45%"  stopColor="#1a5c2a" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#02040a" stopOpacity="0" />
            </radialGradient>
            <radialGradient id="lightBurst" cx="50%" cy="42%" r="22%">
              <stop offset="0%"  stopColor="#ffffff" stopOpacity="0.95" />
              <stop offset="40%" stopColor="#d4edda" stopOpacity="0.5" />
              <stop offset="100%" stopColor="#1a5c2a" stopOpacity="0" />
            </radialGradient>
            <clipPath id="tunnelArch">
              <ellipse cx="720" cy="378" rx="310" ry="230" />
            </clipPath>
          </defs>

          {/* Tunnel ceiling/left wall */}
          <path d="M0,0 L0,900 L410,900 L410,580 Q480,560 540,500 Q600,430 620,378 Q640,310 720,280 L0,280 Z"
            fill="#050a07" opacity="0.97" />
          {/* Tunnel ceiling/right wall */}
          <path d="M1440,0 L1440,900 L1030,900 L1030,580 Q960,560 900,500 Q840,430 820,378 Q800,310 720,280 L1440,280 Z"
            fill="#050a07" opacity="0.97" />
          {/* Top fill */}
          <rect x="0" y="0" width="1440" height="282" fill="#050a07" />

          {/* Stadium light glow */}
          <ellipse cx="720" cy="378" rx="320" ry="235"
            fill="url(#stadiumLight)"
            style={{ animation: 'cl-tunnel-glow 0.8s ease forwards', opacity: 0 }}
          />

          {/* Bright center burst */}
          <ellipse cx="720" cy="360" rx="130" ry="100"
            fill="url(#lightBurst)"
            style={{ animation: 'cl-light-burst 0.6s 0.3s ease forwards', opacity: 0 }}
          />

          {/* Tunnel wall texture lines */}
          {[0.15, 0.28, 0.72, 0.85].map((x, i) => (
            <line key={i}
              x1={x * 1440} y1="0"
              x2={720 + (x - 0.5) * 300} y2="320"
              stroke="rgba(45,140,64,0.07)" strokeWidth="1"
            />
          ))}

          {/* Player silhouettes at tunnel mouth */}
          <g style={{ animation: 'cl-silo-rise 0.5s 0.55s ease forwards', opacity: 0 }}>
            {/* Center player (taller, QB stance) */}
            <g transform="translate(720, 525)">
              <ellipse cx="0" cy="-80" rx="13" ry="13" fill="#0a1a0d" opacity="0.92"/>
              <rect x="-10" y="-68" width="20" height="38" rx="3" fill="#0a1a0d" opacity="0.92"/>
              <rect x="-22" y="-62" width="12" height="24" rx="2" fill="#0a1a0d" opacity="0.88"/>
              <rect x="10" y="-62" width="12" height="24" rx="2" fill="#0a1a0d" opacity="0.88"/>
              <rect x="-8" y="-30" width="7" height="30" rx="2" fill="#0a1a0d" opacity="0.92"/>
              <rect x="1" y="-30" width="7" height="30" rx="2" fill="#0a1a0d" opacity="0.92"/>
            </g>
            {/* Left player */}
            <g transform="translate(660, 545)">
              <ellipse cx="0" cy="-70" rx="11" ry="11" fill="#0a1a0d" opacity="0.88"/>
              <rect x="-8" y="-59" width="16" height="32" rx="3" fill="#0a1a0d" opacity="0.88"/>
              <rect x="-18" y="-54" width="10" height="20" rx="2" fill="#0a1a0d" opacity="0.82"/>
              <rect x="8" y="-54" width="10" height="20" rx="2" fill="#0a1a0d" opacity="0.82"/>
              <rect x="-6" y="-27" width="6" height="27" rx="2" fill="#0a1a0d" opacity="0.88"/>
              <rect x="0" y="-27" width="6" height="27" rx="2" fill="#0a1a0d" opacity="0.88"/>
            </g>
            {/* Right player */}
            <g transform="translate(780, 540)">
              <ellipse cx="0" cy="-70" rx="11" ry="11" fill="#0a1a0d" opacity="0.88"/>
              <rect x="-8" y="-59" width="16" height="32" rx="3" fill="#0a1a0d" opacity="0.88"/>
              <rect x="-18" y="-54" width="10" height="20" rx="2" fill="#0a1a0d" opacity="0.82"/>
              <rect x="8" y="-54" width="10" height="20" rx="2" fill="#0a1a0d" opacity="0.82"/>
              <rect x="-6" y="-27" width="6" height="27" rx="2" fill="#0a1a0d" opacity="0.88"/>
              <rect x="0" y="-27" width="6" height="27" rx="2" fill="#0a1a0d" opacity="0.88"/>
            </g>
            {/* Far left faint silhouette */}
            <g transform="translate(612, 560)" opacity="0.55">
              <ellipse cx="0" cy="-62" rx="9" ry="9" fill="#0a1a0d"/>
              <rect x="-7" y="-53" width="14" height="28" rx="2" fill="#0a1a0d"/>
              <rect x="-5" y="-25" width="10" height="25" rx="2" fill="#0a1a0d"/>
            </g>
            {/* Far right faint silhouette */}
            <g transform="translate(828, 558)" opacity="0.55">
              <ellipse cx="0" cy="-62" rx="9" ry="9" fill="#0a1a0d"/>
              <rect x="-7" y="-53" width="14" height="28" rx="2" fill="#0a1a0d"/>
              <rect x="-5" y="-25" width="10" height="25" rx="2" fill="#0a1a0d"/>
            </g>
          </g>
        </svg>

        {/* ── AI SCOUTING OVERLAYS ── */}
        {AI_TAGS.map((tag, i) => (
          <div key={i} className="cl-tag-line" style={{
            position: 'absolute',
            left: tag.x, top: tag.y,
            transform: 'translateX(-50%)',
            fontFamily: '"DM Mono", "Courier New", monospace',
            fontSize: 'clamp(9px, 1.1vw, 12px)',
            fontWeight: 500,
            letterSpacing: '0.18em',
            color: '#C9A84C',
            textShadow: '0 0 12px rgba(201,168,76,0.6)',
            whiteSpace: 'nowrap',
            opacity: 0,
            animation: `cl-tag-pop 0.5s ${tag.delay}s ease forwards`,
            borderLeft: '2px solid #C9A84C',
            paddingLeft: 8,
          }}>
            <span style={{ fontSize: '0.7em', opacity: 0.6, marginRight: 6 }}>◆</span>
            {tag.text}
          </div>
        ))}

        {/* ── LOGO REVEAL ── */}
        <div style={{
          position: 'absolute',
          top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)',
          textAlign: 'center',
          opacity: 0,
          animation: 'cl-logo-reveal 0.55s 1.42s cubic-bezier(0.16,1,0.3,1) forwards',
          pointerEvents: 'none',
        }}>
          {/* Shield SVG mark */}
          <svg width="56" height="64" viewBox="0 0 56 64" style={{ display: 'block', margin: '0 auto 10px' }}>
            <defs>
              <linearGradient id="shieldGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#2d8c40"/>
                <stop offset="100%" stopColor="#1a5c2a"/>
              </linearGradient>
            </defs>
            <path d="M28 2 L52 12 L52 34 Q52 52 28 62 Q4 52 4 34 L4 12 Z"
              fill="url(#shieldGrad)" stroke="#2d8c40" strokeWidth="1.5"/>
            {/* Crosshair C */}
            <circle cx="28" cy="32" r="11" fill="none" stroke="rgba(248,246,240,0.25)" strokeWidth="1"/>
            <path d="M36 26 Q28 20 20 26 Q16 32 20 38 Q28 44 36 38"
              fill="none" stroke="#f8f6f0" strokeWidth="2.2" strokeLinecap="round"/>
            <line x1="16" y1="32" x2="22" y2="32" stroke="#C9A84C" strokeWidth="1.5" strokeLinecap="round"/>
            <line x1="34" y1="32" x2="40" y2="32" stroke="#C9A84C" strokeWidth="1.5" strokeLinecap="round"/>
            <line x1="28" y1="19" x2="28" y2="25" stroke="#C9A84C" strokeWidth="1.5" strokeLinecap="round"/>
            <line x1="28" y1="39" x2="28" y2="45" stroke="#C9A84C" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          <div style={{
            fontFamily: '"Bebas Neue", "DM Sans", sans-serif',
            fontSize: 'clamp(28px, 4vw, 46px)',
            fontWeight: 400,
            letterSpacing: '0.12em',
            color: '#f8f6f0',
            textShadow: '0 0 40px rgba(45,140,64,0.5), 0 2px 20px rgba(0,0,0,0.8)',
            lineHeight: 1,
          }}>
            COACHLENZ
          </div>
          <div style={{
            fontFamily: '"DM Mono", monospace',
            fontSize: 'clamp(8px, 1vw, 11px)',
            letterSpacing: '0.3em',
            color: '#C9A84C',
            marginTop: 6,
            textTransform: 'uppercase',
          }}>
            AI Film Analyst OS
          </div>
        </div>

        {/* ── SKIP BUTTON ── */}
        <button
          onClick={() => { setExiting(true); setTimeout(() => setVisible(false), 500) }}
          style={{
            position: 'absolute', bottom: 28, right: 28,
            background: 'transparent',
            border: '1px solid rgba(255,255,255,0.15)',
            color: 'rgba(255,255,255,0.4)',
            fontFamily: '"DM Mono", monospace',
            fontSize: 10,
            letterSpacing: '0.2em',
            padding: '6px 14px',
            cursor: 'pointer',
            borderRadius: 2,
            zIndex: 1,
            transition: 'color 0.2s, border-color 0.2s',
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = '#C9A84C'; (e.currentTarget as HTMLElement).style.borderColor = 'rgba(201,168,76,0.4)' }}
          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = 'rgba(255,255,255,0.4)'; (e.currentTarget as HTMLElement).style.borderColor = 'rgba(255,255,255,0.15)' }}
        >
          SKIP INTRO
        </button>
      </div>
    </>
  )
}
