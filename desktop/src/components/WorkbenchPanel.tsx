import { useEffect, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { WorkbenchClient, type PluginListing, type PluginReview, type Toolchain } from '../api/workbench';
import { useSessionStore, useWorkspaceStore } from '../stores/bifangStore';
import { SystemMetricsPanel } from './SystemMetricsPanel';
import { PackageSetupPanel } from './PackageSetupPanel';

const client = new WorkbenchClient(invoke);

export function WorkbenchPanel({ onClose }: { onClose: () => void }) {
  const workspace = useWorkspaceStore(state => state.workspacePath);
  const agentBusy = useSessionStore(state => state.busy);
  const [catalog, setCatalog] = useState<PluginListing | null>(null);
  const [profiles, setProfiles] = useState<Toolchain[]>([]);
  const [reviewed, setReviewed] = useState<PluginReview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [pending, setPending] = useState(false);
  const [setupBusy, setSetupBusy] = useState(false);
  const [error, setError] = useState('');
  const generation = useRef(0);
  const dialog = useRef<HTMLDialogElement>(null);

  const load = async (path: string, current: number) => {
    const plugins = await client.list(path);
    const toolchains = await client.toolchains(path);
    if (current !== generation.current) return;
    setCatalog(plugins); setProfiles(toolchains);
  };
  useEffect(() => {
    const current = ++generation.current;
    setCatalog(null); setProfiles([]); setReviewed(null); setConfirmed(false); setError('');
    dialog.current?.close();
    if (!workspace) { setPending(false); return; }
    setPending(true);
    void load(workspace, current).catch(() => {
      if (current === generation.current) setError('Open the latest native desktop build to manage local plugins and language setup. If already open, refresh and check the selected project and plugin files.');
    }).finally(() => { if (current === generation.current) setPending(false); });
    return () => { generation.current += 1; };
  }, [workspace]);

  const perform = async (operation: (path: string, current: number) => Promise<void>) => {
    if (!workspace || pending || agentBusy || setupBusy) return;
    const current = generation.current;
    setPending(true); setError('');
    try { await operation(workspace, current); }
    catch { if (current === generation.current) { setConfirmed(false); setError('The operation could not be verified. Refresh and review the current plugin files before trying again.'); } }
    finally { if (current === generation.current) setPending(false); }
  };
  const review = (id: string) => perform(async (path, current) => {
    const result = await client.review(path, id);
    if (current !== generation.current) return;
    setReviewed(result); setConfirmed(false); dialog.current?.showModal();
  });
  const enable = () => perform(async (path, current) => {
    if (!reviewed || !confirmed) return;
    await client.trust(path, reviewed, confirmed);
    if (current !== generation.current) return;
    dialog.current?.close(); setReviewed(null); setConfirmed(false);
    await load(path, current);
  });

  return (
    <section aria-label="Developer workbench" className="flex-1 min-h-0 overflow-y-auto bg-bifang-canvas p-6 animate-in">
      <header className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <p className="text-overline text-bifang-brand-orange">Your forge, extended</p>
          <h2 className="mt-2 text-display-sm font-bold text-bifang-text-primary">Developer workbench</h2>
          <p className="mt-2 break-all text-body-sm text-bifang-text-muted">
            {workspace || 'Open or create a local workspace to begin.'}
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary" disabled={!workspace || pending || agentBusy || setupBusy} onClick={() => void perform(load)}>Refresh</button>
          <button className="btn-secondary" disabled={pending || setupBusy} onClick={onClose}>Back to editor</button>
        </div>
      </header>
      {pending && <p role="status" className="mb-4 text-body-sm text-bifang-text-muted animate-in">Checking local workbench…</p>}
      {error && <p role="alert" className="mb-4 rounded-lg border border-bifang-brand-red/30 bg-bifang-brand-red/10 p-3 text-body-sm text-bifang-brand-red animate-in">{error}</p>}
      {agentBusy && <p className="mb-4 text-body-sm text-bifang-text-muted">{setupBusy ? 'Dependency setup is running; other agent and plugin actions are paused.' : 'Plugin changes pause while the agent is working.'}</p>}
      <SystemMetricsPanel client={client} workspace={workspace} />
      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <section className="rounded-2xl border border-bifang-border bg-bifang-panel p-5 panel-hover animate-in stagger-1">
          <h3 className="text-h4 text-bifang-text-primary">Plugins</h3>
          <p className="mt-2 text-body-sm text-bifang-text-secondary">Review local extensions, then choose which code you trust.</p>
          {catalog && <p className="mt-3 text-caption text-bifang-text-muted">{catalog.execution}</p>}
          {catalog?.plugins.length === 0 && (
            <p className="mt-5 text-body-sm text-bifang-text-secondary">
              Add a Python plugin and its matching <code className="text-code">.plugin.json</code> manifest to <code className="text-code">.bifang/plugins</code> in this project, then refresh.
            </p>
          )}
          <div className="mt-4 space-y-3">
            {catalog?.plugins.map(plugin => (
              <article key={plugin.id} className="rounded-xl border border-bifang-border bg-bifang-surface p-4 panel-hover">
                <div className="flex items-center justify-between gap-3">
                  <h4 className="text-h5 text-bifang-text-primary">{plugin.name} <span className="text-caption text-bifang-text-muted">{plugin.version}</span></h4>
                  <span className={`text-caption ${plugin.trusted ? 'text-bifang-success' : 'text-bifang-warning'}`}>{plugin.state}</span>
                </div>
                <p className="mt-2 text-body-sm text-bifang-text-secondary">{plugin.description}</p>
                <p className="mt-2 break-all text-code text-bifang-text-muted">{plugin.source_path}</p>
                <div className="mt-3 flex gap-2">
                  <button className="btn-secondary" disabled={pending || agentBusy} onClick={() => void review(plugin.id)}>Review code</button>
                  {plugin.state !== 'disabled' && (
                    <button className="btn-secondary" disabled={pending || agentBusy} onClick={() => void perform(async (path, current) => { await client.disable(path, plugin.id); await load(path, current); })}>
                      Disable
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
          {catalog?.errors.map((item, index) => (
            <p key={index} className="mt-3 break-all text-body-sm text-bifang-warning">{item.error}: {item.path}</p>
          ))}
        </section>
        <section className="rounded-2xl border border-bifang-border bg-bifang-panel p-5 panel-hover animate-in stagger-2">
          <h3 className="text-h4 text-bifang-text-primary">Language setup</h3>
          <p className="mt-2 text-body-sm text-bifang-text-secondary">Manifest-aware bootstrap previews. Run selected commands yourself in the local terminal for now.</p>
          {catalog && profiles.length === 0 && (
            <p className="mt-5 text-body-sm text-bifang-text-secondary">
              No supported root manifests found. Python, JavaScript / TypeScript and Rust are detected here.
            </p>
          )}
          {profiles.map(profile => (
            <article key={profile.id} className="mt-4 rounded-xl border border-bifang-border bg-bifang-surface p-4 panel-hover">
              <h4 className="text-h5 text-bifang-text-primary">{profile.label}</h4>
              <p className="mt-2 text-caption text-bifang-text-muted">{profile.manifests.join(' · ')}</p>
              <p className="mt-2 text-body-sm text-bifang-text-secondary">
                {profile.manager}: {profile.available ? 'found on PATH' : 'not found on PATH'}
              </p>
              {profile.bootstrap_argv.length > 0 ? (
                <pre className="mt-3 overflow-x-auto rounded-lg bg-bifang-canvas border border-bifang-border p-3 text-code text-bifang-brand-orange/90">{profile.bootstrap_argv.join(' ')}</pre>
              ) : (
                <p className="mt-3 text-body-sm text-bifang-warning">Select the lockfile's package manager before installation.</p>
              )}
              <p className="mt-3 text-caption text-bifang-text-muted">
                Downloads dependencies{profile.may_execute_dependency_code ? ' and may execute dependency build code' : ''}. No installation runs from this panel.
              </p>
            </article>
          ))}
        </section>
      </div>
      <PackageSetupPanel client={client} workspace={workspace} disabled={pending} onBusyChange={setSetupBusy} />
      <dialog ref={dialog} aria-labelledby="plugin-review-title" onCancel={event => { if (pending) event.preventDefault(); else { setReviewed(null); setConfirmed(false); } }} className="m-auto max-h-[90vh] w-[min(56rem,95vw)] overflow-y-auto rounded-2xl border-bifang-border bg-bifang-panel p-6 text-bifang-text-primary shadow-2xl glass-strong">
        {reviewed && (
          <>
            <h2 id="plugin-review-title" className="text-h4 text-bifang-text-primary">Review {reviewed.name}</h2>
            <p className="mt-2 text-body-sm text-bifang-text-secondary">{reviewed.description}</p>
            <p className="mt-2 text-body-sm text-bifang-text-secondary">Declared capabilities: {reviewed.capabilities.join(', ') || 'none'}</p>
            <p className="mt-3 break-all text-caption text-bifang-text-muted">{reviewed.manifest_path}<br />{reviewed.source_path}</p>
            <p className="mt-3 break-all font-mono text-code text-bifang-brand-orange/80">SHA-256 {reviewed.sha256}</p>
            <pre aria-label="Plugin source code" className="mt-4 max-h-80 overflow-auto rounded-xl bg-bifang-canvas border border-bifang-border p-4 text-code text-bifang-text-secondary">{reviewed.source}</pre>
            <p className="mt-4 text-body-sm text-bifang-warning">{reviewed.execution}</p>
            <label className="mt-4 flex gap-3 text-body-sm">
              <input type="checkbox" checked={confirmed} disabled={pending || agentBusy} onChange={event => setConfirmed(event.target.checked)} className="w-4 h-4 rounded border-bifang-border bg-bifang-surface text-bifang-brand-red focus:ring-bifang-brand-orange" />
              <span>I reviewed this version and trust its code and dependencies with full host access.</span>
            </label>
            {error && <p role="alert" className="mt-3 text-body-sm text-bifang-brand-red">{error}</p>}
            <div className="mt-5 flex justify-end gap-3">
              <button autoFocus className="btn-secondary" disabled={pending} onClick={() => { dialog.current?.close(); setReviewed(null); setConfirmed(false); }}>Cancel</button>
              <button className="btn-primary" disabled={!confirmed || pending || agentBusy} onClick={() => void enable()}>Enable reviewed version</button>
            </div>
          </>
        )}
      </dialog>
    </section>
  );
}