/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Terminal palette: deep neutral surfaces, one accent, semantic P&L
        // colours that stay distinguishable for red/green colour blindness
        // (profit leans teal-green, loss leans orange-red).
        base: {
          900: '#0a0c10',
          850: '#0e1117',
          800: '#131720',
          750: '#181d28',
          700: '#1e2430',
          600: '#2a3140',
          500: '#3a4254',
        },
        ink: {
          DEFAULT: '#e6e9ef',
          muted: '#99a2b3',
          faint: '#6b7585',
        },
        accent: {
          DEFAULT: '#4c8dff',
          soft: '#1d2d4d',
          dim: '#2f5fa8',
        },
        profit: { DEFAULT: '#2ebd85', soft: '#11311f' },
        loss: { DEFAULT: '#f6465d', soft: '#3a1620' },
        warn: { DEFAULT: '#f0b90b', soft: '#3a2f08' },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'Menlo', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      boxShadow: {
        panel: '0 1px 2px rgba(0,0,0,.4), 0 0 0 1px rgba(255,255,255,.04)',
      },
    },
  },
  plugins: [],
}
