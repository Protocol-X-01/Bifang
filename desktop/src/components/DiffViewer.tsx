import { localFetch } from '../api/localApi';
import { useEffect, useRef, useState } from 'react';
import { FileText, Minus, Plus, Copy, Check, Code2 } from 'lucide-react';
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
  const [patchDigest, setPatchDigest] = useState('');
  const reviewedPatch = useRef<{ sessionId: string; digest: string } | null>(null);
  const [viewMode, setViewMode] = useState<'unified' | 'split'>('unified');
  const [applying, setApplying] = useState(false);
  const [applyMessage, setApplyMessage] = useState('');
  const applyDialog = useRef<HTMLDialogElement>(null);
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
    reviewedPatch.current = null;
    applyDialog.current?.close();
    setDiff([]);
    setDiffText('');
    setPatchDigest('');
    setApplyMessage('');
    const fetchDiff = async () => {
      if (!sessionId) {
        setDiff([]);
        setDiffText('');
        return;
      }
      try {
        const response = await localFetch(`/sessions/${sessionId}/diff`);
        if (!response.ok) return;
        const data = await response.json();
        if (active) {
          setDiffText(data.diff || '');
          setPatchDigest(/^[0-9a-f]{64}$/.test(data.patch_sha256) ? data.patch_sha256 : '');
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
    const reviewed = reviewedPatch.current;
    if (!reviewed || reviewed.sessionId !== sessionId) return;
    reviewedPatch.current = null;
    applyDialog.current?.close();
    setApplying(true);
    setApplyMessage('');
    try {
      const response = await localFetch(`/sessions/${reviewed.sessionId}/apply`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patch_sha256: reviewed.digest }),
      });
      if (!response.ok) throw new Error((await response.json()).detail || 'Could not apply changes.');
      setApplyMessage('Changes applied to the original project.');
    } catch (error) {
      setApplyMessage(String(error));
    } finally {
      setApplying(false);
    }
  };

  const getLineNumberStyle = () => 'w-8 text-right text-bifang-text-muted select-none pr-2 border-r border-bifang-border';

  return (
    <div className="flex flex-col w-80 bg-bifang-canvas border-l border-bifang-border">
      <dialog ref={applyDialog} aria-labelledby="apply-title" className="m-auto max-w-lg rounded-2xl border-bifang-border bg-bifang-panel p-6 text-bifang-text-primary shadow-2xl glass-strong">
        <div className="flex items-center gap-2 mb-4">
          <div className="p-1.5 rounded-lg bg-gradient-to-r from-bifang-brand-red to-bifang-brand-orange">
            <Check className="w-5 h-5 text-bifang-brand-white" />
          </div>
          <h2 id="apply-title" className="text-h4 text-bifang-text-primary">Apply reviewed changes?</h2>
        </div>
        <p className="text-body-sm text-bifang-text-secondary mb-6">This copies the reviewed patch to your original project. A Git checkout must be clean; a folder must be unchanged since this session started.</p>
        <div className="flex justify-end gap-3">
          <button type="button" className="btn-secondary" onClick={() => applyDialog.current?.close()} autoFocus>Cancel</button>
          <button type="button" className="btn-primary" onClick={applyChanges} disabled={applying}>{applying ? 'Applying…' : 'Apply to project'}</button>
        </div>
      </dialog>

      <div className="p-4 border-b border-bifang-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-gradient-to-r from-bifang-brand-red to-bifang-brand-orange">
            <FileText className="w-5 h-5 text-bifang-brand-white" />
          </div>
          <h3 className="text-h5 text-bifang-text-primary truncate">Workspace Diff</h3>
        </div>
      </div>

      <div className="px-4 py-3 border-b border-bifang-border flex items-center gap-2">
        <button
          className={`px-3 py-1.5 rounded-md text-body-sm font-medium transition-all duration-200 ${viewMode === 'unified'
            ? 'bg-gradient-to-r from-bifang-brand-red to-bifang-brand-orange text-bifang-brand-white shadow-lg shadow-bifang-brand-red/20'
            : 'bg-bifang-surface text-bifang-text-secondary hover:bg-bifang-panel hover:text-bifang-text-primary'}`}
          onClick={() => setViewMode('unified')}
        >
          <Code2 className="w-3.5 h-3.5 inline mr-1.5" />
          Unified
        </button>
        <button
          className={`px-3 py-1.5 rounded-md text-body-sm font-medium transition-all duration-200 ${viewMode === 'split'
            ? 'bg-gradient-to-r from-bifang-brand-red to-bifang-brand-orange text-bifang-brand-white shadow-lg shadow-bifang-brand-red/20'
            : 'bg-bifang-surface text-bifang-text-secondary hover:bg-bifang-panel hover:text-bifang-text-primary'}`}
          onClick={() => setViewMode('split')}
        >
          Split
        </button>
        <button className="btn-success ml-auto" onClick={() => {
          if (!sessionId || !patchDigest) return;
          reviewedPatch.current = { sessionId, digest: patchDigest };
          applyDialog.current?.showModal();
        }} disabled={applying || !diffText || !patchDigest}>
          <Check className="w-3.5 h-3.5 inline mr-1.5" />{applying ? 'Applying…' : 'Apply'}
        </button>
        <button className="p-2 rounded-lg bg-bifang-surface border border-bifang-border text-bifang-text-muted hover:bg-bifang-panel hover:text-bifang-text-primary hover:border-bifang-border-bright transition-all duration-200" title="Copy diff" onClick={() => navigator.clipboard.writeText(diffText)} disabled={!diffText}>
          <Copy className="w-4 h-4" />
        </button>
      </div>

      {applyMessage && <p role="status" className="border-b border-bifang-brand-red/30 bg-bifang-brand-red/10 px-4 py-3 text-body-sm text-bifang-brand-red">{applyMessage}</p>}

      <div className="flex-1 overflow-auto p-4 font-mono text-body-sm scrollbar-thin">
        {diff.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <Code2 className="w-12 h-12 text-bifang-text-muted/50 mb-4" />
            <p className="text-bifang-text-muted">{sessionId ? 'No workspace changes yet.' : 'Choose a workspace and ask Bifang to make a change.'}</p>
          </div>
        )}
        {viewMode === 'unified' ? (
          <div className="space-y-0.5 font-mono">
            {diff.map((line, i) => (
              <div
                key={i}
                className={`flex gap-2 px-2 py-1 rounded-sm transition-colors ${
                  line.type === 'added' ? 'bg-bifang-success/10 border-l-2 border-bifang-success' :
                  line.type === 'removed' ? 'bg-bifang-brand-red/10 border-l-2 border-bifang-brand-red' :
                  'bg-transparent'
                }`}
              >
                <span className={getLineNumberStyle()}>
                  {line.oldLineNumber || ''}
                </span>
                <span className={getLineNumberStyle()}>
                  {line.newLineNumber || ''}
                </span>
                <span className={`flex-1 min-w-0 truncate ${line.type === 'added' ? 'text-bifang-success' : line.type === 'removed' ? 'text-bifang-brand-red' : 'text-bifang-text-secondary'}`}>
                  {line.type === 'added' && <Plus className="w-3.5 h-3.5 inline mr-1.5 text-bifang-success" />}
                  {line.type === 'removed' && <Minus className="w-3.5 h-3.5 inline mr-1.5 text-bifang-brand-red" />}
                  {line.content}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-0.5">
              <div className="text-overline text-bifang-text-muted mb-2 px-2">Original</div>
              {diff.map((line, i) =>
                line.type !== 'added' && (
                  <div
                    key={i}
                    className={`flex gap-2 px-2 py-1 rounded-sm ${line.type === 'removed' ? 'bg-bifang-brand-red/10 border-l-2 border-bifang-brand-red' : ''}`}
                  >
                    <span className={getLineNumberStyle()}>
                      {line.oldLineNumber || ''}
                    </span>
                    <span className={`flex-1 min-w-0 truncate ${line.type === 'removed' ? 'text-bifang-brand-red line-through' : 'text-bifang-text-secondary'}`}>
                      {line.type === 'removed' && <Minus className="w-3.5 h-3.5 inline mr-1.5 text-bifang-brand-red" />}
                      {line.content}
                    </span>
                  </div>
                )
              )}
            </div>
            <div className="space-y-0.5">
              <div className="text-overline text-bifang-text-muted mb-2 px-2">Modified</div>
              {diff.map((line, i) =>
                line.type !== 'removed' && (
                  <div
                    key={i}
                    className={`flex gap-2 px-2 py-1 rounded-sm ${line.type === 'added' ? 'bg-bifang-success/10 border-l-2 border-bifang-success' : ''}`}
                  >
                    <span className={getLineNumberStyle()}>
                      {line.newLineNumber || ''}
                    </span>
                    <span className={`flex-1 min-w-0 truncate ${line.type === 'added' ? 'text-bifang-success' : 'text-bifang-text-secondary'}`}>
                      {line.type === 'added' && <Plus className="w-3.5 h-3.5 inline mr-1.5 text-bifang-success" />}
                      {line.content}
                    </span>
                  </div>
                )
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}