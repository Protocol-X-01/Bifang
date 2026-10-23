/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: '#0F1728',
        foreground: '#F7F7F7',
        card: '#1A2338',
        'card-foreground': '#F7F7F7',
        popover: '#1A2338',
        'popover-foreground': '#F7F7F7',
        primary: '#E63946',
        'primary-foreground': '#F7F7F7',
        secondary: '#243048',
        'secondary-foreground': '#F7F7F7',
        muted: '#243048',
        'muted-foreground': '#A0A8B8',
        accent: '#243048',
        'accent-foreground': '#F7F7F7',
        destructive: '#EF4444',
        'destructive-foreground': '#F7F7F7',
        border: '#2D3A50',
        input: '#2D3A50',
        ring: '#E63946',
        surface: {
          50: '#F7F7F7',
          100: '#E2E8F0',
          300: '#CBD5E1',
          400: '#94A3B8',
          500: '#8493AC',
          700: '#334155',
          800: '#1E293B',
          900: '#162033',
          950: '#0F172A',
        },
        // Bifang Brand Palette (from brand spec)
        bifang: {
          500: '#E63946',
          600: '#CC293B',
          red: '#E63906',        // Bifang Red - Energy, focus
          orange: '#FF8A5D',     // Flame Orange - Action, creativity
          white: '#F7F7F7',      // Cloud White - Clarity, simplicity
          slate: '#0F1728',      // Deep Slate - Stability, depth (primary bg)
          'slate-light': '#1A2338',
          'slate-lighter': '#243048',
        },
        // Semantic aliases for easy theming
        brand: {
          primary: '#E63946',
          secondary: '#FF8A5D',
          background: '#0F1728',
          surface: '#1A2338',
          'surface-elevated': '#243048',
          text: '#F7F7F7',
          'text-muted': '#A0A8B8',
          border: '#2D3A50',
          'border-bright': '#3D4A68',
        },
        // Status colors
        status: {
          success: '#10B981',
          warning: '#F59E0B',
          error: '#EF4444',
          info: '#3B82F6',
          running: '#10B981',
          stopped: '#EF4444',
          starting: '#F59E0B',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        display: ['Space Grotesk', 'Inter', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        'xs': ['0.75rem', { lineHeight: '1.5' }],
        'sm': ['0.875rem', { lineHeight: '1.5' }],
        'base': ['1rem', { lineHeight: '1.6' }],
        'lg': ['1.125rem', { lineHeight: '1.6' }],
        'xl': ['1.25rem', { lineHeight: '1.5' }],
        '2xl': ['1.5rem', { lineHeight: '1.4' }],
        '3xl': ['1.875rem', { lineHeight: '1.3' }],
        '4xl': ['2.25rem', { lineHeight: '1.2' }],
      },
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
        '128': '32rem',
      },
      borderRadius: {
        'xl': '1rem',
        '2xl': '1.5rem',
        '3xl': '2rem',
      },
      boxShadow: {
        'glow': '0 0 20px rgba(230, 57, 6, 0.3)',
        'glow-orange': '0 0 20px rgba(255, 138, 93, 0.3)',
        'inner-glow': 'inset 0 0 20px rgba(230, 57, 6, 0.1)',
        'card': '0 4px 24px rgba(0, 0, 0, 0.4)',
        'card-hover': '0 8px 32px rgba(0, 0, 0, 0.5)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow': 'spin 2s linear infinite',
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-down': 'slideDown 0.3s ease-out',
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(-4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideDown: {
          '0%': { opacity: '0', transform: 'translateY(-10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseGlow: {
          '0%, 100%': { boxShadow: '0 0 20px rgba(230, 57, 6, 0.3)' },
          '50%': { boxShadow: '0 0 40px rgba(230, 57, 6, 0.5)' },
        },
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-conic': 'conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))',
        'brand-gradient': 'linear-gradient(135deg, #E63906 0%, #FF8A5D 100%)',
        'surface-gradient': 'linear-gradient(135deg, #1A2338 0%, #0F1728 100%)',
        'verify-gradient': 'linear-gradient(90deg, #10B981 0%, #059669 100%)',
      },
    },
  },
  plugins: [],
}
