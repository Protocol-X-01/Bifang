import { useRef, useState, useEffect } from 'react';
import { createWorkspace, resolveWorkspace, nativeWorkspace, workspaceDirectories } from '../api/workspaces';
import { open } from '@tauri-apps/plugin-dialog';
import { FolderOpen, FolderPlus, Play, Square, ChevronLeft, ChevronRight, Sparkles, Zap, ShieldCheck } from 'lucide-react';
import { useSessionStore, useWorkspaceStore } from '../stores/bifangStore';
import { version } from '../../package.json';

interface SidebarProps {
  serverStatus: 'starting' | 'running' | 'stopped';
  onStartServer: () => void;
  onStopServer: () => void;
}

export function Sidebar({ serverStatus, onStartServer, onStopServer }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [pathInput, setPathInput] = useState('');
  const [pathError, setPathError] = useState('');
  const [openingPath, setOpeningPath] = useState(false);
  const [creatingWorkspace, setCreatingWorkspace] = useState(false);
  const [workspaceName, setWorkspaceName] = useState('');
  const [directories, setDirectories] = useState<{ name: string; path: string }[]>([]);
  const [serverPulse, setServerPulse] = useState(false);
  const pathDialog = useRef<HTMLDialogElement>(null);
  const workspacePath = useWorkspaceStore((state) => state.workspacePath);
  const filespaces = useWorkspaceStore(state => state.filespaces);
  const busy = useSessionStore((state) => state.busy);

  // Pulse animation for running server
  useEffect(() => {
    if (serverStatus === 'running') {
      const interval = setInterval(() => setServerPulse(p => !p), 2000);
      return () => clearInterval(interval);
    }
  }, [serverStatus]);

  const openPathDialog = () => {
    if (busy || openingPath) return;
    setCreatingWorkspace(false);
    setPathInput(workspacePath || '');
    setPathError('');
    setDirectories([]);
    pathDialog.current?.showModal();
  };

  const openCreateDialog = () => {
    if (busy || openingPath) return;
    setCreatingWorkspace(true);
    setPathInput('');
    setWorkspaceName('');
    setDirectories([]);
    setPathError('');
    pathDialog.current?.showModal();
  };

  const chooseParent = async () => {
    try {
      if (!nativeWorkspace()) {
        const result = await workspaceDirectories(pathInput || undefined);
        setPathInput(result.path); setDirectories(result.directories); setPathError('');
        return;
      }
      const path = await open({ directory: true, multiple: false });
      if (path) setPathInput(path);
    } catch {
      setPathError('Enter the parent directory path below; the folder chooser is unavailable.');
    }
  };

  const selectWorkspace = async (path: string) => {
    const resolved = await resolveWorkspace(path);
    useWorkspaceStore.getState().setWorkspace(resolved);
  };

  const reopenSpace = async (path: string) => {
    if (busy || openingPath) return;
    setOpeningPath(true); setPathError('');
    try { await selectWorkspace(path); }
    catch (error) { setOpeningPath(false); openPathDialog(); setPathError(String(error)); }
    finally { setOpeningPath(false); }
  };

  const handleOpenPath = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!pathInput.trim() || openingPath || busy || (creatingWorkspace && !workspaceName.trim())) return;
    setOpeningPath(true);
    setPathError('');
    try {
      if (creatingWorkspace) {
        const resolved = await createWorkspace(pathInput, workspaceName);
        useWorkspaceStore.getState().setWorkspace(resolved);
      } else {
        await selectWorkspace(pathInput);
      }
      pathDialog.current?.close();
    } catch (error) {
      setPathError(String(error));
    } finally {
      setOpeningPath(false);
    }
  };

  const handleOpenFolder = async () => {
    if (busy || openingPath) return;
    if (!nativeWorkspace()) { openPathDialog(); return; }
    try {
      const path = await open({ directory: true, multiple: false });
      if (path) {
        await selectWorkspace(path);
      }
    } catch (e) {
      openPathDialog();
      setPathError(`The folder chooser could not open this workspace. ${String(e)}`);
    }
  };

  const getStatusConfig = () => {
    switch (serverStatus) {
      case 'running': return { color: 'success', icon: ShieldCheck, pulse: true, label: 'Active' };
      case 'starting': return { color: 'warning', icon: Zap, pulse: true, label: 'Starting…' };
      default: return { color: 'error', icon: Square, pulse: false, label: 'Stopped' };
    }
  };

  const StatusIcon = getStatusConfig().icon;

  return (
    <aside className={`sidebar transition-all duration-300 ease-out ${collapsed ? 'w-16' : 'w-64'}`}>
      <dialog ref={pathDialog} onCancel={(event) => { if (openingPath) event.preventDefault(); }} aria-labelledby="workspace-path-title" className="m-auto w-full max-w-xl rounded-2xl border-bifang-border bg-bifang-panel p-6 text-bifang-text-primary shadow-2xl glass-strong">
        <form onSubmit={handleOpenPath}>
          <h2 id="workspace-path-title" className="text-h4 text-bifang-text-primary">{creatingWorkspace ? 'Create a new workspace' : 'Open a workspace'}</h2>
          <p className="mt-2 text-body-sm text-bifang-text-secondary">{creatingWorkspace ? 'Start fresh with an empty project folder. Choose its name and an existing parent directory. No packages, scripts or Git setup run automatically.' : 'Enter the absolute path to an existing project directory. This does not run a command or change its files.'}</p>
          {creatingWorkspace && <>
            <label htmlFor="workspace-name" className="mt-5 block text-label text-bifang-text-secondary">Workspace name</label>
            <input id="workspace-name" value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} maxLength={120} autoComplete="off" disabled={openingPath} required className="input mt-2 focus:ring-bifang-focus-ring focus:ring-offset-bifang-focus-offset" />
          </>}
          <label htmlFor="workspace-path" className="mt-5 block text-label text-bifang-text-secondary">{creatingWorkspace ? 'Parent directory path' : 'Directory path'}</label>
          <input id="workspace-path" name="workspace-path" value={pathInput} onChange={(event) => setPathInput(event.target.value)} aria-describedby={pathError ? 'workspace-path-error' : undefined} aria-invalid={Boolean(pathError)} className="input mt-2 focus:ring-bifang-focus-ring focus:ring-offset-bifang-focus-offset" autoFocus autoComplete="off" spellCheck={false} disabled={openingPath} />
          {creatingWorkspace && <button type="button" onClick={chooseParent} disabled={openingPath} className="mt-2 text-label text-bifang-brand-orange hover:underline hover:text-bifang-brand-orange/80 transition-colors">Browse parent folder…</button>}
          {directories.length > 0 && <select aria-label="Choose parent directory" className="input mt-2" value="" onChange={event => { setPathInput(event.target.value); setDirectories([]); }}><option value="" disabled>Choose a directory within this folder…</option>{directories.map(directory => <option key={directory.path} value={directory.path}>{directory.name}</option>)}</select>}
          {pathError && <p id="workspace-path-error" role="alert" className="mt-3 text-body-sm text-bifang-brand-red">{pathError}</p>}
          <div className="mt-6 flex justify-end gap-3">
            <button type="button" className="btn-secondary" onClick={() => pathDialog.current?.close()} disabled={openingPath}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={busy || openingPath || !pathInput.trim() || (creatingWorkspace && !workspaceName.trim())}>{openingPath ? (creatingWorkspace ? 'Creating…' : 'Opening…') : (creatingWorkspace ? 'Create workspace' : 'Open workspace')}</button>
          </div>
        </form>
      </dialog>
      <div className="flex flex-col h-full animate-in slide-in-left">
        {/* Header */}
        <div className={`flex items-center justify-between p-4 border-b border-bifang-border ${collapsed ? 'justify-center' : ''}`}>
          {!collapsed && (
            <div className="flex items-center gap-3 animate-in stagger-1">
              <div className="relative">
                <img src="/favicon.svg" className="h-9 w-9" alt="Bifang" />
                {serverStatus === 'running' && <span className="absolute -bottom-1 -right-1 w-3 h-3 rounded-full bg-bifang-success ring-2 ring-bifang-canvas animate-pulse" />}
              </div>
              <div>
                <h1 className="text-h5 text-bifang-text-primary tracking-tight">Bifang</h1>
                <p className="text-overline text-bifang-brand-orange">Build. Run. Verify.</p>
              </div>
            </div>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="p-2 rounded-lg bg-bifang-panel/50 hover:bg-bifang-panel hover:border-bifang-border-bright border border-bifang-border transition-all duration-200"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <ChevronRight className="w-5 h-5 text-bifang-text-secondary" /> : <ChevronLeft className="w-5 h-5 text-bifang-text-secondary" />}
          </button>
        </div>

        {/* Workspace Section */}
        <div className={`p-4 border-b border-bifang-border ${collapsed ? 'px-2' : ''}`}>
          {!collapsed && (
            <div className="flex items-center gap-2 mb-3">
              <FolderOpen className="w-4 h-4 text-bifang-brand-orange" />
              <span className="text-overline text-bifang-text-muted">Workspace</span>
            </div>
          )}
          <button
            onClick={handleOpenFolder}
            disabled={busy}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg bg-bifang-surface border border-bifang-border/50 hover:bg-bifang-surface-hover hover:border-bifang-border transition-all duration-200 text-left ${collapsed ? 'justify-center' : ''} group`}
            title={collapsed ? 'Open workspace' : ''}
          >
            <FolderOpen className="w-5 h-5 text-bifang-text-muted flex-shrink-0 group-hover:text-bifang-brand-orange transition-colors" />
            {!collapsed && (
              <span className="text-body-sm text-bifang-text-secondary truncate group-hover:text-bifang-text-primary transition-colors">
                {workspacePath ? workspacePath.split(/[\\/]/).pop() || workspacePath : 'Open existing workspace…'}
              </span>
            )}
          </button>
          <button type="button" onClick={openCreateDialog} disabled={busy || openingPath} title="New workspace" aria-label="New workspace" className={`mt-3 w-full flex items-center gap-3 rounded-lg border-2 border-dashed border-bifang-brand-red/30 bg-bifang-panel/50 px-3 py-2.5 text-bifang-brand-red hover:border-bifang-brand-red hover:bg-bifang-brand-red/5 hover:text-bifang-brand-red disabled:opacity-50 disabled:hover:border-bifang-brand-red/30 disabled:hover:bg-bifang-panel/50 transition-all duration-200 ${collapsed ? 'justify-center' : ''}`}>
            <FolderPlus className="h-5 w-5 shrink-0" />
            {!collapsed && <span className="text-body-sm font-medium">New workspace…</span>}
            <Sparkles className="w-4 h-4 opacity-60" />
          </button>
        </div>

        {!collapsed && <button type="button" disabled={busy} className="mx-4 mb-4 text-left text-caption text-bifang-text-muted underline-offset-4 hover:text-bifang-text-secondary hover:underline disabled:opacity-50 transition-colors" onClick={openPathDialog}>Open by path…</button>}
        {!collapsed && filespaces.length > 0 && <section aria-label="Saved filespaces" className="border-b border-bifang-border px-4 pb-4">
          <h2 className="mb-2 text-overline text-bifang-text-muted">Filespaces</h2>
          <select aria-label="Reopen a saved filespace" value="" disabled={busy || openingPath} className="input" onChange={event => { if (event.target.value) void reopenSpace(event.target.value); }}>
            <option value="">Reopen a project…</option>
            {filespaces.map(space => <option key={space.path} value={space.path}>{space.name} — {space.path}</option>)}
          </select>
          <p className="mt-2 text-caption text-bifang-text-muted">Remembers projects on this device when storage is available. Files stay on disk.</p>
          {workspacePath && filespaces.some(space => space.path === workspacePath) && <button type="button" className="mt-2 text-caption text-bifang-text-muted hover:text-bifang-text-secondary transition-colors" onClick={() => useWorkspaceStore.getState().forgetWorkspace(workspacePath)}>Forget current filespace</button>}
        </section>}

        {/* Server Controls */}
        <div className={`p-4 border-b border-bifang-border ${collapsed ? 'px-2' : ''}`}>
          {!collapsed && (
            <div className="flex items-center gap-2 mb-3">
              <Zap className="w-4 h-4 text-bifang-brand-orange" />
              <span className="text-overline text-bifang-text-muted">Server</span>
            </div>
          )}
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className="relative flex-shrink-0">
                <StatusIcon className={`w-5 h-5 text-bifang-${getStatusConfig().color} ${getStatusConfig().pulse ? 'animate-pulse' : ''}`} />
                {getStatusConfig().pulse && serverPulse && <span className="absolute inset-0 w-5 h-5 rounded-full bg-bifang-success/30 animate-ping" />}
              </div>
              {!collapsed && (
                <span className="text-body-sm font-medium text-bifang-text-primary capitalize">{getStatusConfig().label}</span>
              )}
            </div>
            {!collapsed && (
              <div className="flex gap-2">
                <button
                  onClick={onStartServer}
                  disabled={serverStatus === 'running' || busy}
                  className="flex-1 btn-primary"
                >
                  <Play className="w-4 h-4 mr-1.5" />
                  <span>Start</span>
                </button>
                <button
                  onClick={onStopServer}
                  disabled={serverStatus === 'stopped' || busy}
                  className="flex-1 btn-destructive"
                >
                  <Square className="w-4 h-4 mr-1.5" />
                  <span>Stop</span>
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="flex-1" />

        {/* Version & Brand Footer */}
        <div className={`p-4 border-t border-bifang-border ${collapsed ? 'px-2' : ''}`}>
          {!collapsed && (
            <div className="text-center animate-in slide-up">
              <p className="text-caption text-bifang-text-muted">v{version}</p>
              <p className="mt-1 text-overline text-bifang-brand-orange/60">Evidence-driven coding</p>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}