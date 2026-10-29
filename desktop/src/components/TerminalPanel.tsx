import { useEffect, useRef, useState } from 'react';
import { invoke, isTauri } from '@tauri-apps/api/core';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { LocalTerminal, type TerminalOpened } from '../api/localTerminal';
import { useWorkspaceStore } from '../stores/bifangStore';
import { Maximize2, Minimize2, X, Terminal as TerminalIcon, Zap } from 'lucide-react';

export function TerminalPanel({ visible, onHide, onActiveChange }: { visible: boolean; onHide: () => void; onActiveChange: (active: boolean) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const emulator = useRef<Terminal | null>(null);
  const fitting = useRef<FitAddon | null>(null);
  const connection = useRef<LocalTerminal | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const mounted = useRef(false);
  const [session, setSession] = useState<TerminalOpened | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');
  const path = useWorkspaceStore(state => state.workspacePath);

  useEffect(() => {
    mounted.current = true;
    const terminal = new Terminal({
      fontFamily: '"JetBrains Mono", "Cascadia Code", "SFMono-Regular", Consolas, monospace',
      fontSize: 13,
      cursorBlink: false,
      screenReaderMode: true,
      scrollback: 5000,
      theme: {
        background: '#0F172A',
        foreground: '#F7F7F7',
        cursor: '#FF8A3D',
        cursorAccent: '#0F172A',
        selectionBackground: 'rgba(230, 57, 70, 0.3)',
        black: '#1E293B',
        red: '#F87171',
        green: '#4ADE80',
        yellow: '#FBBF24',
        blue: '#60A5FA',
        magenta: '#F472B6',
        cyan: '#22D3EE',
        white: '#E2E8F0',
        brightBlack: '#475569',
        brightRed: '#FCA5A5',
        brightGreen: '#86EFAC',
        brightYellow: '#FDE047',
        brightBlue: '#93C5FD',
        brightMagenta: '#F9A8D4',
        brightCyan: '#67E8F9',
        brightWhite: '#F8FAFC',
      },
      linkHandler: { activate: () => undefined },
      allowProposedApi: true,
    });
    const fit = new FitAddon();
    terminal.loadAddon(fit);
    if (host.current) terminal.open(host.current);
    const clipboard = terminal.parser.registerOscHandler(52, () => true);
    const input = terminal.onData(text => {
      void connection.current?.send(text).catch(reason => { if (mounted.current) setError(String(reason)); });
    });
    const resize = terminal.onResize(size => {
      void connection.current?.resize(size.rows, size.cols).catch(reason => { if (mounted.current) setError(String(reason)); });
    });
    const observer = new ResizeObserver(() => { if (host.current?.offsetWidth) fit.fit(); });
    if (host.current) observer.observe(host.current);
    emulator.current = terminal;
    fitting.current = fit;
    return () => {
      mounted.current = false;
      void connection.current?.close().catch(() => undefined);
      connection.current = null;
      observer.disconnect();
      clipboard.dispose(); input.dispose(); resize.dispose(); terminal.dispose();
      emulator.current = null;
    };
  }, []);

  useEffect(() => { if (visible && host.current?.offsetWidth) fitting.current?.fit(); }, [visible]);

  const start = async () => {
    if (!path || starting || !emulator.current) return;
    if (!isTauri()) { setError('Open the Bifang desktop application to use a local terminal.'); return; }
    setStarting(true); setError(''); dialog.current?.close();
    const terminal = emulator.current;
    terminal.reset();
    const link = new LocalTerminal(invoke, bytes => new Promise(resolve => terminal.write(bytes, resolve)), code => {
      if (!mounted.current) return;
      terminal.writeln(`\r\n\x1b[38;5;240mShell exited · ${code ?? 'unknown status'}\x1b[0m`);
      setSession(null);
      onActiveChange(false);
    }, reason => { if (mounted.current) setError(String(reason)); });
    connection.current = link;
    try {
      const opened = await link.start(path, terminal.rows, terminal.cols, true);
      if (mounted.current && opened) { setSession(opened); onActiveChange(true); terminal.focus(); }
    } catch (reason) {
      if (mounted.current) setError(String(reason));
    } finally {
      if (mounted.current) setStarting(false);
    }
  };

  const close = async () => {
    setError('');
    try {
      await connection.current?.close();
      connection.current = null;
      setSession(null);
      onActiveChange(false);
      emulator.current?.writeln('\r\n\x1b[38;5;240mLocal terminal closed.\x1b[0m');
    } catch (reason) { setError(String(reason)); }
  };

  return (
    <section aria-label="Local machine terminal" className={visible ? 'flex h-[30%] max-h-72 min-h-0 shrink-0 flex-col overflow-hidden border-t border-bifang-border bg-bifang-canvas animate-in slide-up' : 'hidden'}>
      <dialog ref={dialog} aria-labelledby="terminal-consent-title" className="m-auto max-w-lg rounded-2xl border-bifang-border bg-bifang-panel p-6 text-bifang-text-primary shadow-2xl glass-strong">
        <div className="flex items-center gap-2 mb-4">
          <div className="p-1.5 rounded-lg bg-gradient-to-r from-bifang-brand-red to-bifang-brand-orange">
            <TerminalIcon className="w-5 h-5 text-bifang-brand-white" />
          </div>
          <h2 id="terminal-consent-title" className="text-h4 text-bifang-text-primary">Your local terminal</h2>
        </div>
        <p className="text-body-sm text-bifang-text-secondary mb-4">You control this shell. It can change files and access your computer and network. It is separate from the agent's offline command sandbox.</p>
        <p className="mb-3 break-all text-caption font-mono text-bifang-brand-orange/80 bg-bifang-surface border border-bifang-border px-2 py-1.5 rounded">{path}</p>
        <p className="text-caption text-bifang-text-muted mb-4">Startup profiles are skipped. API-key environment variables are not inherited. Terminal output is not sent to the model or saved in chat.</p>
        <div className="flex justify-end gap-3">
          <button autoFocus className="btn-secondary" onClick={() => dialog.current?.close()}>Cancel</button>
          <button className="btn-primary" onClick={() => void start()} disabled={starting}>{starting ? 'Starting…' : 'Start local shell'}</button>
        </div>
      </dialog>

      <header className="flex items-center gap-3 border-b border-bifang-border px-4 py-2.5 text-caption bg-bifang-panel/50 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <div className="p-1 rounded bg-gradient-to-r from-bifang-brand-red to-bifang-brand-orange">
            <TerminalIcon className="w-4 h-4 text-bifang-brand-white" />
          </div>
          <span className="text-overline text-bifang-brand-orange">Workbench · Terminal</span>
        </div>
        <span className="min-w-0 flex-1 truncate text-bifang-text-muted" title={session?.directory}>
          {session ? `${session.program} · ${session.directory}` : 'Your machine · explicit start'}
        </span>
        {session ? (
          <button className="btn-secondary" onClick={() => void close()}><X className="w-3.5 h-3.5 mr-1.5" /><span>Close shell</span></button>
        ) : (
          <button className="btn-primary" disabled={!path || starting} onClick={() => dialog.current?.showModal()}>{starting ? 'Starting…' : 'Open local terminal'}</button>
        )}
        <button className="btn-ghost" onClick={onHide} aria-label="Hide terminal panel"><X className="w-4 h-4" /></button>
      </header>
      {error && <p role="alert" className="px-4 py-1.5 text-caption text-bifang-brand-red bg-bifang-brand-red/10 border-b border-bifang-brand-red/20">{error}</p>}
      {!session && <p className="px-4 pt-2 text-caption text-bifang-text-muted">{path ? 'Open a shell when you need it. Run btop here if installed; nothing is installed automatically.' : 'Select a workspace before opening a shell.'}</p>}
      <div ref={host} className="min-h-0 flex-1 px-3 py-2" />
    </section>
  );
}