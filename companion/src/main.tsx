import React from 'react';
import ReactDOM from 'react-dom/client';
import { RemoteWorkspace } from '../../desktop/src/components/RemoteWorkspace';
import { DeviceTerminal } from './DeviceTerminal';
import logo from '../../desktop/public/favicon.svg';
import './style.css';

const terminalEdition = (import.meta as ImportMeta & { env: Record<string, string> }).env.VITE_BIFANG_EDITION === 'terminal';

type ThemeChoice = 'system' | 'dark' | 'light';

function CompanionApp() {
  React.useEffect(() => {
    const update = () => document.documentElement.style.setProperty('--companion-height', `${Math.max(120, Math.floor(window.visualViewport?.height ?? window.innerHeight))}px`);
    update();
    window.addEventListener('resize', update);
    window.visualViewport?.addEventListener('resize', update);
    return () => {
      window.removeEventListener('resize', update);
      window.visualViewport?.removeEventListener('resize', update);
      document.documentElement.style.removeProperty('--companion-height');
    };
  }, []);
  const [theme, setTheme] = React.useState<ThemeChoice>(() => {
    const stored = window.localStorage.getItem('bifang-theme');
    return stored === 'dark' || stored === 'light' || stored === 'system' ? stored : 'system';
  });
  React.useEffect(() => {
    window.localStorage.setItem('bifang-theme', theme);
    const apply = () => {
      document.documentElement.dataset.theme = theme === 'system'
        ? (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark')
        : theme;
    };
    apply();
    const media = window.matchMedia('(prefers-color-scheme: light)');
    if (theme === 'system') {
      media.addEventListener('change', apply);
      return () => media.removeEventListener('change', apply);
    }
  }, [theme]);
  const [tab, setTab] = React.useState<'code' | 'terminal'>('terminal');
  const [terminalBrief, setTerminalBrief] = React.useState('');
  return (
    <main className="companion flex h-dvh min-w-0 flex-col overflow-hidden bg-background text-foreground">
      <header className="companion-header flex shrink-0 items-center gap-3 border-b border-border px-4 py-3">
        <img src={logo} className="h-8 w-8" alt="Bifang bird" />
        <div><h1 className="text-sm font-semibold">{terminalEdition ? 'Bifang Terminal' : 'Bifang Companion'}</h1><p className="text-xs text-muted-foreground">{terminalEdition ? 'A command line. A coding workspace.' : 'Your code, within reach.'}</p></div>
      </header>
      <nav className="companion-navigation flex shrink-0 gap-2 border-b border-border px-4 py-2" aria-label="Companion workspace">
        <button type="button" className={tab === 'code' ? 'btn-primary' : 'btn-secondary'} aria-pressed={tab === 'code'} onClick={() => setTab('code')}>Code</button>
        <button type="button" className={tab === 'terminal' ? 'btn-primary' : 'btn-secondary'} aria-pressed={tab === 'terminal'} onClick={() => setTab('terminal')}>Terminal</button>
      </nav>
      <div className={tab === 'code' ? 'flex min-h-0 min-w-0 flex-1' : 'hidden'}><RemoteWorkspace terminalBrief={terminalBrief} onTerminalBriefUsed={() => setTerminalBrief('')} /></div>
      <div className={tab === 'terminal' ? 'flex min-h-0 min-w-0 flex-1' : 'hidden'}><DeviceTerminal standalone={terminalEdition} visible={tab === 'terminal'} onAskAgent={brief => { setTerminalBrief(brief); setTab('code'); }} /></div>
      <footer className="companion-footer flex shrink-0 items-center justify-between gap-3 border-t border-border px-4 py-2 text-xs text-muted-foreground">
        <span>{tab === 'terminal' ? 'Terminal · on this device' : 'Coding · your connected service'}</span>
        <label htmlFor="companion-theme" className="flex shrink-0 items-center gap-2"><span>Theme</span>
          <select id="companion-theme" className="companion-theme-select" value={theme} onChange={event => setTheme(event.target.value as ThemeChoice)}>
            <option value="system">System</option>
            <option value="dark">Dark</option>
            <option value="light">Light</option>
          </select>
        </label>
      </footer>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><CompanionApp /></React.StrictMode>,
);
