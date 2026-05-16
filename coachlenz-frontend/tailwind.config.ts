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
        coachlenz: {
          bg: '#0d0d0d',
          card: '#161616',
          border: '#1e1e1e',
          blue: '#2563eb',
          'blue-hover': '#1d4ed8',
          'blue-light': '#3b82f6',
          muted: '#6b7280',
          text: '#e5e7eb',
          'text-dim': '#9ca3af',
        },
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
}

export default config
