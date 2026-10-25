import React from 'react';
import ReactDOM from 'react-dom/client';
import { RemoteWorkspace } from '../../desktop/src/components/RemoteWorkspace';
import logo from '../../desktop/public/favicon.svg';
import './style.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <main className="companion flex h-dvh flex-col overflow-hidden bg-background text-foreground">
      <header className="companion-header flex shrink-0 items-center gap-3 border-b border-border px-4 py-3">
        <img src={logo} className="h-8 w-8" alt="Bifang bird" />
        <div><h1 className="text-sm font-semibold">Bifang Companion</h1><p className="text-xs text-muted-foreground">Your forge, within reach.</p></div>
      </header>
      <RemoteWorkspace />
      <footer className="companion-footer shrink-0 border-t border-border px-4 py-2 text-xs text-muted-foreground">Session-only access · hosted snapshots</footer>
    </main>
  </React.StrictMode>,
);
