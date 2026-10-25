import { useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Sidebar } from './components/Sidebar';
import { ChatPanel } from './components/ChatPanel';
import { FileExplorer } from './components/FileExplorer';
import { DiffViewer } from './components/DiffViewer';
import { StatusBar } from './components/StatusBar';
import { RemoteWorkspace } from './components/RemoteWorkspace';
import { useSessionStore } from './stores/bifangStore';

function App() {
  const [remote, setRemote] = useState(false);
  const localBusy = useSessionStore(state => state.busy);
  const [serverStatus, setServerStatus] = useState<'starting' | 'running' | 'stopped'>('starting');
  useEffect(() => {
    checkServerStatus();
    const interval = setInterval(checkServerStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const checkServerStatus = async () => {
    try {
      const running = await invoke<boolean>('get_server_status');
      setServerStatus(running ? 'running' : 'stopped');
    } catch {
      setServerStatus('stopped');
    }
  };

  const handleStartServer = async () => {
    try {
      await invoke('start_bifang_server');
      setServerStatus('running');
    } catch (e) {
      console.error('Failed to start server:', e);
    }
  };

  const handleStopServer = async () => {
    try {
      await invoke('stop_bifang_server');
      setServerStatus('stopped');
    } catch (e) {
      console.error('Failed to stop server:', e);
    }
  };

  return (
    <div className="flex h-screen bg-surface-950 text-surface-50 font-sans">
      {remote ? <aside className="sidebar flex flex-col p-6" aria-label="Remote forge guide">
        <h1 className="flex items-center gap-2 text-lg font-bold text-bifang-500"><img src="/favicon.svg" className="h-8 w-8" alt="Bifang bird" />Bifang</h1>
        <p className="mt-8 text-xs uppercase tracking-widest text-brand-primary">Remote forge</p>
        <h2 className="mt-3 text-xl font-semibold">Your intent.<br />Verified changes.</h2>
        <ol className="mt-6 space-y-4 text-sm text-surface-300"><li>01 · Select a focused source snapshot</li><li>02 · Inspect the proposed change</li><li>03 · Approve the isolated check</li><li>04 · Review, stage and Apply</li></ol>
        <p className="mt-auto pt-6 text-xs text-surface-400">Remote jobs continue independently of the local server. You control each approval.</p>
      </aside> : <Sidebar
        serverStatus={serverStatus}
        onStartServer={handleStartServer}
        onStopServer={handleStopServer}
      />}
      <div className="flex-1 flex flex-col overflow-hidden">
        <nav aria-label="Workspace mode" className="flex gap-2 border-b border-surface-800 p-2">
          <button className={remote ? 'btn-secondary' : 'btn-primary'} disabled={localBusy} aria-pressed={!remote} onClick={() => setRemote(false)}>Local workspace</button>
          <button className={remote ? 'btn-primary' : 'btn-secondary'} disabled={localBusy} aria-pressed={remote} onClick={() => setRemote(true)}>Remote forge</button>
        </nav>
        {remote && <RemoteWorkspace />}
        <div className={`flex-1 flex overflow-hidden ${remote ? 'hidden' : ''}`}>
          <FileExplorer />
          <div className="flex-1 flex flex-col overflow-hidden border-l border-surface-800">
            <ChatPanel />
          </div>
          <DiffViewer />
        </div>
        {remote ? <footer className="border-t border-surface-800 px-4 py-2 text-xs text-surface-400">Remote forge · HTTPS native transport · hosted snapshots only</footer> : <StatusBar />}
      </div>
    </div>
  );
}

export default App;
