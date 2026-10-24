import { useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { open } from '@tauri-apps/plugin-dialog';
import { FolderOpen, Play, Square, ChevronLeft, ChevronRight } from 'lucide-react';
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
  const pathDialog = useRef<HTMLDialogElement>(null);
  const workspacePath = useWorkspaceStore((state) => state.workspacePath);
  const busy = useSessionStore((state) => state.busy);

  const openPathDialog = () => {
    if (busy) return;
    setPathInput(workspacePath || '');
    setPathError('');
    pathDialog.current?.showModal();
  };

  const selectWorkspace = async (path: string) => {
    const resolved = await invoke<string>('resolve_workspace_path', { path });
    useWorkspaceStore.getState().setWorkspace(resolved);
  };

  const handleOpenPath = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!pathInput.trim() || openingPath || busy) return;
    setOpeningPath(true);
    setPathError('');
    try {
      await selectWorkspace(pathInput);
      pathDialog.current?.close();
    } catch (error) {
      setPathError(String(error));
    } finally {
      setOpeningPath(false);
    }
  };

  const handleOpenFolder = async () => {
    if (busy) return;
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

  return (
    <aside className={`sidebar transition-all duration-300 ${collapsed ? 'w-16' : ''}`}>
      <dialog ref={pathDialog} onCancel={(event) => { if (openingPath) event.preventDefault(); }} aria-labelledby="workspace-path-title" className="m-auto w-full max-w-xl rounded-2xl border border-border bg-card p-6 text-card-foreground shadow-xl backdrop:bg-black/70">
        <form onSubmit={handleOpenPath}>
          <h2 id="workspace-path-title" className="text-xl font-semibold">Open a workspace</h2>
          <p className="mt-2 text-sm text-muted-foreground">Enter the absolute path to an existing project directory. This does not run a command or change its files.</p>
          <label htmlFor="workspace-path" className="mt-5 block text-sm font-medium">Directory path</label>
          <input id="workspace-path" name="workspace-path" value={pathInput} onChange={(event) => setPathInput(event.target.value)} aria-describedby={pathError ? 'workspace-path-error' : undefined} aria-invalid={Boolean(pathError)} className="mt-2 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-primary" autoFocus autoComplete="off" spellCheck={false} disabled={openingPath} />
          {pathError && <p id="workspace-path-error" role="alert" className="mt-3 text-sm text-red-300">{pathError}</p>}
          <div className="mt-6 flex justify-end gap-3">
            <button type="button" className="btn-secondary" onClick={() => pathDialog.current?.close()} disabled={openingPath}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={openingPath || !pathInput.trim()}>{openingPath ? 'Opening…' : 'Open workspace'}</button>
          </div>
        </form>
      </dialog>
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className={`flex items-center justify-between p-4 border-b border-surface-800 ${collapsed ? 'justify-center' : ''}`}>
          {!collapsed && (
            <h1 className="flex items-center gap-2 text-lg font-bold text-bifang-500">
              <img src="/favicon.svg" className="h-8 w-8" alt="Bifang bird" />
              <span>Bifang</span>
            </h1>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="p-2 rounded-lg hover:bg-surface-800 transition-colors"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <ChevronRight className="w-5 h-5" /> : <ChevronLeft className="w-5 h-5" />}
          </button>
        </div>

        {/* Workspace */}
        <div className={`p-4 border-b border-surface-800 ${collapsed ? 'px-2' : ''}`}>
          {!collapsed && (
            <label className="block text-xs font-medium text-surface-400 mb-2">Workspace</label>
          )}
          <button
            onClick={handleOpenFolder}
            disabled={busy}
            className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-800 hover:bg-surface-700 transition-colors text-left ${collapsed ? 'justify-center' : ''}`}
            title={collapsed ? 'Open workspace' : ''}
          >
            <FolderOpen className="w-4 h-4 text-surface-400 flex-shrink-0" />
            {!collapsed && (
              <span className="text-sm text-surface-300 truncate">
                {workspacePath ? workspacePath.split('/').pop() || workspacePath : 'No workspace'}
              </span>
            )}
          </button>
        </div>

        {!collapsed && <button type="button" disabled={busy} className="mx-4 mb-4 text-left text-xs text-surface-400 underline-offset-4 hover:text-surface-100 hover:underline disabled:opacity-50" onClick={openPathDialog}>Open by path…</button>}

        {/* Server Controls */}
        <div className={`p-4 border-b border-surface-800 ${collapsed ? 'px-2' : ''}`}>
          {!collapsed && (
            <label className="block text-xs font-medium text-surface-400 mb-2">Server</label>
          )}
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${
                serverStatus === 'running' ? 'bg-green-500' :
                serverStatus === 'starting' ? 'bg-yellow-500 animate-pulse' :
                'bg-red-500'
              }`} />
              {!collapsed && (
                <span className="text-sm text-surface-300 capitalize">{serverStatus}</span>
              )}
            </div>
            {!collapsed && (
              <div className="flex gap-2">
                <button
                  onClick={onStartServer}
                  disabled={serverStatus === 'running' || busy}
                  className="flex-1 btn btn-sm btn-primary"
                >
                  <Play className="w-3 h-3 mr-1" />
                  <span>Start</span>
                </button>
                <button
                  onClick={onStopServer}
                  disabled={serverStatus === 'stopped' || busy}
                  className="flex-1 btn-sm btn-destructive"
                >
                  <Square className="w-3 h-3 mr-1" />
                  <span>Stop</span>
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="flex-1" />

        {/* Version */}
        <div className={`p-4 border-t border-surface-800 ${collapsed ? 'px-2' : ''}`}>
          {!collapsed && (
            <p className="text-xs text-surface-500 text-center">v{version}</p>
          )}
        </div>
      </div>
    </aside>
  );
}
