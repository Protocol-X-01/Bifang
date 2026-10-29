import { useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Loader2, AlertTriangle, Zap, RefreshCw } from 'lucide-react';

export function parseRemoteModels(value: unknown, provider: string): { models: string[]; default_model: string | null } {
  const catalog = value as { provider?: unknown; models?: unknown; default_model?: unknown } | null;
  if (!catalog || catalog.provider !== provider || !Array.isArray(catalog.models) || catalog.models.length > 4096
    || catalog.models.some(model => typeof model !== 'string' || !model.trim() || model.length > 256 || /[\x00-\x1f]/.test(model))
    || new Set(catalog.models).size !== catalog.models.length
    || !(catalog.default_model === null || typeof catalog.default_model === 'string' && catalog.models.includes(catalog.default_model))) {
    throw new Error('The service returned an invalid model list.');
  }
  return { models: catalog.models, default_model: catalog.default_model as string | null };
}

export function RemoteModelPicker({ provider, value, disabled, onChange }: {
  provider: string; value: string; disabled: boolean; onChange: (model: string) => void;
}) {
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let current = true;
    setLoading(true);
    setError('');
    setModels([]);
    onChange('');
    void invoke('remote_operation', { operation: { operation: 'models', provider } }).then(result => {
      if (!current) return;
      const catalog = parseRemoteModels(result, provider);
      setModels(catalog.models);
      onChange(catalog.default_model ?? catalog.models[0] ?? '');
      if (!catalog.models.length) setError('No models are available from this provider.');
    }).catch(() => {
      if (current) setError('Could not load the service model list. Check the connection, then retry.');
    }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [provider, revision, onChange]);

  return (
    <div className="space-y-2 animate-in">
      <label className="block text-caption text-bifang-text-muted">Model
        <select aria-label="Model" className="input mt-1" value={value} disabled={disabled || loading || !models.length} required onChange={event => onChange(event.target.value)}>
          <option value="" disabled>{loading ? 'Loading available models…' : 'Choose a model'}</option>
          {models.map(model => <option key={model} value={model}>{model}</option>)}
        </select>
      </label>
      {error && <p role="alert" className="text-caption text-bifang-brand-red">{error}</p>}
      <div className="flex items-center gap-2">
        <button type="button" className="btn-secondary btn-sm" disabled={disabled || loading} onClick={() => setRevision(current => current + 1)}>
          <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Refresh models
        </button>
        <p className="text-caption text-bifang-text-muted">Available IDs come from this service's provider catalogue. Availability alone does not establish coding quality or support for every task.</p>
      </div>
    </div>
  );
}