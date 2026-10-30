import { Server, RefreshCw, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { useState, useEffect } from 'react';

interface MCPServer {
  id: string;
  name: string;
  status: 'connected' | 'disconnected' | 'connecting';
  tools_count: number;
  last_heartbeat: string;
}

export function MCPPanel() {
  const [servers, setServers] = useState<MCPServer[]>([
    { id: 'librarian', name: 'Librarian MCP', status: 'connected', tools_count: 9236, last_heartbeat: '2s ago' },
    { id: 'toolbox', name: 'Toolbox MCP', status: 'connected', tools_count: 14, last_heartbeat: '5s ago' },
  ]);
  
  const [refreshing, setRefreshing] = useState(false);
  
  const handleRefresh = async () => {
    setRefreshing(true);
    // Simulated refresh
    await new Promise(resolve => setTimeout(resolve, 1000));
    setRefreshing(false);
  };
  
  const getStatusIcon = (status: MCPServer['status']) => {
    switch (status) {
      case 'connected': return <CheckCircle className="w-4 h-4 text-status-success" />;
      case 'disconnected': return <XCircle className="w-4 h-4 text-status-error" />;
      case 'connecting': return <Loader2 className="w-4 h-4 text-status-warning animate-spin" />;
    }
  };
  
  const getStatusColor = (status: MCPServer['status']) => {
    switch (status) {
      case 'connected': return 'border-status-success/30';
      case 'disconnected': return 'border-status-error/30';
      case 'connecting': return 'border-status-warning/30';
    }
  };
  
  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Server className="w-5 h-5 text-bifang-brand-orange" />
          MCP Servers
        </h2>
        <button 
          onClick={handleRefresh}
          disabled={refreshing}
          className="btn btn-sm btn-ghost"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
        </button>
      </div>
      
      {servers.map(server => (
        <div 
          key={server.id}
          className={`border rounded-lg p-4 bg-bifang-slate-panel/50 ${getStatusColor(server.status)}`}
        >
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-3">
              {getStatusIcon(server.status)}
              <div>
                <h3 className="font-medium text-sm">{server.name}</h3>
                <p className="text-xs text-bifang-text-muted">{server.tools_count.toLocaleString()} tools</p>
              </div>
            </div>
            <span className="text-xs text-bifang-text-muted">{server.last_heartbeat}</span>
          </div>
          
          <div className="flex gap-2">
            <button className="btn btn-xs btn-secondary flex-1">Configure</button>
            <button className="btn btn-xs btn-ghost flex-1">View Tools</button>
          </div>
        </div>
      ))}
      
      <button className="btn btn-sm btn-secondary w-full mt-4">
        + Add MCP Server
      </button>
    </div>
  );
}
