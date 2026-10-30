import { Sun, Moon, Monitor } from 'lucide-react';
import { useState } from 'react';

type Theme = 'light' | 'dark' | 'system';

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>('dark');

  const themes: { value: Theme; icon: typeof Sun; label: string }[] = [
    { value: 'light', icon: Sun, label: 'Light' },
    { value: 'dark', icon: Moon, label: 'Dark' },
    { value: 'system', icon: Monitor, label: 'System' }
  ];

  return (
    <div className="flex gap-1 bg-bifang-slate-panel rounded-lg p-1 border border-bifang-slate-border">
      {themes.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          onClick={() => setTheme(value)}
          className={`
            flex items-center justify-center w-8 h-8 rounded transition-all
            ${theme === value 
              ? 'bg-bifang-brand-orange text-bifang-brand-white shadow-sm' 
              : 'text-bifang-text-muted hover:text-bifang-text-primary hover:bg-bifang-slate-elevated'
            }
          `}
          aria-label={label}
          title={label}
        >
          <Icon className="w-4 h-4" />
        </button>
      ))}
    </div>
  );
}
