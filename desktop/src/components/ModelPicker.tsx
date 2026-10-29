import { localFetch } from '../api/localApi';
import { useEffect, useState } from 'react';
import { ChevronDown, RefreshCw, Sparkles, Zap, Shield } from 'lucide-react';
import { parseModelCatalog, selectionFor, selectionValue, type ModelCatalog, type ModelSelection } from '../api/models';

interface Props {
  selection: ModelSelection | null;
  busy: boolean;
  onChange: (selection: ModelSelection | null) => void;
}

export function ModelPicker({ selection, busy, onChange }: Props) {
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError('');
    setCatalog(null);
    localFetch('/models', { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error('The live model catalog is unavailable.');
        const result = parseModelCatalog(await response.json());
        if (!controller.signal.aborted) setCatalog(result);
      })
      .catch(() => { if (!controller.signal.aborted) setError('Catalog unavailable; the configured deployment remains selectable.'); });
    return () => controller.abort();
  }, [revision]);

  const selected = selectionValue(selection);
  const known = selected === 'configured' || selected === 'auto' ? true : catalog?.models.includes(selection?.model || '');

  return (
    <div className="border-b border-bifang-border bg-bifang-panel/50 px-4 py-3 animate-in">
      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor="model-selection" className="text-overline text-bifang-brand-orange">Model</label>
        <div className="relative min-w-0 flex-1">
          <select id="model-selection" value={selected} disabled={busy} onChange={(event) => onChange(selectionFor(event.target.value))} className="input appearance-none pr-10">
            <option value="configured">Configured deployment{catalog?.configured_model ? ` · ${catalog.configured_model}` : ''}</option>
            <option value="auto" disabled={!catalog?.auto_available}>Auto · task-based selection</option>
            {!known && selection?.model && <option value={selected} disabled>{selection.model} · unavailable</option>}
            {catalog?.models.map((model) => <option key={model} value={`model:${model}`}>{model}</option>)}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-bifang-text-muted" />
        </div>
        <button type="button" disabled={busy} onClick={() => setRevision((value) => value + 1)} className="btn-ghost btn-sm text-caption">
          <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
          Refresh models
        </button>
      </div>
      <p className="mt-2 text-caption text-bifang-text-muted">
        {(selection?.routing_mode || catalog?.configured_mode) === 'auto'
          ? 'Task-based routing on Token Factory. One model per step; no hidden parallel calls.'
          : selection || catalog ? 'Pinned for this request. Changing models keeps your conversation and workspace.'
            : 'Server configuration applies. Changing models keeps your conversation and workspace.'}
      </p>
      {error && <p role="status" className="mt-2 text-caption text-bifang-warning">{error}</p>}
    </div>
  );
}