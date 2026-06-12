import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['var(--font-syne)', 'sans-serif'],
        sans: ['var(--font-dm-sans)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-dm-mono)', 'monospace'],
      },
      colors: {
        bg: {
          1: '#07090d',
          2: '#0d1018',
          3: '#12161f',
          4: '#171d29',
          5: '#1c2333',
        },
        brand: {
          DEFAULT: '#4a8525',
          light: '#22c55e',
          mid: '#3a6b1e',
          dark: '#2d5016',
          400: '#22c55e',
          500: '#4a8525',
          600: '#3a6b1e',
        },
        gold: {
          DEFAULT: '#c9a84c',
          light: '#e8c96a',
          400: '#c9a84c',
          500: '#e8c96a',
        },
        cl: {
          text: '#edf0f8',
          text2: '#a8b8cc',
          text3: '#6a7d95',
        },
      },
    },
  },
  plugins: [],
}
export default config
