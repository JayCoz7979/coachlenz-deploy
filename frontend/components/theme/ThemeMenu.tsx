'use client'
import { useEffect, useRef, useState } from 'react'
import { useTheme } from './ThemeProvider'
import { ACCENT_PRESETS, DEFAULT_ACCENT_SWATCH, accentBase, type ThemeMode } from '@/lib/theme/theme'

// Small inline icons (no new dependency). Stroke follows currentColor.
function Icon({ d, children, size = 15 }: { d?: string; children?: React.ReactNode; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {d ? <path d={d} /> : children}
    </svg>
  )
}
const SunIcon = () => (
  <Icon>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </Icon>
)
const MoonIcon = () => <Icon d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
const MonitorIcon = () => (
  <Icon>
    <rect x="3" y="4" width="18" height="12" rx="2" />
    <path d="M8 20h8M12 16v4" />
  </Icon>
)

const MODES: { key: ThemeMode; label: string; icon: React.ReactNode }[] = [
  { key: 'light', label: 'Light', icon: <SunIcon /> },
  { key: 'dark', label: 'Dark', icon: <MoonIcon /> },
  { key: 'system', label: 'Auto', icon: <MonitorIcon /> },
]

export default function ThemeMenu() {
  const { mode, accent, resolved, setMode, setAccent } = useTheme()
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const customActive = !!accentBase(accent) && !ACCENT_PRESETS.some((p) => p.key === accent)
  const customValue = customActive ? accent : '#4a8525'

  const btn: React.CSSProperties = {
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
    width: 34, height: 34, borderRadius: 9, flexShrink: 0, cursor: 'pointer',
    border: '1px solid var(--border2)', background: 'var(--bg2)', color: 'var(--text2)',
    transition: '.12s',
  }
  const swatch = (bg: string, selected: boolean): React.CSSProperties => ({
    width: 26, height: 26, borderRadius: 7, cursor: 'pointer', background: bg,
    border: selected ? '2px solid var(--gold)' : '1px solid var(--border2)',
    boxShadow: selected ? '0 0 0 2px var(--goldl)' : 'none', transition: '.12s',
  })

  return (
    <div ref={wrapRef} style={{ position: 'relative', flexShrink: 0 }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={btn}
        aria-label="Theme settings"
        aria-haspopup="dialog"
        aria-expanded={open}
        title="Theme"
      >
        {resolved === 'light' ? <SunIcon /> : <MoonIcon />}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Theme settings"
          style={{
            position: 'absolute', right: 0, top: 'calc(100% + 8px)', zIndex: 200,
            width: 258, padding: 14, borderRadius: 12,
            background: 'var(--bg2)', border: '1px solid var(--border2)',
            boxShadow: '0 18px 50px rgba(0,0,0,.45)', color: 'var(--text)',
            fontFamily: 'var(--sans, inherit)',
          }}
        >
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 8 }}>
            Appearance
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6, marginBottom: 14 }}>
            {MODES.map((m) => {
              const active = mode === m.key
              return (
                <button
                  key={m.key}
                  type="button"
                  onClick={() => setMode(m.key)}
                  style={{
                    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
                    padding: '9px 4px', borderRadius: 9, cursor: 'pointer', fontSize: 11, fontWeight: 600,
                    border: active ? '1px solid var(--green3)' : '1px solid var(--border2)',
                    background: active ? 'var(--greenl)' : 'transparent',
                    color: active ? 'var(--green3)' : 'var(--text2)', transition: '.12s',
                  }}
                  aria-pressed={active}
                >
                  {m.icon}
                  {m.label}
                </button>
              )
            })}
          </div>

          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 8 }}>
            Accent color
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: 6, marginBottom: 12 }}>
            {ACCENT_PRESETS.map((p) => (
              <button
                key={p.key}
                type="button"
                onClick={() => setAccent(p.key)}
                style={swatch(p.base || DEFAULT_ACCENT_SWATCH, accent === p.key)}
                aria-label={p.label}
                title={p.label}
              />
            ))}
          </div>

          <label style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 12, cursor: 'pointer' }}>
            <span
              style={{
                width: 26, height: 26, borderRadius: 7, overflow: 'hidden', flexShrink: 0, position: 'relative',
                border: customActive ? '2px solid var(--gold)' : '1px solid var(--border2)',
                background: customActive ? customValue : 'transparent',
                display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text3)', fontSize: 14,
              }}
            >
              {!customActive && '+'}
              <input
                type="color"
                value={customValue}
                onChange={(e) => setAccent(e.target.value)}
                style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer', width: '100%', height: '100%' }}
                aria-label="Custom accent color"
              />
            </span>
            <span style={{ fontSize: 12, color: 'var(--text2)' }}>
              {customActive ? `Custom ${accent}` : 'Pick a custom color'}
            </span>
          </label>

          <button
            type="button"
            onClick={() => {
              setMode('dark')
              setAccent('default')
            }}
            style={{
              width: '100%', padding: '7px', borderRadius: 8, cursor: 'pointer', fontSize: 11, fontWeight: 600,
              border: '1px solid var(--border2)', background: 'transparent', color: 'var(--text2)', transition: '.12s',
            }}
          >
            Reset to CoachLenz default
          </button>
        </div>
      )}
    </div>
  )
}
