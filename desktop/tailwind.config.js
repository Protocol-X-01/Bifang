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
        // Bifang Brand Palette
        brand: {
          red: '#E63946',
          orange: '#FF8A3D',
          white: '#F7F7F7',
          slate: '#0F172A',
          'slate-light': '#1A2338',
          'slate-lighter': '#243048',
          success: '#22C55E',
          warning: '#F59E0B',
          info: '#3B82F6',
        },
        // Semantic aliases for theming
        bifang: {
          canvas: '#0F172A',
          surface: '#1A2338',
          'surface-hover': '#202B40',
          panel: '#151D30',
          'panel-hover': '#1C2642',
          border: '#2D3A50',
          'border-bright': '#3D4A68',
          divider: 'rgba(255, 255, 255, 0.06)',
        },
        // Text colors
        text: {
          primary: '#F7F7F7',
          secondary: '#B8C3D6',
          muted: '#9AA9BF',
          disabled: '#6B7A94',
          inverse: '#0F172A',
          link: '#FF8A3D',
          'link-hover': '#FFAE77',
        },
        // Surface/background
        surface: {
          background: '#0F172A',
          foreground: '#F7F7F7',
          card: '#1A2338',
          'card-foreground': '#F7F7F7',
          popover: '#151D30',
          'popover-foreground': '#F7F7F7',
        },
        // Primary (brand red)
        primary: {
          50: '#FEF0F0', 100: '#FDE0E2', 200: '#FBCCCF', 300: '#F8A8A8',
          400: '#F3797A', 500: '#E63946', 600: '#CC293B', 700: '#A61F2F',
          800: '#7D1723', 900: '#5C101A', DEFAULT: '#E63946',
        },
        // Accent (flame orange)
        accent: {
          50: '#FFF5F0', 100: '#FFE0CC', 200: '#FFC699', 300: '#FFA666',
          400: '#FF8A3D', 500: '#FF721A', 600: '#E65C14', 700: '#CC4610',
          800: '#B3330C', 900: '#8C2508', DEFAULT: '#FF8A3D',
        },
        // Neutral (slate)
        neutral: {
          50: '#F8FAFC', 100: '#F1F5F9', 200: '#E2E8F0', 300: '#CBD5E1',
          400: '#94A3B8', 500: '#64748B', 600: '#475569', 700: '#334155',
          800: '#1E293B', 900: '#0F172A', 950: '#08121E', DEFAULT: '#64748B',
        },
        // Semantic
        success: {
          base: '#22C55E', light: '#4ADE80', dark: '#16A34A',
          contrast: '#0F172A', bg: 'rgba(34, 197, 94, 0.1)', border: 'rgba(34, 197, 94, 0.3)'
        },
        warning: {
          base: '#F59E0B', light: '#FBBF24', dark: '#D97706',
          contrast: '#0F172A', bg: 'rgba(245, 158, 11, 0.1)', border: 'rgba(245, 158, 11, 0.3)'
        },
        error: {
          base: '#EF4444', light: '#F87171', dark: '#DC2626',
          contrast: '#F7F7F7', bg: 'rgba(239, 68, 68, 0.1)', border: 'rgba(239, 68, 68, 0.3)'
        },
        info: {
          base: '#3B82F6', light: '#60A5FA', dark: '#2563EB',
          contrast: '#F7F7F7', bg: 'rgba(59, 130, 246, 0.1)', border: 'rgba(59, 130, 246, 0.3)'
        },
        focus: { ring: '#FF8A3D', 'ring-offset': '#0F172A' },
        selection: { bg: 'rgba(230, 57, 70, 0.3)', text: '#F7F7F7' },
      },
      fontFamily: {
        display: ['Space Grotesk', 'Inter', 'system-ui', 'sans-serif'],
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Monaco', 'Consolas', 'monospace'],
        ui: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
      },
      fontSize: {
        'xs': ['11px', { lineHeight: '1.5', letterSpacing: '0.015em' }],
        'sm': ['12px', { lineHeight: '1.5', letterSpacing: '0' }],
        'base': ['13px', { lineHeight: '1.5', letterSpacing: '0' }],
        'lg': ['14px', { lineHeight: '1.5', letterSpacing: '0' }],
        'xl': ['16px', { lineHeight: '1.625', letterSpacing: '0' }],
        '2xl': ['20px', { lineHeight: '1.4', letterSpacing: '-0.015em' }],
        '3xl': ['25px', { lineHeight: '1.3', letterSpacing: '-0.015em' }],
        '4xl': ['32px', { lineHeight: '1.25', letterSpacing: '-0.015em' }],
        '5xl': ['40px', { lineHeight: '1.2', letterSpacing: '-0.02em' }],
        '6xl': ['50px', { lineHeight: '1.15', letterSpacing: '-0.02em' }],
        '7xl': ['64px', { lineHeight: '1.1', letterSpacing: '-0.03em' }],
      },
      fontWeight: {
        light: '300', normal: '400', medium: '500', semibold: '600', bold: '700', extrabold: '800',
      },
      lineHeight: {
        none: '1', tight: '1.15', snug: '1.25', normal: '1.5', relaxed: '1.625', loose: '1.75', code: '1.6',
      },
      letterSpacing: {
        tighter: '-0.03em', tight: '-0.015em', normal: '0',
        wide: '0.015em', wider: '0.03em', widest: '0.08em', display: '0.1em',
      },
      spacing: {
        '0': '0', '1': '2px', '2': '4px', '3': '6px', '4': '8px',
        '5': '10px', '6': '12px', '7': '14px', '8': '16px', '9': '18px',
        '10': '20px', '11': '22px', '12': '24px', '14': '28px', '16': '32px',
        '20': '40px', '24': '48px', '28': '56px', '32': '64px', '36': '72px',
        '40': '80px', '48': '96px', '56': '112px', '64': '128px',
      },
      borderRadius: {
        'none': '0', 'sm': '4px', DEFAULT: '8px', 'md': '10px', 'lg': '12px', 'xl': '16px', '2xl': '20px', 'full': '9999px',
      },
      borderWidth: {
        'none': '0', 'thin': '1px', DEFAULT: '1px', 'medium': '2px', 'thick': '3px',
      },
      boxShadow: {
        'none': 'none',
        'xs': '0 1px 2px rgba(0, 0, 0, 0.3)',
        'sm': '0 2px 4px rgba(0, 0, 0, 0.4), 0 1px 2px rgba(0, 0, 0, 0.3)',
        DEFAULT: '0 4px 8px rgba(0, 0, 0, 0.5), 0 2px 4px rgba(0, 0, 0, 0.3)',
        'md': '0 8px 16px rgba(0, 0, 0, 0.5), 0 4px 8px rgba(0, 0, 0, 0.3)',
        'lg': '0 16px 32px rgba(0, 0, 0, 0.6), 0 8px 16px rgba(0, 0, 0, 0.4)',
        'xl': '0 24px 48px rgba(0, 0, 0, 0.7), 0 12px 24px rgba(0, 0, 0, 0.5)',
        '2xl': '0 32px 64px rgba(0, 0, 0, 0.8)',
        'inner': 'inset 0 2px 4px rgba(0, 0, 0, 0.4)',
        'glow-red': '0 0 24px rgba(230, 57, 70, 0.4), 0 0 48px rgba(230, 57, 70, 0.2)',
        'glow-orange': '0 0 24px rgba(255, 138, 61, 0.4), 0 0 48px rgba(255, 138, 61, 0.2)',
        'glow-green': '0 0 24px rgba(34, 197, 94, 0.4), 0 0 48px rgba(34, 197, 94, 0.2)',
      },
      animation: {
        'fade-in': 'fadeIn 200ms cubic-bezier(0, 0, 0.2, 1)',
        'fade-out': 'fadeOut 150ms cubic-bezier(0.4, 0, 1, 1)',
        'slide-up': 'slideUp 300ms cubic-bezier(0, 0, 0.2, 1)',
        'slide-down': 'slideDown 300ms cubic-bezier(0, 0, 0.2, 1)',
        'slide-in-left': 'slideInLeft 300ms cubic-bezier(0, 0, 0.2, 1)',
        'slide-in-right': 'slideInRight 300ms cubic-bezier(0, 0, 0.2, 1)',
        'scale-in': 'scaleIn 200ms cubic-bezier(0.34, 1.56, 0.64, 1)',
        'scale-out': 'scaleOut 150ms cubic-bezier(0.4, 0, 1, 1)',
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
        'shimmer': 'shimmer 2s linear infinite',
        'spin-slow': 'spin 2s linear infinite',
      },
      keyframes: {
        fadeIn: { 'from': { opacity: '0' }, 'to': { opacity: '1' } },
        fadeOut: { 'from': { opacity: '1' }, 'to': { opacity: '0' } },
        slideUp: { 'from': { transform: 'translateY(8px)', opacity: '0' }, 'to': { transform: 'translateY(0)', opacity: '1' } },
        slideDown: { 'from': { transform: 'translateY(-8px)', opacity: '0' }, 'to': { transform: 'translateY(0)', opacity: '1' } },
        slideInLeft: { 'from': { transform: 'translateX(-16px)', opacity: '0' }, 'to': { transform: 'translateX(0)', opacity: '1' } },
        slideInRight: { 'from': { transform: 'translateX(16px)', opacity: '0' }, 'to': { transform: 'translateX(0)', opacity: '1' } },
        scaleIn: { 'from': { transform: 'scale(0.96)', opacity: '0' }, 'to': { transform: 'scale(1)', opacity: '1' } },
        scaleOut: { 'from': { transform: 'scale(1)', opacity: '1' }, 'to': { transform: 'scale(0.96)', opacity: '0' } },
        pulseGlow: { '0%, 100%': { boxShadow: '0 0 16px rgba(230, 57, 70, 0.3)' }, '50%': { boxShadow: '0 0 32px rgba(230, 57, 70, 0.5)' } },
        shimmer: { 'from': { backgroundPosition: '200% 0' }, 'to': { backgroundPosition: '-200% 0' } },
      },
      backgroundImage: {
        'gradient-ember': 'linear-gradient(135deg, #E63946 0%, #FF8A3D 100%)',
        'gradient-ember-reverse': 'linear-gradient(135deg, #FF8A3D 0%, #E63946 100%)',
        'gradient-surface': 'linear-gradient(135deg, #1A2338 0%, #0F172A 100%)',
        'gradient-verify': 'linear-gradient(90deg, #22C55E 0%, #16A34A 100%)',
        'grid-pattern': 'linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)',
      },
      backgroundSize: {
        'grid': '40px 40px',
      },
      transitionDuration: {
        'instant': '0ms', 'fast': '100ms', DEFAULT: '200ms', 'slow': '300ms', 'slower': '450ms', 'slowest': '700ms',
      },
      transitionTimingFunction: {
        'ease': 'cubic-bezier(0.25, 0.1, 0.25, 1)',
        'ease-out': 'cubic-bezier(0, 0, 0.2, 1)',
        'ease-in': 'cubic-bezier(0.4, 0, 1, 1)',
        'ease-in-out': 'cubic-bezier(0.4, 0, 0.2, 1)',
        'spring': 'cubic-bezier(0.34, 1.56, 0.64, 1)',
        'bounce': 'cubic-bezier(0.68, -0.55, 0.265, 1.55)',
      },
      zIndex: {
        base: '0', dropdown: '100', sticky: '200', overlay: '300',
        modal: '400', popover: '500', tooltip: '600', toast: '700', notification: '800',
      },
    },
  },
  plugins: [],
}