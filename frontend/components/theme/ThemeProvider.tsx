'use client'
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import {
  DEFAULT_PREF,
  applyTheme,
  readStoredPref,
  resolveMode,
  writeStoredPref,
  type ThemeMode,
  type ThemePref,
} from '@/lib/theme/theme'

interface ThemeCtx {
  mode: ThemeMode
  accent: string
  resolved: 'light' | 'dark'
  setMode: (m: ThemeMode) => void
  setAccent: (a: string) => void
}

const Ctx = createContext<ThemeCtx | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPref] = useState<ThemePref>(DEFAULT_PREF)
  const [resolved, setResolved] = useState<'light' | 'dark'>('dark')

  // Hydrate from storage after mount. The no-flash script already applied the
  // class pre-paint; this just syncs React state so the menu reflects it.
  useEffect(() => {
    const p = readStoredPref()
    setPref(p)
    applyTheme(p)
    setResolved(resolveMode(p.mode))
  }, [])

  // Track the OS preference while in system mode.
  useEffect(() => {
    if (pref.mode !== 'system' || typeof window === 'undefined' || !window.matchMedia) return
    const mq = window.matchMedia('(prefers-color-scheme: light)')
    const onChange = () => {
      applyTheme(pref)
      setResolved(resolveMode(pref.mode))
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [pref])

  const commit = useCallback((next: ThemePref) => {
    setPref(next)
    writeStoredPref(next)
    applyTheme(next)
    setResolved(resolveMode(next.mode))
  }, [])

  const setMode = useCallback((mode: ThemeMode) => commit({ ...pref, mode }), [pref, commit])
  const setAccent = useCallback((accent: string) => commit({ ...pref, accent }), [pref, commit])

  return (
    <Ctx.Provider value={{ mode: pref.mode, accent: pref.accent, resolved, setMode, setAccent }}>
      {children}
    </Ctx.Provider>
  )
}

export function useTheme(): ThemeCtx {
  const c = useContext(Ctx)
  // Safe fallback so a component rendered outside the provider never crashes.
  return c ?? { mode: 'dark', accent: 'default', resolved: 'dark', setMode: () => {}, setAccent: () => {} }
}
