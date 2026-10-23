import { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Server } from 'lucide-react';

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
    <footer className="h-8 px-4 border-t border-surface-800 bg-surface-900 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <Server className={`w-4 h-4 ${serverInfo.status === 'running' ? 'text-green-500' : 'text-red-500'}`} />
          <span className="text-xs text-surface-300 capitalize">{serverInfo.status}</span>
        </div>
      </div>
      <span className="text-xs text-surface-500">Agent API · localhost</span>
    </footer>
  );
}
