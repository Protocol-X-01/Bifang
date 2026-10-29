// Bifang Design System - CSS Variables & Utilities
// Import this in your components for consistent theming

export const bifangTokens = {
  colors: {
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
    surface: {
      canvas: '#0F172A',
      elevated: '#1A2338',
      'elevated-hover': '#202B40',
      panel: '#151D30',
      'panel-hover': '#1C2642',
      border: '#2D3A50',
      'border-bright': '#3D4A68',
      divider: 'rgba(255, 255, 255, 0.06)',
    },
    text: {
      primary: '#F7F7F7',
      secondary: '#B8C3D6',
      muted: '#9AA9BF',
      disabled: '#6B7A94',
      inverse: '#0F172A',
      link: '#FF8A3D',
      'link-hover': '#FFAE77',
    },
    semantic: {
      success: { base: '#22C55E', light: '#4ADE80', dark: '#16A34A', bg: 'rgba(34, 197, 94, 0.1)', border: 'rgba(34, 197, 94, 0.3)' },
      warning: { base: '#F59E0B', light: '#FBBF24', dark: '#D97706', bg: 'rgba(245, 158, 11, 0.1)', border: 'rgba(245, 158, 11, 0.3)' },
      error: { base: '#EF4444', light: '#F87171', dark: '#DC2626', bg: 'rgba(239, 68, 68, 0.1)', border: 'rgba(239, 68, 68, 0.3)' },
      info: { base: '#3B82F6', light: '#60A5FA', dark: '#2563EB', bg: 'rgba(59, 130, 246, 0.1)', border: 'rgba(59, 130, 246, 0.3)' },
    },
    focus: { ring: '#FF8A3D', offset: '#0F172A' },
    selection: { bg: 'rgba(230, 57, 70, 0.3)', text: '#F7F7F7' },
  },

  typography: {
    fontFamily: {
      display: 'Space Grotesk, Inter, system-ui, sans-serif',
      sans: 'Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
      mono: 'JetBrains Mono, Fira Code, Monaco, Consolas, monospace',
    },
    fontSize: {
      xs: '11px', sm: '12px', base: '13px', lg: '14px',
      xl: '16px', '2xl': '20px', '3xl': '25px', '4xl': '32px',
      '5xl': '40px', '6xl': '50px', '7xl': '64px',
    },
    fontWeight: { light: 300, normal: 400, medium: 500, semibold: 600, bold: 700, extrabold: 800 },
    lineHeight: { none: 1, tight: 1.15, snug: 1.25, normal: 1.5, relaxed: 1.625, loose: 1.75, code: 1.6 },
    letterSpacing: { tighter: '-0.03em', tight: '-0.015em', normal: '0', wide: '0.015em', wider: '0.03em', widest: '0.08em', display: '0.1em' },
  },

  spacing: {
    0: '0', 1: '2px', 2: '4px', 3: '6px', 4: '8px',
    5: '10px', 6: '12px', 7: '14px', 8: '16px', 9: '18px',
    10: '20px', 11: '22px', 12: '24px', 14: '28px', 16: '32px',
    20: '40px', 24: '48px', 28: '56px', 32: '64px', 36: '72px',
    40: '80px', 48: '96px', 56: '112px', 64: '128px',
  },

  borderRadius: { none: '0', sm: '4px', DEFAULT: '8px', md: '10px', lg: '12px', xl: '16px', '2xl': '20px', full: '9999px' },
  borderWidth: { none: '0', thin: '1px', DEFAULT: '1px', medium: '2px', thick: '3px' },

  shadows: {
    none: 'none',
    xs: '0 1px 2px rgba(0, 0, 0, 0.3)',
    sm: '0 2px 4px rgba(0, 0, 0, 0.4), 0 1px 2px rgba(0, 0, 0, 0.3)',
    DEFAULT: '0 4px 8px rgba(0, 0, 0, 0.5), 0 2px 4px rgba(0, 0, 0, 0.3)',
    md: '0 8px 16px rgba(0, 0, 0, 0.5), 0 4px 8px rgba(0, 0, 0, 0.3)',
    lg: '0 16px 32px rgba(0, 0, 0, 0.6), 0 8px 16px rgba(0, 0, 0, 0.4)',
    xl: '0 24px 48px rgba(0, 0, 0, 0.7), 0 12px 24px rgba(0, 0, 0, 0.5)',
    '2xl': '0 32px 64px rgba(0, 0, 0, 0.8)',
    inner: 'inset 0 2px 4px rgba(0, 0, 0, 0.4)',
    'glow-red': '0 0 24px rgba(230, 57, 70, 0.4), 0 0 48px rgba(230, 57, 70, 0.2)',
    'glow-orange': '0 0 24px rgba(255, 138, 61, 0.4), 0 0 48px rgba(255, 138, 61, 0.2)',
    'glow-green': '0 0 24px rgba(34, 197, 94, 0.4), 0 0 48px rgba(34, 197, 94, 0.2)',
  },

  motion: {
    duration: { instant: '0ms', fast: '100ms', DEFAULT: '200ms', slow: '300ms', slower: '450ms', slowest: '700ms' },
    easing: {
      linear: 'linear',
      ease: 'cubic-bezier(0.25, 0.1, 0.25, 1)',
      easeOut: 'cubic-bezier(0, 0, 0.2, 1)',
      easeIn: 'cubic-bezier(0.4, 0, 1, 1)',
      easeInOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
      spring: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
      bounce: 'cubic-bezier(0.68, -0.55, 0.265, 1.55)',
    },
  },

  breakpoints: { xs: '480px', sm: '640px', md: '768px', lg: '1024px', xl: '1280px', '2xl': '1536px' },
  zIndex: { base: 0, dropdown: 100, sticky: 200, overlay: 300, modal: 400, popover: 500, tooltip: 600, toast: 700, notification: 800 },
} as const;

