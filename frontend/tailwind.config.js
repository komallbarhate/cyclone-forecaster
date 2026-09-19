/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Control room dark theme palette
        'cs-bg': '#0A0E1A',
        'cs-surface': '#0F1629',
        'cs-card': '#141D35',
        'cs-border': '#1E2D4A',
        'cs-accent': '#38BDF8',
        'cs-accent-dim': '#0EA5E9',
        'cs-danger': '#EF4444',
        'cs-warning': '#F59E0B',
        'cs-success': '#10B981',
        'cs-text': '#E2E8F0',
        'cs-muted': '#64748B',
        'cs-surge': '#F97316',
        'cs-rain': '#3B82F6',
        'cs-wind': '#A855F7',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      animation: {
        'pulse-danger': 'pulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'slide-in': 'slideIn 0.3s ease-out',
        'fade-in': 'fadeIn 0.2s ease-out',
      },
      keyframes: {
        slideIn: {
          '0%': { transform: 'translateX(20px)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
