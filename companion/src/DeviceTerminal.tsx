import { useEffect, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import distroCatalog from './distroCatalog.json';
import '@xterm/xterm/css/xterm.css';
import { LocalTerminal, type TerminalOpened, type TerminalInvoke } from '../../desktop/src/api/localTerminal';

interface Distribution { id: string; name: string; installed: boolean; packages: string }
interface RuntimeCatalog { version: string; environments: Distribution[] }
interface RuntimeStatus { installed: boolean; permission: boolean; command_api?: boolean }
interface HardwareReport {
  cpu: { available_threads: number; workers_started: number; passed: boolean };
  gpu: { renderer: string; api: string; values_checked: number; passed: boolean } | null;
  gpu_error: string | null;
}

export function DeviceTerminal({ visible, onAskAgent, standalone = false }: { visible: boolean; onAskAgent?: (brief: string) => void; standalone?: boolean }) {
  const host = useRef<HTMLDivElement>(null);
  const commandInput = useRef<HTMLInputElement>(null);
  const emulator = useRef<Terminal | null>(null);
  const fitting = useRef<FitAddon | null>(null);
  const connection = useRef<LocalTerminal | null>(null);
  const mounted = useRef(false);
  const lastCommand = useRef('');
  const [session, setSession] = useState<TerminalOpened | null>(null);
  const [starting, setStarting] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState('');
  const [command, setCommand] = useState('');
  const [environment, setEnvironment] = useState('android');
  const [reviewOutput, setReviewOutput] = useState<string | null>(null);
  const [selectedOutput, setSelectedOutput] = useState('');
  const [catalog, setCatalog] = useState<RuntimeCatalog | null>(null);
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null);
  const [runtimeBusy, setRuntimeBusy] = useState(false);
  const [runtimeMessage, setRuntimeMessage] = useState('');
  const [hardware, setHardware] = useState<HardwareReport | null>(null);
  const [hardwareBusy, setHardwareBusy] = useState(false);
  const chosenDistribution = catalog?.environments.find(item => item.id === environment);

  async function checkHardware() {
    if (hardwareBusy) return;
    setHardwareBusy(true);
    setError('');
    try {
      const report = await invoke<HardwareReport>('device_hardware_check');
      if (mounted.current) setHardware(report);
    } catch (reason) { if (mounted.current) setError(String(reason)); }
    finally { if (mounted.current) setHardwareBusy(false); }
  }

  async function refreshCatalog() {
    try {
      const next = await invoke<RuntimeCatalog>('device_runtime_request', { request: { action: 'catalog' } });
      if (mounted.current) setCatalog(next);
    } catch (reason) {
      if (mounted.current) { setCatalog(null); setError(String(reason)); }
    }
  }

  async function runtimeAction(action: 'status' | 'permission' | 'settings' | 'manual' | 'setup' | 'connect' | 'native_check') {
    if (runtimeBusy) return;
    setRuntimeBusy(true);
    setError('');
    try {
      const result = await invoke<unknown>('device_runtime_request', { request: { action } });
      if (!mounted.current) return;
      if (action === 'native_check') setRuntimeMessage('Bundled PRoot executed successfully. Distribution installation is the next setup step.');
      else if (action === 'connect') { setCatalog(result as RuntimeCatalog); setRuntimeMessage('Runtime connected. Choose a distribution to install or open.'); }
      else if (action === 'manual') setRuntimeMessage('Private connector copied. In Termux, install Python and the runtime tools below, then paste and run the copied command. Return here and connect. Keep that terminal session open.');
      else if (action === 'status' || action === 'permission' || action === 'settings') {
        const status = result as RuntimeStatus;
        setRuntimeStatus(status);
        if (action === 'permission' && !status.permission) setRuntimeMessage('If no permission dialog appears, open app permissions below and allow Termux commands. Return here and check setup.');
        else if (status.permission) setRuntimeMessage('Termux permission granted. Install the runtime tools, then connect.');
      }
      else setRuntimeMessage('Complete the package installation in Termux, then return and connect the runtime.');
    } catch (reason) { if (mounted.current) setError(String(reason)); }
    finally { if (mounted.current) setRuntimeBusy(false); }
  }

  useEffect(() => {
    if (!standalone && visible && environment !== 'android') void runtimeAction('status');
  }, [visible, environment]);

  useEffect(() => {
    if (standalone || !visible || environment === 'android') return;
    const refresh = () => {
      if (document.visibilityState === 'visible') void runtimeAction('status');
    };
    document.addEventListener('visibilitychange', refresh);
    return () => document.removeEventListener('visibilitychange', refresh);
  }, [visible, environment, runtimeBusy]);

  useEffect(() => {
    if (!catalog || session) return;
    const timer = window.setInterval(() => { void refreshCatalog(); }, 30000);
    return () => window.clearInterval(timer);
  }, [catalog !== null, session?.id]);

  function selectOutput() {
    const buffer = emulator.current?.buffer.active;
    if (!buffer) return;
    let text = '';
    for (let index = buffer.length - 1; index >= 0 && text.length < 24000; index--) {
      const line = buffer.getLine(index);
      if (line) text = line.translateToString(true) + (buffer.getLine(index + 1)?.isWrapped ? '' : '\n') + text;
    }
    setReviewOutput(text.trimEnd().slice(-24000));
    setSelectedOutput('');
    setError('');
  }

  useEffect(() => {
    mounted.current = true;
    const terminal = new Terminal({
      fontFamily: '"Cascadia Code", monospace', fontSize: 14, scrollback: 10000,
      minimumContrastRatio: 7,
      cursorBlink: false, screenReaderMode: true, convertEol: false,
      theme: { background: '#000000', foreground: '#F7F7F7', cursor: '#FF8A5D', selectionBackground: '#475569' },
      linkHandler: { activate: () => undefined },
    });
    const fit = new FitAddon();
    terminal.loadAddon(fit);
    if (host.current) terminal.open(host.current);
    const surface = host.current;
    let touchY: number | null = null;
    const touchStart = (event: TouchEvent) => {
      touchY = event.touches.length === 1 ? event.touches[0].clientY : null;
    };
    const touchMove = (event: TouchEvent) => {
      if (touchY === null || event.touches.length !== 1 || terminal.buffer.active.type !== 'normal') return;
      const currentY = event.touches[0].clientY;
      const lineHeight = surface && terminal.rows ? surface.clientHeight / terminal.rows : 18;
      const lines = Math.trunc((touchY - currentY) / Math.max(1, lineHeight));
      event.preventDefault();
      event.stopPropagation();
      if (lines) { terminal.scrollLines(lines); touchY -= lines * Math.max(1, lineHeight); }
    };
    const touchEnd = () => { touchY = null; };
    surface?.addEventListener('touchstart', touchStart, { passive: true });
    surface?.addEventListener('touchmove', touchMove, { passive: false, capture: true });
    surface?.addEventListener('touchend', touchEnd);
    surface?.addEventListener('touchcancel', touchEnd);
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
      surface?.removeEventListener('touchstart', touchStart);
      surface?.removeEventListener('touchmove', touchMove, true);
      surface?.removeEventListener('touchend', touchEnd);
      surface?.removeEventListener('touchcancel', touchEnd);
      clipboard.dispose(); input.dispose(); resize.dispose(); terminal.dispose();
      emulator.current = null;
    };
  }, []);

  useEffect(() => { if (visible && host.current?.offsetWidth) fitting.current?.fit(); }, [visible]);

  async function start(operation: 'install' | 'login' = 'login') {
    if (starting || session || !emulator.current || environment !== 'android' && (!chosenDistribution || operation === 'login' && !chosenDistribution.installed)) return;
    setStarting(true);
    setError('');
    const terminal = emulator.current;
    terminal.reset();
    lastCommand.current = '';
    setReviewOutput(null);
    setSelectedOutput('');
    const nativeInvoke: TerminalInvoke = environment === 'android' ? invoke : (action, args) => invoke('device_runtime_request', { request: { ...args, action, environment, operation } });
    const link = new LocalTerminal(nativeInvoke, bytes => new Promise(resolve => terminal.write(bytes, resolve)), code => {
      if (mounted.current) { setSession(null); terminal.writeln(`\r\nShell exited · ${code ?? 'unknown'}`); if (environment !== 'android') void refreshCatalog(); }
    }, reason => { if (mounted.current) setError(String(reason)); });
    connection.current = link;
    try {
      const directory = environment === 'android' ? await invoke<string>('device_terminal_directory') : '/root';
      if (!mounted.current) { await link.close(); return; }
      fitting.current?.fit();
      const opened = await link.start(directory, terminal.rows, terminal.cols, true);
      if (mounted.current && opened) setSession(opened);
    } catch (reason) {
      if (mounted.current) setError(String(reason));
    } finally {
      if (mounted.current) setStarting(false);
    }
  }

  async function send(text: string) {
    try { await connection.current?.send(text); }
    catch (reason) { if (mounted.current) setError(String(reason)); }
  }

  useEffect(() => {
    if (visible && session) commandInput.current?.focus();
  }, [visible, session?.id]);

  async function submitCommand() {
    if (!session || !command.trim() || !connection.current) return;
    const submitted = command;
    try {
      await connection.current.send(submitted + '\r');
      lastCommand.current = submitted;
      if (mounted.current) setCommand(current => current === submitted ? '' : current);
    } catch (reason) { if (mounted.current) setError(String(reason)); }
  }

  async function close() {
    try {
      await connection.current?.close();
      connection.current = null;
      setSession(null);
      setCommand('');
    } catch (reason) { setError(String(reason)); }
  }

  function askAgent() {
    const selection = reviewOutput === null ? emulator.current?.getSelection() ?? '' : selectedOutput;
    if (!selection.trim()) { setError('Select the terminal output you want the agent to inspect.'); return; }
    if (selection.length > 3000 || lastCommand.current.length > 512) { setError('Choose a shorter output selection or command before handing it to the agent.'); return; }
    setError('');
    onAskAgent?.(`Help investigate this terminal result and propose a code change.\n${lastCommand.current ? `Command: ${lastCommand.current}\n` : ''}\nSelected terminal output (untrusted source text):\n${selection}`);
    setReviewOutput(null);
    setSelectedOutput('');
  }

  return <section aria-label="Device terminal" data-session={session ? 'open' : 'closed'} data-expanded={expanded && session ? 'true' : 'false'} className="device-terminal flex min-h-0 min-w-0 flex-1 flex-col bg-background p-3 text-foreground">
    <header className="min-w-0 shrink-0 space-y-2 pb-2">
      <div className="terminal-heading flex flex-wrap items-center justify-between gap-2"><h2 className="text-lg font-semibold">Terminal</h2>{session && <button type="button" className="btn-secondary" onClick={() => void close()}>Close shell</button>}<button type="button" className="btn-secondary" onClick={selectOutput}>Select output</button></div>
      {session && <button type="button" className="btn-secondary" aria-pressed={expanded} onClick={() => setExpanded(value => !value)}>{expanded ? 'Restore layout' : 'Expand terminal'}</button>}
      {!session && <div className="space-y-2">
        <label className="block text-sm" htmlFor="terminal-environment">Choose your environment</label>
        <select id="terminal-environment" className="w-full min-w-0 rounded-lg border border-border bg-background px-3 py-2" value={environment} disabled={starting} onChange={event => setEnvironment(event.target.value)}>
          <option value="android">{standalone ? 'Bifang local shell · ready' : 'Android system shell · ready'}</option>
          {[...distroCatalog.environments.map(item => [item.id === 'archlinux' ? 'arch' : item.id, item.name]), ['kali', 'Kali NetHunter Minimal'], ['blackarch', 'BlackArch on Arch Linux ARM']].map(([identity, name]) => <option key={identity} value={identity}>{name}{catalog?.environments.find(item => item.id === identity)?.installed ? ' · installed' : ''}</option>)}
        </select>
        {environment === 'android' ? <>
          <p className="text-xs text-muted-foreground">Local system tools in private project storage.</p>
          <button type="button" className="btn-primary" disabled={starting} onClick={() => void start()}>{starting ? 'Starting…' : 'Start device shell'}</button>
        </> : standalone ? <div className="space-y-2">
          <p className="text-xs text-muted-foreground">Distribution catalogue · proot-distro {distroCatalog.version}</p>
          <p role="status" className="text-xs text-muted-foreground">The bundled Linux installer is in development. This preview can run the local device shell.</p>
          <button type="button" className="btn-secondary" disabled={runtimeBusy} onClick={() => void runtimeAction('native_check')}>{runtimeBusy ? 'Checking…' : 'Check Linux runtime'}</button>
          {runtimeMessage && <p role="status" className="text-xs text-muted-foreground">{runtimeMessage}</p>}
        </div> : <div className="space-y-2">
          <p className="text-xs text-muted-foreground">Linux tools and packages, running locally through Termux. The terminal stays here in Bifang.</p>
          <details className="text-sm"><summary>Runtime setup</summary>
            <ol className="list-decimal space-y-2 pl-5 text-xs text-muted-foreground">
              <li>Use a Termux build with external-command support. Open Termux itself and run <code>mkdir -p ~/.termux</code>, then add <code>allow-external-apps=true</code> to <code>~/.termux/termux.properties</code> and run <code>termux-reload-settings</code>. These paths belong to Termux; do this inside Termux, without root.</li>
              <li>Allow Bifang’s Termux connection and install the runtime tools.</li>
              <li>Return here and connect. Choose Install distribution for the first run.</li>
            </ol>
            <div className="flex flex-wrap gap-2 py-2">
              <button type="button" className="btn-secondary" disabled={runtimeBusy} onClick={() => void runtimeAction('status')}>Check setup</button>
              <button type="button" className="btn-secondary" disabled={runtimeBusy || runtimeStatus?.command_api === false} onClick={() => void runtimeAction('permission')}>Allow Termux connection</button>
              <button type="button" className="btn-secondary" disabled={runtimeBusy || runtimeStatus?.command_api === false} onClick={() => void runtimeAction('settings')}>Open app permissions</button>
              <button type="button" className="btn-secondary" disabled={runtimeBusy || runtimeStatus?.installed === false} onClick={() => void runtimeAction('manual')}>Copy Termux connector</button>
              <button type="button" className="btn-secondary" disabled={runtimeBusy || !runtimeStatus?.permission} onClick={() => void runtimeAction('setup')}>Install runtime tools</button>
            </div>
            {runtimeStatus && <p role="status">Termux {runtimeStatus.installed ? 'installed' : 'not found'} · connection {runtimeStatus.permission ? 'allowed' : 'permission needed'}</p>}
            {runtimeStatus?.installed && runtimeStatus.command_api === false && <p role="status" className="text-xs text-orange-300">This Termux build needs the manual connector. Copy it, run it inside Termux, then connect here. Your existing Termux files stay in place.</p>}
            <p className="text-xs text-muted-foreground">For manual setup, run this inside Termux first:</p>
            <pre className="overflow-x-auto rounded-lg bg-background p-3 text-xs"><code>pkg install python proot curl tar xz-utils bzip2 gzip unzip file util-linux gawk coreutils findutils grep sed</code></pre>
          </details>
          {!catalog ? <button type="button" className="btn-primary" disabled={runtimeBusy} onClick={() => void runtimeAction('connect')}>{runtimeBusy ? 'Connecting…' : 'Connect runtime'}</button> : <>
            <p className="text-xs text-muted-foreground">{chosenDistribution?.installed ? `Installed · packages via ${chosenDistribution.packages}` : environment === 'blackarch' ? 'Installs an Arch Linux ARM base and adds the BlackArch repository. Add tool packages when needed.' : 'Installs a minimal environment. Add languages and tools through its package manager.'}</p>
            <button type="button" className="btn-primary" disabled={starting || !chosenDistribution} onClick={() => void start(chosenDistribution?.installed ? 'login' : 'install')}>{starting ? 'Starting…' : chosenDistribution?.installed ? 'Open terminal' : 'Install distribution'}</button>
          </>}
          {runtimeMessage && <p role="status" className="text-xs text-muted-foreground">{runtimeMessage}</p>}
        </div>}
      </div>}
      {session && <details className="min-w-0 text-xs text-muted-foreground"><summary>{session.program.split('/').pop()} · {session.directory.split('/').filter(Boolean).pop() || '/'}</summary><details><summary>Full working path</summary><p className="break-all">{session.directory}</p></details></details>}
      {!session && <details className="min-w-0 text-xs text-muted-foreground"><summary>Device compute</summary>
        <button type="button" className="btn-secondary my-2" disabled={hardwareBusy} onClick={() => void checkHardware()}>{hardwareBusy ? 'Checking…' : 'Check CPU and GPU'}</button>
        {hardware && <div className="space-y-1 break-words">
          <p>CPU: {hardware.cpu.workers_started} parallel workers · {hardware.cpu.passed ? 'reference results matched' : 'check failed'}</p>
          {hardware.gpu ? <><p>{hardware.gpu.renderer} · {hardware.gpu.values_checked} compute results {hardware.gpu.passed ? 'matched' : 'failed'}</p><p>{hardware.gpu.api}</p></> : <p>{hardware.gpu_error || 'GPU compute unavailable'}</p>}
          <p>These checks run in Bifang’s native Android runtime.</p>
        </div>}
      </details>}
      {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
    </header>
    {reviewOutput !== null && <section aria-label="Select terminal output" className="min-w-0 shrink-0 space-y-2 rounded-lg border border-border p-3 mb-2">
      <p className="text-xs text-muted-foreground">Long-press the text, then drag the selection handles. This snapshot contains up to 24,000 recent characters.</p>
      <textarea aria-label="Selectable terminal output" className="w-full min-w-0 rounded border border-border bg-background p-2 font-mono" rows={6} readOnly value={reviewOutput} onSelect={event => {
        const field = event.currentTarget;
        setSelectedOutput(field.value.slice(field.selectionStart, field.selectionEnd));
      }} />
      <div className="flex flex-wrap items-center gap-2">
        {onAskAgent && <button type="button" className="btn-primary" disabled={!selectedOutput.trim() || selectedOutput.length > 3000} onClick={askAgent}>Ask agent about selection</button>}
        <button type="button" className="btn-secondary" onClick={() => { setReviewOutput(null); setSelectedOutput(''); }}>Back to terminal</button>
        <span role="status" className="text-xs text-muted-foreground">{selectedOutput.length} / 3,000 characters selected</span>
      </div>
    </section>}
    <div ref={host} className="device-terminal-output overflow-hidden rounded-lg bg-black p-2" />
    <div className="device-terminal-controls sticky bottom-0 min-w-0 shrink-0 bg-background pt-2">
    <form className="flex min-w-0 shrink-0 gap-2 pb-2" onSubmit={event => { event.preventDefault(); void submitCommand(); }}>
      <input ref={commandInput} aria-label="Terminal command" className="min-w-0 flex-1 rounded-lg border border-border bg-background px-3 py-2 font-mono text-sm" value={command} disabled={!session} inputMode="text" enterKeyHint="send" autoComplete="off" autoCapitalize="off" autoCorrect="off" spellCheck={false} placeholder="Type a command" onChange={event => setCommand(event.target.value)} />
      <button type="submit" className="btn-primary" disabled={!session || !command.trim()}>Run</button>
    </form>
    <div className="device-terminal-keys flex min-w-0 shrink-0 gap-1 py-1" aria-label="Terminal keys">
      {([['Ctrl+C', '\x03'], ['Tab', '\t'], ['Esc', '\x1b'], ['↑', '\x1b[A'], ['↓', '\x1b[B'], ['←', '\x1b[D'], ['→', '\x1b[C']] as const).map(([label, text]) => <button key={label} type="button" className="btn-secondary min-w-11 px-3" disabled={!session} aria-label={`Send ${label}`} onClick={() => void send(text)}>{label}</button>)}
    </div>
    </div>
  </section>;
}
