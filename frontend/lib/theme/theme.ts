/**
 * CoachLenz theme engine (mirrors the ProgramPilot / Prism setup).
 *
 * The app is painted from semantic CSS variables defined in two places:
 *   - app/globals.css  :root  (legacy Tailwind pages)
 *   - app/os.css       .clz   (the OS shell / modern surface)
 * Dark is the DEFAULT and stays byte-identical to the live site. Light is an
 * opt-in override selected by a `app-light` class on <body>. The accent picker
 * recolors the green highlight ramp in BOTH layers by injecting one <style> tag
 * (so it overrides both `:root{}` and `.clz{}` on equal specificity, cascade-last).
 *
 * Persistence is per-device via localStorage (no backend migration, zero DB risk).
 * A server-synced per-profile pref can be layered on later without changing this file.
 */

export type ThemeMode = 'light' | 'dark' | 'system'
export interface ThemePref { mode: ThemeMode; accent: string } // accent = preset key, a #hex, or 'default'

export const STORAGE_KEY = 'coachlenz.theme.v1'
export const ACCENT_STYLE_ID = 'clz-accent'
export const DEFAULT_PREF: ThemePref = { mode: 'dark', accent: 'default' }

export interface AccentPreset { key: string; label: string; base: string }
// `base` is the main highlight color (maps to --green3). '' = keep the designed ramp.
export const ACCENT_PRESETS: AccentPreset[] = [
  { key: 'default', label: 'Forest', base: '' },
  { key: 'emerald', label: 'Emerald', base: '#10b981' },
  { key: 'pine', label: 'Pine', base: '#2f8f4e' },
  { key: 'teal', label: 'Teal', base: '#14b8a6' },
  { key: 'lime', label: 'Lime', base: '#6aa519' },
  { key: 'gold', label: 'Gold', base: '#c9a84c' },
  { key: 'amber', label: 'Amber', base: '#d08a1e' },
  { key: 'crimson', label: 'Crimson', base: '#d33f3f' },
]
// The swatch shown for the 'default' (Forest) accent, purely for the menu UI.
export const DEFAULT_ACCENT_SWATCH = '#4a8525'

const HEX = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i

export function accentBase(accent: string): string {
  if (!accent || accent === 'default') return ''
  if (HEX.test(accent)) return accent
  return ACCENT_PRESETS.find((p) => p.key === accent)?.base || ''
}

/** CSS that recolors the green ramp from one base color, scoped to both token layers. */
export function accentCss(accent: string): string {
  const b = accentBase(accent)
  if (!b) return ''
  const ramp =
    `--green:color-mix(in srgb, ${b} 62%, #000);` +
    `--green2:color-mix(in srgb, ${b} 80%, #000);` +
    `--green3:${b};` +
    `--green4:color-mix(in srgb, ${b} 58%, #fff);` +
    `--greenl:color-mix(in srgb, ${b} 18%, transparent);` +
    `--greenl2:color-mix(in srgb, ${b} 8%, transparent);` +
    `--green-mid:color-mix(in srgb, ${b} 80%, #000);` +
    `--green-light:${b};`
  return `:root{${ramp}} .clz{${ramp}}`
}

export function resolveMode(mode: ThemeMode): 'light' | 'dark' {
  if (mode === 'system') {
    return typeof window !== 'undefined' &&
      window.matchMedia &&
      window.matchMedia('(prefers-color-scheme: light)').matches
      ? 'light'
      : 'dark'
  }
  return mode
}

export function applyTheme(pref: ThemePref): void {
  if (typeof document === 'undefined' || !document.body) return
  const resolved = resolveMode(pref.mode)
  const b = document.body
  b.classList.toggle('app-light', resolved === 'light')
  b.classList.toggle('app-dark', resolved === 'dark')

  const css = accentCss(pref.accent)
  let tag = document.getElementById(ACCENT_STYLE_ID) as HTMLStyleElement | null
  if (css) {
    if (!tag) {
      tag = document.createElement('style')
      tag.id = ACCENT_STYLE_ID
      document.head.appendChild(tag)
    }
    tag.textContent = css
  } else if (tag) {
    tag.textContent = ''
  }
}

export function readStoredPref(): ThemePref {
  if (typeof window === 'undefined') return DEFAULT_PREF
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_PREF
    const p = JSON.parse(raw)
    const mode: ThemeMode =
      p && (p.mode === 'light' || p.mode === 'dark' || p.mode === 'system') ? p.mode : 'dark'
    const accent = p && typeof p.accent === 'string' ? p.accent : 'default'
    return { mode, accent }
  } catch {
    return DEFAULT_PREF
  }
}

export function writeStoredPref(pref: ThemePref): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(pref))
  } catch {
    /* storage unavailable (private mode) — theme still works for this session */
  }
}

/**
 * Inline, render-blocking script placed first in <body>. Applies the stored theme
 * (class + accent) before paint so there is no dark/light flash. Mirrors the logic
 * above; kept dependency-free and tiny. The accent preset map MUST match ACCENT_PRESETS.
 */
export const NO_FLASH_SCRIPT = `(function(){try{
var K='${STORAGE_KEY}';var mode='dark',accent='default';
try{var r=localStorage.getItem(K);if(r){var j=JSON.parse(r);if(j){if(j.mode==='light'||j.mode==='dark'||j.mode==='system')mode=j.mode;if(typeof j.accent==='string')accent=j.accent;}}}catch(e){}
var res=mode;if(mode==='system'){res=(window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches)?'light':'dark';}
var b=document.body;b.classList.remove('app-light','app-dark');b.classList.add(res==='light'?'app-light':'app-dark');
var base='';if(accent&&accent!=='default'){if(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(accent)){base=accent;}else{var M={emerald:'#10b981',pine:'#2f8f4e',teal:'#14b8a6',lime:'#6aa519',gold:'#c9a84c',amber:'#d08a1e',crimson:'#d33f3f'};base=M[accent]||'';}}
if(base){var ramp='--green:color-mix(in srgb,'+base+' 62%,#000);--green2:color-mix(in srgb,'+base+' 80%,#000);--green3:'+base+';--green4:color-mix(in srgb,'+base+' 58%,#fff);--greenl:color-mix(in srgb,'+base+' 18%,transparent);--greenl2:color-mix(in srgb,'+base+' 8%,transparent);--green-mid:color-mix(in srgb,'+base+' 80%,#000);--green-light:'+base+';';var s=document.getElementById('${ACCENT_STYLE_ID}');if(!s){s=document.createElement('style');s.id='${ACCENT_STYLE_ID}';document.head.appendChild(s);}s.textContent=':root{'+ramp+'} .clz{'+ramp+'}';}
}catch(e){}})();`
