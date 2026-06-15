import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        green: {
          DEFAULT: '#1a5c2a',
          mid: '#236b32',
          light: '#2d8c40',
          400: '#2d8c40',
          500: '#1a5c2a',
          600: '#236b32',
        },
        gold: {
          DEFAULT: '#C9A84C',
          light: '#e2c06a',
          400: '#C9A84C',
          500: '#e2c06a',
        },
        charcoal: {
          DEFAULT: '#1c1c1c',
          mid: '#2e2e2e',
          light: '#3d3d3d',
        },
        brand: {
          DEFAULT: '#1a5c2a',
          mid: '#236b32',
          light: '#2d8c40',
          400: '#2d8c40',
          500: '#1a5c2a',
          600: '#236b32',
        },
        error: '#e07070',
      },
      fontFamily: {
        display: ['var(--font-bebas)', 'sans-serif'],
        sans: ['var(--font-dm-sans)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-dm-mono)', 'monospace'],
      },
      borderRadius: {
        none: '0',
        sm: '2px',
        DEFAULT: '4px',
        md: '4px',
        lg: '6px',
      },
    },
  },
  plugins: [],
}

export default config
