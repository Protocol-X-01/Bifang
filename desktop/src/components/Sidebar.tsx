import { useState } from 'react';
import { open } from '@tauri-apps/plugin-dialog';
import { FolderOpen, Play, Square, ChevronLeft, ChevronRight } from 'lucide-react';
import { useWorkspaceStore } from '../stores/bifangStore';

interface SidebarProps {
  serverStatus: 'starting' | 'running' | 'stopped';
  onStartServer: () => void;
  onStopServer: () => void;
}

export function Sidebar({ serverStatus, onStartServer, onStopServer }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const workspacePath = useWorkspaceStore((state) => state.workspacePath);

  const handleOpenFolder = async () => {
    try {
      const path = await open({ directory: true, multiple: false });
      if (path) {
        useWorkspaceStore.getState().setWorkspace(path);
      }
    } catch (e) {
      console.error('Failed to open folder:', e);
    }
  };

  return (
    <aside className={`sidebar transition-all duration-300 ${collapsed ? 'w-16' : ''}`}>
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
                  disabled={serverStatus === 'running'}
                  className="flex-1 btn btn-sm btn-primary"
                >
                  <Play className="w-3 h-3 mr-1" />
                  <span>Start</span>
                </button>
                <button
                  onClick={onStopServer}
                  disabled={serverStatus === 'stopped'}
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
            <p className="text-xs text-surface-500 text-center">v0.2.0</p>
          )}
        </div>
      </div>
    </aside>
  );
}
