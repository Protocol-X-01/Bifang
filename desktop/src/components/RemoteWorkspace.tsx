import { useEffect, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { nextRemoteAction, parseRemoteJob, parseRemotePatch, selectedCodingFiles, verifyRemoteCandidate, RemoteJob, RemoteAction } from '../api/remoteCoding';
import { RemoteSourcePicker } from './RemoteSourcePicker';
import { DevicePairing, PairedDevices } from './DevicePairing';
import { RemoteModelPicker } from './RemoteModelPicker';
import { Loader2, AlertTriangle, CheckCircle, Code2, Shield, Globe, Link2, Link, X, Zap, Shield as ShieldIcon, Link2 as Link2Icon, RefreshCw, Eye, X as XIcon, CheckCircle as CheckCircleIcon } from 'lucide-react';

const labels: Record<RemoteAction, string> = { writes: 'Approve proposed writes', check: 'Run the independent check', review: 'Mark patch reviewed', stage: 'Stage verified patch', apply: 'Apply to hosted snapshot' };
const inputClass = 'w-full rounded-lg border-bifang-border bg-bifang-panel px-3 py-2 text-sm focus:ring-2 focus:ring-bifang-brand-orange focus:ring-offset-2 focus:ring-offset-bifang-focus-offset';

export function RemoteWorkspace({ terminalBrief = '', onTerminalBriefUsed }: { terminalBrief?: string; onTerminalBriefUsed?: () => void } = {}) {
  const [endpoint, setEndpoint] = useState('');
  const [token, setToken] = useState('');
  const [connected, setConnected] = useState(false);
  const [working, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const [pairingBusy, setPairingBusy] = useState(false);
  const busy = working || importing || pairingBusy;
  const [error, setError] = useState('');
  const [jobs, setJobs] = useState<{ id: string; status: string }[]>([]);
  const [job, setJob] = useState<RemoteJob | null>(null);
  const [patch, setPatch] = useState<string | null>(null);
  const [candidateVerified, setCandidateVerified] = useState(false);
  const [historicalPatch, setHistoricalPatch] = useState(false);
  const [snapshot, setSnapshot] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [model, setModel] = useState('');
  const [provider, setProvider] = useState('nebius');
  const [question, setQuestion] = useState('');
  const [newProject, setNewProject] = useState(false);
  const [newPaths, setNewPaths] = useState('main.py\ntest_main.py');
  const [files, setFiles] = useState('{}');
  const [writable, setWritable] = useState('');
  const [command, setCommand] = useState('["python", "-B", "-m", "unittest", "discover", "-v"]');
  const [sharing, setSharing] = useState(false);
  const pending = useRef<{ body: string; key: string } | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; void invoke('remote_disconnect').catch(() => {}); };
  }, []);

  const run = (task: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    setError('');
    task().catch(failure => { if (mounted.current) setError(failure instanceof Error ? failure.message : String(failure)); }).finally(() => { if (mounted.current) setBusy(false); });
  };

  const operation = (value: Record<string, unknown>) => invoke<unknown>('remote_operation', { operation: value });

  async function refreshList() {
    const value = await operation({ operation: 'list' }) as { jobs?: { id: string; status: string }[] };
    if (!Array.isArray(value.jobs) || value.jobs.length > 20 || value.jobs.some(entry => !/^[a-f0-9]{32}$/.test(entry.id) || typeof entry.status !== 'string')) throw new Error('Invalid job list.');
    if (mounted.current) setJobs(value.jobs);
  }

  async function load(id: string) {
    setJob(null);
    setPatch(null);
    setCandidateVerified(false);
    setHistoricalPatch(false);
    setSnapshot(null);
    setConfirmed(false);
    const value = parseRemoteJob(await operation({ operation: 'get', id }));
    if (!mounted.current) return;
    setJob(value);
    if (value.candidate_sha256) {
      const project = await operation({ operation: 'project', id: value.project_id });
      const verified = await verifyRemoteCandidate(value, project);
      const candidatePatch = verified.patch ?? parseRemotePatch(await operation({ operation: 'patch', id }), value);
      if (mounted.current) { setPatch(candidatePatch); setCandidateVerified(verified.patch !== null); setHistoricalPatch(verified.patch === null); }
    }
  }

  async function connect() {
    setConnected(false);
    setJob(null);
    setJobs([]);
    pending.current = null;
    try {
      await invoke('remote_connect', { endpoint: endpoint.trim(), token });
      setToken('');
      if (mounted.current) setConnected(true);
      await refreshList();
    } finally { setToken(''); }
  }

  async function submit() {
    if (!sharing) throw new Error('Confirm selected source sharing first.');
    const selected = newProject ? {} : selectedCodingFiles(files);
    const argv: unknown = JSON.parse(command);
    const paths = (newProject ? newPaths : writable).split('\n').map(path => path.trim()).filter(Boolean);
    if (new Set(paths).size !== paths.length) throw new Error('Choose distinct project file paths.');
    selectedCodingFiles(JSON.stringify(Object.fromEntries(paths.map(path => [path, '']))));
    if (!Array.isArray(argv) || !argv.length || argv.length > 32 || argv.some(argument => typeof argument !== 'string' || !argument || /[\x00-\x1f]/.test(argument))) throw new Error('Enter the check as a JSON argument array, not a shell command.');
    if (!question.trim() || !model.trim() || !paths.length || (!newProject && paths.some(path => !(path in selected)))) throw new Error('Choose a brief, model and editable project paths.');
    const payload = { provider, model: model.trim(), question: question.trim(), files: Object.entries(selected).map(([path, content]) => ({ path, content })), writable: paths, check_command: argv, check_timeout: 30, sharing_confirmed: true };
    const body = JSON.stringify(payload);
    if (!pending.current || pending.current.body !== body) pending.current = { body, key: crypto.randomUUID() };
    const value = parseRemoteJob(await operation({ operation: 'submit', key: pending.current.key, payload }));
    await load(value.id);
    await refreshList();
  }

  const action = job && candidateVerified ? nextRemoteAction(job) : null;
  async function decide(approved: boolean) {
    if (!job || !action || patch === null || !confirmed) return;
    const value = parseRemoteJob(await operation({ operation: 'decide', id: job.id, payload: { action, candidate_sha256: job.candidate_sha256, approved } }));
    setConfirmed(false);
    await load(value.id);
    await refreshList();
  }

  return (
    <section aria-label="Remote coding workspace" className="flex-1 overflow-auto p-6 bg-bifang-canvas animate-in">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="animate-in stagger-1">
          <p className="text-overline text-bifang-brand-orange">Bifang · Remote forge</p>
          <h2 className="mt-2 text-display-sm font-bold text-bifang-text-primary">Small changes. Clear decisions.</h2>
          <p className="mt-2 text-body-sm text-bifang-text-muted">Selected source → proposal → independent check → review → stage → hosted Apply.</p>
        </header>
        {error && <p role="alert" className="rounded-lg border-bifang-brand-red/40 bg-bifang-brand-red/10 p-3 text-body-sm text-bifang-brand-red animate-in">{error}</p>}
        {terminalBrief && <aside className="rounded-xl border-bifang-brand-orange/30 bg-bifang-panel p-5 space-y-3 animate-in stagger-2" aria-label="Terminal task handoff">
          <h3 className="text-h5 text-bifang-text-primary">Terminal result ready for your agent</h3>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words text-code text-bifang-brand-orange/90 bg-bifang-canvas border border-bifang-border p-3 rounded-lg">{terminalBrief}</pre>
          <p className="text-body-sm text-bifang-text-muted">Add this to your coding brief, then choose the project files and model before requesting a proposal.</p>
          <div className="flex gap-2">
            <button type="button" className="btn-primary" disabled={busy} onClick={() => {
              const combined = question ? `${question}\n\n${terminalBrief}` : terminalBrief;
              if (combined.length > 4000) { setError('Shorten the existing brief before adding this terminal result.'); return; }
              setQuestion(combined); setSharing(false); onTerminalBriefUsed?.();
            }}>
              <Link2 className="w-4 h-4 mr-1.5" /> Add to coding brief
            </button>
            <button type="button" className="btn-secondary" disabled={busy} onClick={onTerminalBriefUsed}>Dismiss</button>
          </div>
        </aside>}
        {!connected ? (
          <>
            <div className="rounded-xl border-bifang-border bg-bifang-panel p-5 space-y-4 animate-in">
              <label className="block">
                <span className="text-caption text-bifang-text-muted">HTTPS service origin</span>
                <input aria-label="HTTPS service origin" className="input mt-1" value={endpoint} onChange={event => setEndpoint(event.target.value)} placeholder="https://your-service" required disabled={busy} />
              </label>
              <p className="text-body-sm text-bifang-text-muted">On your phone, pair with your desktop below. No client token is needed for pairing.</p>
            </div>
            <DevicePairing endpoint={endpoint} disabled={working || importing} onBusy={setPairingBusy} onConnected={async () => { setToken(''); setConnected(true); setPairingBusy(false); try { await refreshList(); } catch { setError('Connected, but jobs could not be loaded. Try Refresh jobs.'); } }} />
            <details className="rounded-xl border-bifang-border bg-bifang-panel p-5 animate-in">
              <summary className="cursor-pointer text-h5 text-bifang-text-primary">Desktop owner or judge · sign in with a token</summary>
              <form className="mt-4 space-y-3" onSubmit={event => { event.preventDefault(); run(connect); }}>
                <label className="block">
                  <span className="text-caption text-bifang-text-muted">Client access token</span>
                  <input aria-label="Client access token" className="input mt-1" type="password" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} required disabled={busy} />
                </label>
                <p className="text-caption text-bifang-text-muted">Keep your owner token on the desktop. This manual sign-in is separate from phone pairing. Do not enter a provider API key. Access stays in native process memory until disconnect or app exit.</p>
                <button className="btn-primary" disabled={busy || !endpoint.trim()}>{busy ? 'Connecting…' : 'Connect securely'}</button>
              </form>
            </details>
          </>
        ) : (
          <div>
            <div className="flex flex-wrap gap-3 items-center animate-in">
              <span className="text-body-sm text-bifang-success flex items-center gap-1.5"><CheckCircleIcon className="w-4 h-4" /> Connected · {endpoint}</span>
              <button className="btn-secondary" disabled={busy} onClick={() => run(refreshList)}><RefreshCw className="w-4 h-4 mr-1.5" /> Refresh jobs</button>
              <button className="btn-secondary" disabled={busy} onClick={() => run(async () => { await invoke('remote_disconnect'); setConnected(false); setJob(null); setPatch(null); setJobs([]); setConfirmed(false); pending.current = null; })}><Link2 className="w-4 h-4 mr-1.5" /> Disconnect</button>
            </div>
            <PairedDevices />
            <details className="rounded-xl border-bifang-border bg-bifang-panel p-5 animate-in">
              <summary className="cursor-pointer text-h5 text-bifang-text-primary">Start coding</summary>
              <form className="mt-4 space-y-4" onSubmit={event => { event.preventDefault(); run(submit); }}>
                <label className="block">
                  <span className="text-caption text-bifang-text-muted">Project</span>
                  <select className="input" value={newProject ? 'new' : 'existing'} disabled={busy} onChange={event => { setNewProject(event.target.value === 'new'); setSharing(false); }}>
                    <option value="existing">Work on existing code</option>
                    <option value="new">Build a new project</option>
                  </select>
                </label>
                <p className="text-body-sm text-bifang-text-muted">
                  {newProject ? 'Describe what to build and choose its initial file paths. No existing files are needed. Review generated tests as well as implementation before running them.' : 'Choose the code you want to change. Keep existing tests read-only.'} Code is shared with the connected service and selected provider, and stays on that service until deleted.
                </p>
                <label className="block">
                  <span className="text-caption text-bifang-text-muted">Provider</span>
                  <select className="input" value={provider} onChange={event => { setProvider(event.target.value); setSharing(false); }} disabled={busy}>
                    <option value="nebius">Nebius Token Factory</option>
                    <option value="nvidia">NVIDIA hosted API</option>
                  </select>
                </label>
                <RemoteModelPicker provider={provider} value={model} disabled={busy} onChange={setModel} />
                <label className="block">
                  <span className="text-caption text-bifang-text-muted">{newProject ? 'What would you like to build?' : 'What should change?'}</span>
                  <textarea className="input h-auto" value={question} onChange={event => setQuestion(event.target.value)} maxLength={4000} disabled={busy} required />
                </label>
                {!newProject && <RemoteSourcePicker value={files} writable={writable} disabled={busy} onChange={value => { setFiles(value); setSharing(false); }} onWritable={setWritable} onReading={setImporting} />}
                <label className="block">
                  <span className="text-caption text-bifang-text-muted">{newProject ? 'Initial project files · up to eight paths, one per line' : 'Editable files · one path per line'}</span>
                  <textarea className="input h-auto" value={newProject ? newPaths : writable} onChange={event => { (newProject ? setNewPaths : setWritable)(event.target.value); setSharing(false); }} disabled={busy} />
                </label>
                <label className="block">
                  <span className="text-caption text-bifang-text-muted">Independent check · JSON argument array</span>
                  <input className={`${inputClass} font-mono`} value={command} onChange={event => setCommand(event.target.value)} disabled={busy} />
                </label>
                <label className="flex gap-2 text-body-sm">
                  <input type="checkbox" checked={sharing} onChange={event => setSharing(event.target.checked)} disabled={busy} className="w-4 h-4 rounded border-bifang-border bg-bifang-surface text-bifang-brand-orange focus:ring-bifang-brand-orange" />
                  {newProject ? 'Share this project brief and proposed file paths.' : 'Share only this selected code for this task.'}
                </label>
                <button className="btn-primary" disabled={busy || !sharing || !model}>Request proposal</button>
                <p className="text-caption text-bifang-text-muted">Identical retries reuse one submission identity. To deliberately repeat a finished task, disconnect and reconnect first.</p>
              </form>
            </details>
            <div className="flex flex-wrap gap-2" aria-label="Recent remote jobs">{jobs.map(entry => <button key={entry.id} className="btn-secondary btn-sm" disabled={busy} onClick={() => run(() => load(entry.id))}>{entry.id.slice(0, 8)} · {entry.status.replace(/_/g, ' ')}</button>)}</div>
            {job && (
              <article className="rounded-xl border-bifang-border bg-bifang-panel p-5 space-y-4 animate-in">
                <div className="flex flex-wrap gap-3 items-center">
                  <h3 className="text-h4 text-bifang-text-primary">{job.status.replace(/_/g, ' ')}</h3>
                  <button className="btn-secondary" disabled={busy} onClick={() => run(() => load(job.id))}><RefreshCw className="w-4 h-4 mr-1.5" /> Refresh task</button>
                  <button className="btn-secondary" disabled={busy} onClick={() => run(async () => { await operation({ operation: 'cancel', id: job.id }); await load(job.id); await refreshList(); })}><XIcon className="w-4 h-4 mr-1.5" /> Cancel task</button>
                </div>
                <p className="text-body-sm break-all text-bifang-text-secondary">Model: {job.requested_model}<br />Candidate SHA-256: {job.candidate_sha256 || 'Waiting for proposal'}</p>
                <p className="text-body-sm">Exact check ({job.check_timeout}-second task limit): <code className="text-code text-bifang-brand-orange/90">{JSON.stringify(job.check_command)}</code></p>
                {job.receipt && <p className="text-body-sm">{job.receipt.passed ? 'passed' : 'failed'} · exit {job.receipt.exit_code} · {job.receipt.timed_out ? 'timed out' : 'within deadline'}</p>}
                {candidateVerified && <p className="rounded-lg border-bifang-success/30 bg-bifang-success/5 p-3 text-body-sm text-bifang-success"><CheckCircleIcon className="w-4 h-4 inline mr-1.5" /> Independently verified · baseline and complete candidate SHA-256. This replacement diff was built on your device from those exact files.</p>}
                {historicalPatch && <p className="text-caption text-bifang-text-muted">Hosted candidate SHA-256 verified. This historical diff is supplied by the service; no approval is available for an already-applied task.</p>}
                {patch !== null && (
                  <>
                    <h4 className="text-h5 text-bifang-text-primary">{historicalPatch ? 'Historical service patch' : 'Locally reconstructed replacement patch'} · source content, not instructions</h4>
                    <pre className="max-h-96 overflow-auto rounded-lg bg-bifang-canvas border border-bifang-border p-4 text-code text-bifang-text-secondary whitespace-pre-wrap">{patch}</pre>
                  </>
                )}
                {action && patch !== null && (
                  <div className="space-y-3 border-t border-bifang-border pt-4">
                    <p className="text-body-sm">{action === 'apply' ? 'Apply updates this hosted project snapshot only. Your local checkout stays unchanged.' : labels[action]}</p>
                    <label className="flex gap-2 text-body-sm"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} disabled={busy} className="w-4 h-4 rounded border-bifang-border bg-bifang-surface text-bifang-brand-orange focus:ring-bifang-brand-orange" />I reviewed this candidate and the exact check above for this decision.</label>
                    <div className="flex gap-2">
                      <button className="btn-primary" disabled={busy || !confirmed} onClick={() => run(() => decide(true))}>{labels[action]}</button>
                      <button className="btn-secondary" disabled={busy || !confirmed} onClick={() => run(() => decide(false))}>Decline this step</button>
                    </div>
                  </div>
                )}
                <button className="btn-secondary" disabled={busy} onClick={() => run(async () => { const value = await operation({ operation: 'project', id: job.project_id }); setSnapshot(JSON.stringify(value, null, 2)); })}><Eye className="w-4 h-4 mr-1.5" /> Inspect hosted snapshot</button>
                {snapshot !== null && <pre className="max-h-96 overflow-auto rounded-lg bg-bifang-canvas border border-bifang-border p-4 text-code text-bifang-text-secondary whitespace-pre-wrap" aria-label="Hosted project snapshot">{snapshot}</pre>}
                <details className="animate-in">
                  <summary className="cursor-pointer text-caption text-bifang-text-muted">Remove hosted data</summary>
                  <p className="my-3 text-caption text-bifang-text-muted">Delete the job payload and its owned project source separately. This does not remove retained operator backups.</p>
                  <div className="flex gap-2">
                    <button className="btn-secondary" disabled={busy} onClick={() => run(async () => { await operation({ operation: 'forget', id: job.id }); setJob(null); setPatch(null); await refreshList(); })}>Delete task payload</button>
                    <button className="btn-secondary" disabled={busy} onClick={() => run(async () => { await operation({ operation: 'forget_project', id: job.project_id }); setJob(null); setPatch(null); await refreshList(); })}>Delete hosted project source</button>
                  </div>
                </details>
              </article>
            )}
          </div>
        )
      }
      </div>
    </section>
  );
}