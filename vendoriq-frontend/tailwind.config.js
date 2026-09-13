/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // These token names are kept as-is (navy/saffron/slate) even though the
        // palette itself changed from a dark navy+amber theme to a light
        // green+white one, purely so every existing className across the app
        // (bg-navy-800, text-saffron-500, text-slate-text, etc.) keeps working
        // without having to touch every page. Each shade below resolves through
        // a CSS variable that flips value when the `dark` class is present on
        // <html> (see index.css), which is how light/dark mode actually works.
        navy: {
          950: 'rgb(var(--c-navy-950) / <alpha-value>)',
          900: 'rgb(var(--c-navy-900) / <alpha-value>)',
          800: 'rgb(var(--c-navy-800) / <alpha-value>)',
          700: 'rgb(var(--c-navy-700) / <alpha-value>)',
          600: 'rgb(var(--c-navy-600) / <alpha-value>)',
        },
        saffron: {
          400: 'rgb(var(--c-brand-400) / <alpha-value>)',
          500: 'rgb(var(--c-brand-500) / <alpha-value>)',
          600: 'rgb(var(--c-brand-600) / <alpha-value>)',
        },
        brand: {
          50: 'rgb(var(--c-brand-50) / <alpha-value>)',
          400: 'rgb(var(--c-brand-400) / <alpha-value>)',
          500: 'rgb(var(--c-brand-500) / <alpha-value>)',
          600: 'rgb(var(--c-brand-600) / <alpha-value>)',
          700: 'rgb(var(--c-brand-700) / <alpha-value>)',
        },
        slate: {
          text: 'rgb(var(--c-text) / <alpha-value>)',
          muted: 'rgb(var(--c-text-muted) / <alpha-value>)',
          dim: 'rgb(var(--c-text-dim) / <alpha-value>)',
        }
      },
      fontFamily: {
        mono: ['DM Mono', 'Courier New', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      keyframes: {
        'profit-pulse': {
          '0%, 100%': { textShadow: '0 0 8px rgba(30, 132, 73, 0.35)' },
          '50%': { textShadow: '0 0 20px rgba(30, 132, 73, 0.7), 0 0 40px rgba(30, 132, 73, 0.25)' },
        },
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in': {
          from: { transform: 'translateX(-100%)' },
          to: { transform: 'translateX(0)' },
        }
      },
      animation: {
        'profit-pulse': 'profit-pulse 2.5s ease-in-out infinite',
        'fade-in': 'fade-in 0.3s ease-out',
        'slide-in': 'slide-in 0.25s ease-out',
      }
    },
  },
  plugins: [],
}
