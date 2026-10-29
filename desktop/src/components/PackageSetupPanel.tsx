import { useEffect, useMemo, useRef, useState } from 'react';
import { Channel, invoke, isTauri } from '@tauri-apps/api/core';
import { SetupClient, type SetupPlan, type SetupReceipt, type SetupProfile } from '../api/setup';
import type { WorkbenchClient } from '../api/workbench';
import { useSessionStore } from '../stores/bifangStore';
import { Loader2, AlertTriangle, CheckCircle, Shield, Globe, Code2, Zap, X, Network } from 'lucide-react';

export function PackageSetupPanel({ client, workspace, disabled, onBusyChange }: {
  client: WorkbenchClient; workspace: string | null; disabled: boolean; onBusyChange: (busy: boolean) => void;
}) {
  const setup = useMemo(() => new SetupClient(invoke, () => new Channel<unknown>(),
    (path, network, profile, builds) => client.setupPlan(path, network, profile, builds)), [client]);
  const [profile, setProfile] = useState<SetupProfile>('javascript-npm');
  const [allowBuilds, setAllowBuilds] = useState(false);
  const [buildConfirmed, setBuildConfirmed] = useState(false);
  const agentBusy = useSessionStore(state => state.busy);
  const [plan, setPlan] = useState<SetupPlan | null>(null);
  const [receipt, setReceipt] = useState<SetupReceipt | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [running, setRunning] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [output, setOutput] = useState('');
  const [error, setError] = useState('');
  const dialog = useRef<HTMLDialogElement>(null);
  const generation = useRef(0);
  const active = useRef<ReturnType<SetupClient['start']> | null>(null);

  useEffect(() => {
    generation.current += 1;
    setPlan(null); setReceipt(null); setConfirmed(false); setOutput(''); setError(''); setReviewing(false);
    setAllowBuilds(false); setBuildConfirmed(false);
    dialog.current?.close();
    return () => {
      generation.current += 1;
      void active.current?.cancel().catch(() => undefined);
    };
  }, [workspace]);

  const review = async (network: boolean) => {
    if (!workspace || disabled || reviewing || running || useSessionStore.getState().busy || !isTauri()) return;
    const current = generation.current;
    setReviewing(true); setPlan(null); setConfirmed(false); setBuildConfirmed(false); setError('');
    try {
      const result = await setup.review(workspace, network, profile, allowBuilds);
      if (current !== generation.current) return;
      setPlan(result); dialog.current?.showModal();
    } catch {
      if (current === generation.current) setError('Check the selected profile, its lockfile, installed runtime and Linux Bubblewrap. Runtimes are not downloaded automatically during review.');
    } finally { if (current === generation.current) setReviewing(false); }
  };

  const install = async () => {
    if (!plan || !confirmed || (plan.allow_builds && !buildConfirmed) || running || disabled || useSessionStore.getState().busy) return;
    const current = generation.current, selected = plan;
    setRunning(true); setCancelling(false); setError(''); setReceipt(null); setOutput('');
    setPlan(null); setConfirmed(false); dialog.current?.close();
    useSessionStore.getState().setBusy(true); onBusyChange(true);
    try {
      const job = setup.start(selected, true, (_stream, text) => {
        if (current === generation.current) setOutput(previous => (previous + text).slice(-100_000));
      }, buildConfirmed);
      active.current = job;
      const result = await job.result;
      if (current === generation.current) setReceipt(result);
    } catch {
      if (current === generation.current) setError('The setup result could not be verified. Inspect the project and saved setup receipts before retrying; no automatic retry was made.');
    } finally {
      active.current = null;
      useSessionStore.getState().setBusy(false); onBusyChange(false);
      setRunning(false); setCancelling(false);
    }
  };

  const cancel = async () => {
    if (!active.current || cancelling) return;
    setCancelling(true);
    try { await active.current.cancel(); }
    catch { setCancelling(false); setError('Could not confirm cancellation. Wait for the final result or inspect saved receipts.'); }
  };

  return (
    <section aria-label="Project dependency setup" className="mt-6 rounded-2xl border-bifang-border bg-bifang-panel p-5 animate-in panel-hover">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <p className="text-overline text-bifang-brand-orange">Prepare your forge</p>
          <h3 className="mt-2 text-h4 text-bifang-text-primary">Dependency setup</h3>
        </div>
        <span className="rounded-full border-bifang-border px-3 py-1 text-caption text-bifang-text-secondary">Locked project setup · Linux</span>
      </div>
      <p className="mt-3 text-body-sm text-bifang-text-secondary">Choose a project profile and review its exact plan. Build code stays disabled unless you explicitly opt in.</p>

      <label className="mt-4 block text-caption text-bifang-text-muted">Setup language
        <select aria-label="Setup language" value={profile} disabled={running || reviewing || agentBusy || disabled}
          onChange={event => { setProfile(event.target.value as SetupProfile); setAllowBuilds(false); setBuildConfirmed(false); setConfirmed(false); setPlan(null); dialog.current?.close(); }}
          className="input input-sm ml-3 max-w-xs">
          <option value="javascript-npm">JavaScript / TypeScript · npm</option>
          <option value="python-uv">Python · uv</option>
          <option value="rust-cargo">Rust · Cargo</option>
        </select>
      </label>

      {profile !== 'javascript-npm' && (
        <label className="mt-3 flex gap-3 text-body-sm text-bifang-warning">
          <input type="checkbox" checked={allowBuilds} disabled={running || reviewing || agentBusy || disabled}
            onChange={event => { setAllowBuilds(event.target.checked); setBuildConfirmed(false); setPlan(null); setConfirmed(false); dialog.current?.close(); }} className="w-4 h-4 rounded border-bifang-border bg-bifang-surface text-bifang-brand-orange focus:ring-bifang-brand-orange" />
          {profile === 'python-uv' ? 'Include dependency build backends in the plan' : 'Include cargo check and project/dependency build code in the plan'}
        </label>
      )}

      {!isTauri() && <p className="mt-3 text-body-sm text-bifang-warning"><Network className="w-4 h-4 inline mr-1.5" />Installation runs in the latest native desktop build, not this browser preview.</p>}

      <div className="mt-4 flex flex-wrap gap-2">
        <button className="btn-secondary" disabled={!workspace || disabled || agentBusy || reviewing || running || !isTauri()} onClick={() => void review(false)}>
          <Shield className="w-4 h-4 mr-1.5" /> Review offline setup
        </button>
        <button className="btn-secondary" disabled={!workspace || disabled || agentBusy || reviewing || running || !isTauri()} onClick={() => void review(true)}>
          <Globe className="w-4 h-4 mr-1.5" /> Review network setup
        </button>
        {running && <button className="btn-secondary" disabled={cancelling} onClick={() => void cancel()}><X className="w-4 h-4 mr-1.5" />{cancelling ? 'Cancelling…' : 'Cancel installation'}</button>}
      </div>

      {(reviewing || running) && <p role="status" className="mt-3 text-body-sm text-bifang-brand-orange flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" />{reviewing ? 'Reading project setup…' : cancelling ? 'Waiting for cancellation and the exit receipt…' : 'Installing the approved plan…'}</p>}
      {error && <p role="alert" className="mt-3 text-body-sm text-bifang-brand-red animate-in">{error}</p>}

      {output && (
        <>
          <p className="mt-4 text-caption text-bifang-text-muted">Live output · last 100,000 characters · not a saved transcript</p>
          <pre aria-label="Dependency setup output" className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-xl bg-bifang-canvas border border-bifang-border p-4 text-code text-bifang-text-secondary">{output}</pre>
        </>
      )}

      {receipt && (
        <div className="mt-4 rounded-xl border-bifang-border bg-bifang-surface p-4 animate-in">
          <div className="flex items-center gap-2">
            <span className={`flex items-center gap-1.5 text-caption font-medium ${receipt.status === 'success' ? 'text-bifang-success' : 'text-bifang-brand-red'}`}>
              {receipt.status === 'success' ? <CheckCircle className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
              Setup {receipt.status}{receipt.returncode !== null ? ` · exit ${receipt.returncode}` : ''}
            </span>
          </div>
          <p className="mt-2 text-caption text-bifang-text-muted">{receipt.elapsed_seconds}s · {receipt.output_bytes} output bytes · {receipt.network}</p>
          <p className="mt-2 break-all text-caption text-bifang-brand-orange/80">Plan {receipt.plan_sha256}</p>
          {receipt.receipt_saved ? (
            <p className="mt-2 break-all text-caption text-bifang-text-muted">Receipt saved: {receipt.receipt_path}</p>
          ) : (
            <p role="alert" className="mt-2 text-body-sm text-bifang-warning">Receipt was not saved. Copy the result below before leaving.</p>
          )}
          <details className="mt-3">
            <summary className="cursor-pointer text-caption text-bifang-text-secondary">Inspect exit receipt</summary>
            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all text-code text-bifang-text-muted bg-bifang-canvas border border-bifang-border p-3 rounded-lg">{JSON.stringify(receipt, null, 2)}</pre>
          </details>
        </div>
      )}

      <dialog ref={dialog} aria-labelledby="setup-review-title" onCancel={() => { setPlan(null); setConfirmed(false); }} className="m-auto max-h-[90vh] w-[min(52rem,95vw)] overflow-y-auto rounded-2xl border-bifang-border bg-bifang-panel p-6 text-bifang-text-primary shadow-2xl glass-strong">
        {plan && (
          <>
            <h2 id="setup-review-title" className="text-h4 text-bifang-text-primary">Review dependency installation</h2>
            <p className="mt-3 break-all text-body-sm text-bifang-text-secondary">{plan.workspace}</p>
            <pre aria-label="Exact installer arguments" className="mt-3 overflow-x-auto rounded-xl bg-bifang-canvas border border-bifang-border p-4 text-code text-bifang-brand-orange/80">{JSON.stringify(plan.argv, null, 2)}</pre>
            <p className="mt-3 text-body-sm text-bifang-text-secondary">{plan.network === 'host-network' ? 'Network enabled: local and remote services are reachable.' : 'Offline: only already cached or local artifacts are available.'}</p>
            <p className="mt-3 text-body-sm text-bifang-text-muted">{plan.execution || 'npm lifecycle hooks are disabled.'}</p>
            <p className="mt-3 text-body-sm text-bifang-text-muted">Can write: {plan.writes.join('; ')}. Cancellation does not roll back partial changes.</p>
            {plan.environment_path && <p className="mt-3 break-all text-body-sm text-bifang-brand-orange/80">New Python environment: {plan.environment_path}. Existing .venv is left untouched.</p>}
            <p className="mt-3 break-all text-caption text-bifang-text-muted">Cache: {plan.cache_path}</p>
            <p className="mt-2 text-caption text-bifang-text-muted">Limit: {plan.timeout_seconds}s · {plan.output_limit_bytes} output bytes</p>
            <p className="mt-3 break-all text-caption text-bifang-brand-orange/80">SHA-256 {plan.sha256}</p>
            <details className="mt-3"><summary className="cursor-pointer text-caption text-bifang-text-secondary">Manifest fingerprints and runtime mounts</summary><pre className="mt-2 overflow-auto text-code text-bifang-text-muted bg-bifang-canvas border border-bifang-border p-3 rounded-lg">{JSON.stringify({ inputs: plan.inputs, runtime_mounts: plan.runtime_mounts, runtime_tools: plan.runtime_tools }, null, 2)}</pre></details>
            {plan.allow_builds && <label className="mt-5 flex gap-3 text-body-sm text-bifang-warning"><input type="checkbox" checked={buildConfirmed} onChange={event => setBuildConfirmed(event.target.checked)} className="w-4 h-4 rounded border-bifang-border bg-bifang-surface text-bifang-brand-orange focus:ring-bifang-brand-orange" />I separately authorize the build code described above to execute in this sandbox.</label>}
            <label className="mt-5 flex gap-3 text-body-sm"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} className="w-4 h-4 rounded border-bifang-border bg-bifang-surface text-bifang-brand-orange focus:ring-bifang-brand-orange" />I approve this exact plan, including its writes and network access.</label>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" autoFocus className="btn-secondary" onClick={() => { dialog.current?.close(); setPlan(null); setConfirmed(false); }}>Cancel</button>
              <button type="button" className="btn-primary" disabled={!confirmed || Boolean(plan.allow_builds && !buildConfirmed) || running || agentBusy || disabled} onClick={() => void install()}>Install approved plan</button>
            </div>
          </>
        )}
      </dialog>
    </section>
  );
}