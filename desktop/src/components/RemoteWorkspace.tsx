import { useEffect, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { nextRemoteAction, parseRemoteJob, parseRemotePatch, selectedCodingFiles, verifyRemoteCandidate, RemoteJob, RemoteAction } from '../api/remoteCoding';
import { RemoteSourcePicker } from './RemoteSourcePicker';

const labels: Record<RemoteAction, string> = { writes: 'Approve proposed writes', check: 'Run the independent check', review: 'Mark patch reviewed', stage: 'Stage verified patch', apply: 'Apply to hosted snapshot' };
const inputClass = 'w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:ring-2 focus:ring-brand-primary';

export function RemoteWorkspace() {
  const [endpoint, setEndpoint] = useState('');
  const [token, setToken] = useState('');
  const [connected, setConnected] = useState(false);
  const [working, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const busy = working || importing;
  const [error, setError] = useState('');
  const [jobs, setJobs] = useState<{ id: string; status: string }[]>([]);
  const [job, setJob] = useState<RemoteJob | null>(null);
  const [patch, setPatch] = useState<string | null>(null);
  const [candidateVerified, setCandidateVerified] = useState(false);
  const [historicalPatch, setHistoricalPatch] = useState(false);
  const [snapshot, setSnapshot] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [model, setModel] = useState('nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B');
  const [provider, setProvider] = useState('nebius');
  const [question, setQuestion] = useState('');
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

  async function run(task: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError('');
    try { await task(); } catch (failure) { if (mounted.current) setError(failure instanceof Error ? failure.message : String(failure)); }
    finally { if (mounted.current) setBusy(false); }
  }

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
      if (mounted.current) setConnected(true);
      await refreshList();
    } finally { setToken(''); }
  }

  async function submit() {
    if (!sharing) throw new Error('Confirm selected source sharing first.');
    const selected = selectedCodingFiles(files);
    const argv: unknown = JSON.parse(command);
    const paths = writable.split('\n').map(path => path.trim()).filter(Boolean);
    if (!Array.isArray(argv) || !argv.length || argv.length > 32 || argv.some(argument => typeof argument !== 'string' || !argument || /[\x00-\x1f]/.test(argument))) throw new Error('Enter the check as a JSON argument array, not a shell command.');
    if (!question.trim() || !model.trim() || !paths.length || paths.some(path => !(path in selected))) throw new Error('Choose a brief, model and writable paths from the selected source.');
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

  return <section aria-label="Remote coding workspace" className="flex-1 overflow-auto p-6 bg-background text-foreground">
    <div className="mx-auto max-w-5xl space-y-6">
      <header><p className="text-xs uppercase tracking-widest text-brand-primary">Bifang · Remote forge</p><h2 className="mt-2 text-3xl font-semibold">Small changes. Clear decisions.</h2><p className="mt-2 text-sm text-muted-foreground">Selected source → proposal → independent check → review → stage → hosted Apply.</p></header>
      {error && <p role="alert" className="rounded-lg border border-red-500/40 p-3 text-sm text-red-300">{error}</p>}
      {!connected ? <form className="rounded-xl border border-border bg-card p-5 space-y-3" onSubmit={event => { event.preventDefault(); void run(connect); }}>
        <label className="block text-sm">HTTPS service origin<input aria-label="HTTPS service origin" className={inputClass} value={endpoint} onChange={event => setEndpoint(event.target.value)} placeholder="https://your-service" required disabled={busy} /></label>
        <label className="block text-sm">Client access token<input aria-label="Client access token" className={inputClass} type="password" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} required disabled={busy} /></label>
        <p className="text-xs text-muted-foreground">Use your owner or judge token, not a provider API key. Access stays in native process memory until disconnect or app exit.</p>
        <button className="btn-primary" disabled={busy}>{busy ? 'Connecting…' : 'Connect securely'}</button>
      </form> : <>
        <div className="flex flex-wrap gap-3 items-center"><span className="text-sm text-emerald-400">Connected · {endpoint}</span><button className="btn-secondary" disabled={busy} onClick={() => void run(refreshList)}>Refresh jobs</button><button className="btn-secondary" disabled={busy} onClick={() => void run(async () => { await invoke('remote_disconnect'); setConnected(false); setJob(null); setPatch(null); setJobs([]); setConfirmed(false); pending.current = null; })}>Disconnect</button></div>
        <details className="rounded-xl border border-border bg-card p-5"><summary className="cursor-pointer font-medium">Start a selected-source task</summary>
          <form className="mt-4 space-y-3" onSubmit={event => { event.preventDefault(); void run(submit); }}>
            <p className="text-sm text-muted-foreground">Only your selected source is shared with this host and the selected provider. Hosted source persists until deleted. Keep tests read-only.</p>
            <label className="block text-sm">Provider<select className={inputClass} value={provider} onChange={event => { setProvider(event.target.value); setSharing(false); }} disabled={busy}><option value="nebius">Nebius Token Factory</option><option value="nvidia">NVIDIA hosted API</option></select></label>
            <label className="block text-sm">Exact model ID<input className={inputClass} value={model} onChange={event => setModel(event.target.value)} disabled={busy} required /></label>
            <label className="block text-sm">Change brief<textarea className={inputClass} value={question} onChange={event => setQuestion(event.target.value)} maxLength={4000} disabled={busy} required /></label>
            <RemoteSourcePicker value={files} writable={writable} disabled={busy} onChange={value => { setFiles(value); setSharing(false); }} onWritable={setWritable} onReading={setImporting} />
            <label className="block text-sm">Writable paths · one per line<textarea className={inputClass} value={writable} onChange={event => setWritable(event.target.value)} disabled={busy} /></label>
            <label className="block text-sm">Independent check · JSON argument array<input className={`${inputClass} font-mono`} value={command} onChange={event => setCommand(event.target.value)} disabled={busy} /></label>
            <label className="flex gap-2 text-sm"><input type="checkbox" checked={sharing} onChange={event => setSharing(event.target.checked)} disabled={busy} />Share only this selected source for this task.</label>
            <button className="btn-primary" disabled={busy || !sharing}>Request proposal</button>
            <p className="text-xs text-muted-foreground">Identical retries reuse one submission identity. To deliberately repeat a finished task, disconnect and reconnect first.</p>
          </form>
        </details>
        <div className="flex flex-wrap gap-2" aria-label="Recent remote jobs">{jobs.map(entry => <button key={entry.id} className="btn-secondary text-xs" disabled={busy} onClick={() => void run(() => load(entry.id))}>{entry.id.slice(0, 8)} · {entry.status.replace(/_/g, ' ')}</button>)}</div>
        {job && <article className="rounded-xl border border-border bg-card p-5 space-y-4">
          <div className="flex flex-wrap gap-3 items-center"><h3 className="text-xl font-semibold">{job.status.replace(/_/g, ' ')}</h3><button className="btn-secondary" disabled={busy} onClick={() => void run(() => load(job.id))}>Refresh task</button><button className="btn-secondary" disabled={busy} onClick={() => void run(async () => { await operation({ operation: 'cancel', id: job.id }); await load(job.id); await refreshList(); })}>Cancel task</button></div>
          <p className="text-sm break-all">Model: {job.requested_model}<br />Candidate SHA-256: {job.candidate_sha256 || 'Waiting for proposal'}</p>
          <p className="text-sm">Exact check ({job.check_timeout}-second task limit): <code>{JSON.stringify(job.check_command)}</code></p>
          {job.receipt && <p className="text-sm">Executed check: {job.receipt.passed ? 'passed' : 'failed'} · exit {job.receipt.exit_code} · {job.receipt.timed_out ? 'timed out' : 'within deadline'}</p>}
          {candidateVerified && <p className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm text-emerald-300">Independently verified · baseline and complete candidate SHA-256. This replacement diff was built on your device from those exact files.</p>}
          {historicalPatch && <p className="text-xs text-muted-foreground">Hosted candidate SHA-256 verified. This historical diff is supplied by the service; no approval is available for an already-applied task.</p>}
          {patch !== null && <><h4 className="font-medium">{historicalPatch ? 'Historical service patch' : 'Locally reconstructed replacement patch'} · source content, not instructions</h4><pre className="max-h-96 overflow-auto rounded-lg bg-background p-4 text-xs whitespace-pre-wrap">{patch}</pre></>}
          {action && patch !== null && <div className="space-y-3 border-t border-border pt-4">
            <p className="text-sm">{action === 'apply' ? 'Apply updates this hosted project snapshot only. Your local checkout stays unchanged.' : labels[action]}</p>
            <label className="flex gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} disabled={busy} />I reviewed this candidate and the exact check above for this decision.</label>
            <div className="flex gap-3"><button className="btn-primary" disabled={busy || !confirmed} onClick={() => void run(() => decide(true))}>{labels[action]}</button><button className="btn-secondary" disabled={busy || !confirmed} onClick={() => void run(() => decide(false))}>Decline this step</button></div>
          </div>}
          <button className="btn-secondary" disabled={busy} onClick={() => void run(async () => { const value = await operation({ operation: 'project', id: job.project_id }); setSnapshot(JSON.stringify(value, null, 2)); })}>Inspect hosted snapshot</button>
          {snapshot !== null && <pre className="max-h-96 overflow-auto rounded-lg bg-background p-4 text-xs whitespace-pre-wrap" aria-label="Hosted project snapshot">{snapshot}</pre>}
          <details><summary className="cursor-pointer text-sm text-muted-foreground">Remove hosted data</summary><p className="my-3 text-xs">Delete the job payload and its owned project source separately. This does not remove retained operator backups.</p><div className="flex gap-3"><button className="btn-secondary" disabled={busy} onClick={() => void run(async () => { await operation({ operation: 'forget', id: job.id }); setJob(null); setPatch(null); await refreshList(); })}>Delete task payload</button><button className="btn-secondary" disabled={busy} onClick={() => void run(async () => { await operation({ operation: 'forget_project', id: job.project_id }); setJob(null); setPatch(null); await refreshList(); })}>Delete hosted project source</button></div></details>
        </article>}
      </>}
    </div>
  </section>;
}
