import { Brain, FileText, Trash2, TrendingUp } from 'lucide-react';

interface ContextStats {
  tokens_used: number;
  tokens_limit: number;
  files_active: number;
  messages_count: number;
}

export function ContextPanel() {
  const stats: ContextStats = {
    tokens_used: 45823,
    tokens_limit: 128000,
    files_active: 12,
    messages_count: 24
  };
  
  const tokenPercentage = (stats.tokens_used / stats.tokens_limit) * 100;
  const tokenColor = tokenPercentage > 90 ? 'bg-status-error' : tokenPercentage > 70 ? 'bg-status-warning' : 'bg-status-success';
  
  return (
    <div className="p-4 space-y-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Brain className="w-5 h-5 text-bifang-brand-orange" />
          Context Manager
        </h2>
      </div>
      
      <div className="space-y-3">
        <div className="flex items-center justify-between text-sm">
          <span className="text-bifang-text-muted">Token Usage</span>
          <span className="font-medium">{stats.tokens_used.toLocaleString()} / {stats.tokens_limit.toLocaleString()}</span>
        </div>
        
        <div className="h-2 bg-bifang-slate-panel rounded-full overflow-hidden">
          <div 
            className={`h-full ${tokenColor} transition-all duration-500`}
            style={{ width: `${tokenPercentage}%` }}
          />
        </div>
        
        <div className="flex items-center gap-2 text-xs text-bifang-text-muted">
          <TrendingUp className="w-3 h-3" />
          <span>{tokenPercentage.toFixed(1)}% used</span>
          <span className="ml-auto">~{(stats.tokens_limit - stats.tokens_used).toLocaleString()} remaining</span>
        </div>
      </div>
      
      <div className="bg-bifang-slate-panel/50 rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium flex items-center gap-2">
            <FileText className="w-4 h-4" />
            Active Files
          </h3>
          <span className="text-xs text-bifang-text-muted">{stats.files_active} files</span>
        </div>
        
        <div className="space-y-1 max-h-40 overflow-y-auto">
          {['src/app.tsx', 'components/ChatPanel.tsx', 'lib/utils.ts'].map(file => (
            <div key={file} className="flex items-center justify-between text-xs py-1 px-2 hover:bg-bifang-slate-elevated rounded transition-colors">
              <span className="text-bifang-text-secondary truncate">{file}</span>
              <button className="text-bifang-text-muted hover:text-status-error transition-colors">
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      </div>
      
      <div className="bg-bifang-slate-panel/50 rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium">Message History</h3>
          <span className="text-xs text-bifang-text-muted">{stats.messages_count} messages</span>
        </div>
        
        <button className="btn btn-xs btn-ghost w-full flex items-center justify-center gap-2">
          <Trash2 className="w-3 h-3" />
          Clear Old Messages
        </button>
      </div>
      
      <div className="bg-bifang-brand-orange/10 border border-bifang-brand-orange/30 rounded-lg p-4">
        <div className="text-xs text-bifang-text-muted mb-2">Estimated Cost (Nemotron Ultra)</div>
        <div className="text-lg font-bold text-bifang-brand-orange">
          ${(stats.tokens_used * 0.0000002).toFixed(4)}
        </div>
        <div className="text-xs text-bifang-text-muted mt-1">≈ {stats.messages_count} messages</div>
      </div>
    </div>
  );
}