// Utility functions
export const cssVar = (path: string) => `var(--bifang-${path.replace(/\./g, '-')})`;

export const theme = {
  // Color helpers
  text: (variant: keyof typeof bifangTokens.colors.text = 'primary') => bifangTokens.colors.text[variant],
  surface: (variant: keyof typeof bifangTokens.colors.surface = 'canvas') => bifangTokens.colors.surface[variant],
  brand: (variant: keyof typeof bifangTokens.colors.brand) => bifangTokens.colors.brand[variant],
  semantic: (variant: keyof typeof bifangTokens.colors.semantic) => bifangTokens.colors.semantic[variant],

  // Typography helpers
  font: {
    display: bifangTokens.typography.fontFamily.display,
    sans: bifangTokens.typography.fontFamily.sans,
    mono: bifangTokens.typography.fontFamily.mono,
  },
  size: (variant: keyof typeof bifangTokens.typography.fontSize) => bifangTokens.typography.fontSize[variant],

  // Spacing helpers
  space: (variant: keyof typeof bifangTokens.spacing) => bifangTokens.spacing[variant],

  // Shadow helpers
  shadow: (variant: keyof typeof bifangTokens.shadows) => bifangTokens.shadows[variant],

  // Motion helpers
  transition: {
    fast: `${bifangTokens.motion.duration.fast} ${bifangTokens.motion.easing.easeOut}`,
    normal: `${bifangTokens.motion.duration.DEFAULT} ${bifangTokens.motion.easing.easeOut}`,
    slow: `${bifangTokens.motion.duration.slow} ${bifangTokens.motion.easing.easeOut}`,
    spring: `${bifangTokens.motion.duration.slow} ${bifangTokens.motion.easing.spring}`,
  },
};

// Component class names (for use with clsx/tailwind-merge)
export const components = {
  btn: 'inline-flex items-center justify-center gap-2 rounded-md font-semibold transition-all duration-200 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-bifang-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-bifang-focus-offset disabled:pointer-events-none disabled:opacity-40 disabled:cursor-not-allowed',
  btnPrimary: 'bg-gradient-to-r from-bifang-brand-red to-bifang-brand-orange text-bifang-brand-white hover:from-bifang-brand-red/90 hover:to-bifang-brand-orange/90 active:from-bifang-brand-red/80 active:to-bifang-brand-orange/80 shadow-lg shadow-bifang-brand-red/20',
  btnSecondary: 'bg-bifang-panel text-bifang-text-primary border border-bifang-border hover:bg-bifang-panel-hover hover:border-bifang-border-bright active:bg-bifang-surface',
  btnGhost: 'bg-transparent text-bifang-text-secondary hover:bg-bifang-surface hover:text-bifang-text-primary active:bg-bifang-panel',
  btnDestructive: 'bg-bifang-brand-red text-bifang-brand-white hover:bg-bifang-brand-red/90 active:bg-bifang-brand-red/80 shadow-lg shadow-bifang-brand-red/20',
  btnSuccess: 'bg-bifang-success text-bifang-text-inverse hover:bg-bifang-success/90 active:bg-bifang-success/80 shadow-lg shadow-bifang-success/20',
  input: 'flex w-full rounded-md border-bifang-border bg-bifang-panel px-3 py-2 text-sm text-bifang-text-primary placeholder-bifang-text-muted transition-all duration-200 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-bifang-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-bifang-focus-offset disabled:cursor-not-allowed disabled:opacity-50 disabled:bg-bifang-surface',
  panel: 'bg-bifang-panel border-bifang-border rounded-lg shadow-lg',
  panelElevated: 'bg-bifang-surface border-bifang-border-bright rounded-xl shadow-xl',
  sidebar: 'flex flex-col h-full w-64 bg-bifang-surface border-r border-bifang-border',
  card: 'bg-bifang-panel border-bifang-border rounded-xl shadow-lg p-4',
  glass: 'bg-bifang-panel/80 backdrop-blur-xl border-bifang-border/50',
  glassStrong: 'bg-bifang-surface/90 backdrop-blur-2xl border-bifang-border/30',
};

export default bifangTokens;