import { Server, Loader2, Check } from 'lucide-react';

interface Props {
  status: string;
  progress: number;
}

export function LoadingScreen({ status, progress }: Props) {
  return (
    <div className="fixed inset-0 bg-gradient-to-br from-bifang-slate-canvas via-bifang-slate-elevated to-bifang-slate-canvas flex items-center justify-center z-50">
      <div className="text-center animate-in fade-in slide-in-from-bottom-4 duration-500">
        <div className="mb-8 relative">
          <div className="absolute inset-0 bg-bifang-brand-orange/20 blur-3xl rounded-full animate-pulse" />
          <Server className="w-20 h-20 mx-auto text-bifang-brand-orange relative animate-bounce" />
        </div>
        
        <div className="mb-6 relative">
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-40 h-40 rounded-full bg-gradient-to-r from-bifang-brand-red via-bifang-brand-orange to-bifang-brand-orange opacity-30 blur-3xl animate-pulse" />
          </div>
          <div className="relative flex items-center justify-center">
            <div className="text-7xl animate-bounce" style={{ animationDuration: '2s' }}>⚡</div>
          </div>
        </div>
        
        <h1 className="text-4xl font-bold mb-2 bg-gradient-to-r from-bifang-brand-red via-bifang-brand-orange to-bifang-brand-orange bg-clip-text text-transparent">
          Bifang
        </h1>
        <p className="text-bifang-text-secondary mb-8 text-base font-medium">Build. Run. Verify.</p>
        
        <p className="text-bifang-text-muted mb-4 text-xs">{status}</p>
        
        <div className="w-64 h-1.5 bg-bifang-slate-panel rounded-full overflow-hidden mx-auto mb-4">
          <div 
            className="h-full bg-gradient-to-r from-bifang-brand-red to-bifang-brand-orange transition-all duration-500 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
        
        <div className="flex items-center justify-center gap-2 text-xs text-bifang-text-muted">
          <Loader2 className="w-3 h-3 animate-spin" />
          <span>{Math.round(progress)}%</span>
        </div>
      </div>
    </div>
  );
}
