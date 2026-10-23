import { useEffect, useState } from 'react';
import { FileText, Minus, Plus, Copy, Check } from 'lucide-react';
import { useSessionStore } from '../stores/bifangStore';

interface DiffLine {
  type: 'added' | 'removed' | 'unchanged';
  content: string;
  lineNumber?: number;
  oldLineNumber?: number;
  newLineNumber?: number;
}

export function DiffViewer() {
  const [diff, setDiff] = useState<DiffLine[]>([]);
  const [diffText, setDiffText] = useState('');
  const [viewMode, setViewMode] = useState<'unified' | 'split'>('unified');
  const [applying, setApplying] = useState(false);
  const sessionId = useSessionStore((state) => state.sessionId);

  const parseDiff = (diffText: string): DiffLine[] => {
    const lines = diffText.split('\n');
    const result: DiffLine[] = [];
    let oldLine = 0;
    let newLine = 0;

    for (const line of lines) {
      if (line.startsWith('diff --git ') || line.startsWith('index ') || line.startsWith('--- ') || line.startsWith('+++ ')) continue;
      if (line.startsWith('@@')) {
        const match = line.match(/@@ -(\d+),?\d* \+(\d+),?\d* @@/);
        if (match) {
          oldLine = parseInt(match[1]) - 1;
          newLine = parseInt(match[2]) - 1;
        }
        result.push({ type: 'unchanged', content: line });
        continue;
      }
      if (line.startsWith('+') && !line.startsWith('+++')) {
        newLine++;
        result.push({ type: 'added', content: line.slice(1), newLineNumber: newLine });
      } else if (line.startsWith('-') && !line.startsWith('---')) {
        oldLine++;
        result.push({ type: 'removed', content: line.slice(1), oldLineNumber: oldLine });
      } else {
        oldLine++;
        newLine++;
        result.push({ type: 'unchanged', content: line, oldLineNumber: oldLine, newLineNumber: newLine });
      }
    }
    return result;
  };

  useEffect(() => {
    let active = true;
    const fetchDiff = async () => {
      if (!sessionId) {
        setDiff([]);
        setDiffText('');
        return;
      }
      try {
        const response = await fetch(`http://127.0.0.1:8000/sessions/${sessionId}/diff`);
        if (!response.ok) return;
        const data = await response.json();
        if (active) {
          setDiffText(data.diff || '');
          setDiff(parseDiff(data.diff || ''));
        }
      } catch (error) {
        console.error('Could not load workspace diff:', error);
      }
    };
    fetchDiff();
    const interval = window.setInterval(fetchDiff, 1500);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [sessionId]);

  const applyChanges = async () => {
    if (!sessionId || !diffText || !window.confirm('Apply these changes to the original repository? This requires a clean checkout.')) return;
    setApplying(true);
    try {
      const response = await fetch(`http://127.0.0.1:8000/sessions/${sessionId}/apply`, { method: 'POST' });
      if (!response.ok) throw new Error((await response.json()).detail || 'Could not apply changes.');
      window.alert('Changes applied to the original repository.');
    } catch (error) {
      window.alert(String(error));
    } finally {
      setApplying(false);
    }
  };

  return (
    <div className="flex flex-col w-80 bg-surface-950 border-l border-surface-800">
      <div className="p-4 border-b border-surface-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-bifang-500" />
          <h3 className="font-medium text-surface-100 truncate">Workspace Diff</h3>
        </div>
      </div>

      <div className="px-4 py-2 border-b border-surface-800 flex items-center gap-2">
        <button
          className={`px-3 py-1.5 rounded text-sm ${viewMode === 'unified' ? 'bg-bifang-500 text-white' : 'bg-surface-800 text-surface-300 hover:bg-surface-700'}`}
          onClick={() => setViewMode('unified')}
        >
          Unified
        </button>
        <button
          className={`px-3 py-1.5 rounded text-sm ${viewMode === 'split' ? 'bg-bifang-500 text-white' : 'bg-surface-800 text-surface-300 hover:bg-surface-700'}`}
          onClick={() => setViewMode('split')}
        >
          Split
        </button>
        <button className="px-3 py-1.5 rounded text-sm bg-green-700 text-white disabled:opacity-50" onClick={applyChanges} disabled={applying || !diffText}>
          <Check className="w-3 h-3 inline mr-1" />{applying ? 'Applying…' : 'Apply'}
        </button>
        <span className="flex-1" />
        <button className="p-1.5 rounded hover:bg-surface-800" title="Copy diff" onClick={() => navigator.clipboard.writeText(diffText)} disabled={!diffText}>
          <Copy className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-auto p-4 font-mono text-sm scrollbar-thin">
        {diff.length === 0 && <p className="text-sm text-surface-500">{sessionId ? 'No workspace changes yet.' : 'Choose a workspace and ask Bifang to make a change.'}</p>}
        {viewMode === 'unified' ? (
          <div className="space-y-0.5 font-mono">
            {diff.map((line, i) => (
              <div
                key={i}
                className={`flex gap-2 px-2 py-0.5 ${
                  line.type === 'added' ? 'bg-green-900/30' :
                  line.type === 'removed' ? 'bg-red-900/30' :
                  'bg-transparent'
                }`}
              >
                <span className="w-8 text-right text-surface-500 select-none pr-2 border-r border-surface-800">
                  {line.oldLineNumber || ''}
                </span>
                <span className="w-8 text-right text-surface-500 select-none pr-2 border-r border-surface-800">
                  {line.newLineNumber || ''}
                </span>
                <span className={`flex-1 ${line.type === 'added' ? 'text-green-300' : line.type === 'removed' ? 'text-red-300' : 'text-surface-300'}`}>
                  {line.type === 'added' && <Plus className="w-3 h-3 inline mr-1" />}
                  {line.type === 'removed' && <Minus className="w-3 h-3 inline mr-1" />}
                  {line.content}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-0.5">
              <div className="text-xs text-surface-500 mb-2 px-2">Original</div>
              {diff.map((line, i) => (
                line.type !== 'added' && (
                  <div
                    key={i}
                    className={`flex gap-2 px-2 py-0.5 ${line.type === 'removed' ? 'bg-red-900/30' : ''}`}
                  >
                    <span className="w-8 text-right text-surface-500 select-none pr-2 border-r border-surface-800">
                      {line.oldLineNumber || ''}
                    </span>
                    <span className={`flex-1 ${line.type === 'removed' ? 'text-red-300 line-through' : 'text-surface-300'}`}>
                      {line.type === 'removed' && <Minus className="w-3 h-3 inline mr-1" />}
                      {line.content}
                    </span>
                  </div>
                ))
              )}
            </div>
            <div className="space-y-0.5">
              <div className="text-xs text-surface-500 mb-2 px-2">Modified</div>
              {diff.map((line, i) => (
                line.type !== 'removed' && (
                  <div
                    key={i}
                    className={`flex gap-2 px-2 py-0.5 ${line.type === 'added' ? 'bg-green-900/30' : ''}`}
                  >
                    <span className="w-8 text-right text-surface-500 select-none pr-2 border-r border-surface-800">
                      {line.newLineNumber || ''}
                    </span>
                    <span className={`flex-1 ${line.type === 'added' ? 'text-green-300' : 'text-surface-300'}`}>
                      {line.type === 'added' && <Plus className="w-3 h-3 inline mr-1" />}
                      {line.content}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
