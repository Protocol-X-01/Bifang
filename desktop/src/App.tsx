import { useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Sidebar } from './components/Sidebar';
import { ChatPanel } from './components/ChatPanel';
import { FileExplorer } from './components/FileExplorer';
import { DiffViewer } from './components/DiffViewer';
import { StatusBar } from './components/StatusBar';
import { useBifangStore } from './stores/bifangStore';

function App() {
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
      <Sidebar
        serverStatus={serverStatus}
        onStartServer={handleStartServer}
        onStopServer={handleStopServer}
      />
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 flex overflow-hidden">
          <FileExplorer />
          <div className="flex-1 flex flex-col overflow-hidden border-l border-surface-800">
            <ChatPanel />
          </div>
          <DiffViewer />
        </div>
        <StatusBar />
      </div>
    </div>
  );
}

export default App;
