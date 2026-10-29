import { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Server, Cpu, HardDrive, Globe, CheckCircle, XCircle } from 'lucide-react';

export function StatusBar() {
  const [serverInfo, setServerInfo] = useState<{
    status: 'running' | 'stopped';
  }>({ status: 'stopped' });

  useEffect(() => {
    const fetchInfo = async () => {
      try {
        const running = await invoke<boolean>('get_server_status');
        if (running) {
          setServerInfo({ status: 'running' });
        } else {
          setServerInfo({ status: 'stopped' });
        }
      } catch {
        setServerInfo({ status: 'stopped' });
      }
    };
    fetchInfo();
    const interval = setInterval(fetchInfo, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <footer className="h-10 px-4 border-t border-bifang-border bg-bifang-panel/80 backdrop-blur-sm flex items-center justify-between">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className={`flex items-center gap-1.5 ${serverInfo.status === 'running' ? 'text-bifang-success' : 'text-bifang-brand-red'}`}>
            {serverInfo.status === 'running' ? <CheckCircle className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
            <span className="text-caption font-medium capitalize">{serverInfo.status}</span>
          </div>
        </div>
      </div>
      <div className="flex items-center gap-4 text-caption text-bifang-text-muted">
        <span className="flex items-center gap-1.5">Agent API · localhost</span>
        <span className="flex items-center gap-1.5"><Cpu className="w-3.5 h-3.5" /> Agent ready</span>
      </div>
    </footer>
  );
}