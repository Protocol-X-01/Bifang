import { localFetch } from '../api/localApi';
import { useEffect, useRef, useState } from 'react';
import { useSessionStore, useWorkspaceStore } from '../stores/bifangStore';
import { parsePreparedImages, parseVisualCatalog, parseVisualResult, visualObservations, visualUploadError,
  type PreparedImage, type VisualModel, type VisualResult } from '../api/vision';
import { Loader2, AlertTriangle, CheckCircle, Image, RefreshCw, X, Sparkles, Eye, Image as ImageIcon } from 'lucide-react';

export function VisionPanel({ ensureSession, onUse }: { ensureSession: () => Promise<string>; onUse: (text: string) => void }) {
  const sessionId = useSessionStore((state) => state.sessionId);
  const busy = useSessionStore((state) => state.busy);
  const workspace = useWorkspaceStore((state) => state.workspacePath);
  const [provider, setProvider] = useState('nebius');
  const [providers, setProviders] = useState(['nebius', 'nvidia']);
  const [models, setModels] = useState<VisualModel[]>([]);
  const [model, setModel] = useState('');
  const [images, setImages] = useState<PreparedImage[]>([]);
  const [prompt, setPrompt] = useState('Inspect this screenshot for UI or coding issues. Separate observations from guesses.');
  const [result, setResult] = useState<VisualResult | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const epoch = useRef(0);
  const previousSession = useRef(sessionId);
  const activeSession = useRef<string | null>(null);
  const activeRequest = useRef('');
  const cancelRequested = useRef(false);
  const preparation = useRef<AbortController | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const reset = () => {
    epoch.current += 1; preparation.current?.abort();
    cancelRequested.current = true;
    if (activeSession.current) void localFetch(`/sessions/${activeSession.current}/vision/cancel?request_id=${activeRequest.current}`, { method: 'POST' })
      .catch((e) => console.error('[VisionPanel] Failed to cancel vision:', e));
    activeSession.current = null;
    if (fileInput.current) fileInput.current.value = '';
    setImages([]); setResult(null); setError(''); setConfirming(false); setLoading(false); setRunning(false);
  };
  useEffect(() => { reset(); }, [workspace]);
  useEffect(() => {
    if (previousSession.current && previousSession.current !== sessionId) reset();
    previousSession.current = sessionId;
  }, [sessionId]);
  useEffect(() => () => {
    epoch.current += 1; preparation.current?.abort();
    cancelRequested.current = true;
    if (activeSession.current) void localFetch(`/sessions/${activeSession.current}/vision/cancel?request_id=${activeRequest.current}`, { method: 'POST' })
      .catch((e) => console.error('[VisionPanel] Failed to cancel vision:', e));
  }, []);
  useEffect(() => { if (confirming) dialog.current?.showModal(); else dialog.current?.close(); }, [confirming]);

  const refresh = async (selected = provider) => {
    if (busy || loading) return;
    const generation = epoch.current;
    setLoading(true); setError(''); setModel(''); setModels([]); setResult(null);
    try {
      const response = await localFetch(`/vision/models?provider=${encodeURIComponent(selected)}`);
      if (!response.ok) throw new Error('Visual model capabilities unavailable. Refresh before sharing images.');
      const catalog = parseVisualCatalog(await response.json());
      if (generation !== epoch.current) return;
      setProviders(catalog.providers); setProvider(catalog.provider || selected); setModels(catalog.models);
      if (!catalog.models.length) setError('No declared vision models are listed for this endpoint. Check provider configuration.');
    } catch (failure) { if (generation === epoch.current) setError(String(failure)); }
    finally { if (generation === epoch.current) setLoading(false); }
  };

  const chooseImages = async (files: FileList | null) => {
    if (!files || !files.length || busy || loading) return;
    const invalid = visualUploadError(files);
    if (invalid) { setError(invalid); setImages([]); setResult(null); return; }
    const generation = epoch.current;
    const controller = new AbortController(); preparation.current = controller;
    setLoading(true); setError(''); setResult(null); setImages([]);
    try {
      const selected = await Promise.all(Array.from(files).map((file) => new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () => reject(new Error('Could not read the selected image.'));
        reader.onload = () => typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('Invalid local image.'));
        reader.readAsDataURL(file);
      })));
      if (generation !== epoch.current) return;
      const response = await localFetch('/vision/prepare', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ images: selected.map((data_url) => ({ data_url })) }),
      });
      if (!response.ok) throw new Error('Image preparation failed. Use still PNG, JPEG or WebP images below 2 MB and four million pixels.');
      const prepared = parsePreparedImages(await response.json());
      if (generation === epoch.current) setImages(prepared);
    } catch (failure) { if (generation === epoch.current) setError(String(failure)); }
    finally { if (generation === epoch.current) { setLoading(false); preparation.current = null; } }
  };

  const inspect = async () => {
    if (useSessionStore.getState().busy || loading || !model || !images.length || !prompt.trim()) return;
    setConfirming(false); setRunning(true); setError(''); setResult(null);
    cancelRequested.current = false; activeRequest.current = crypto.randomUUID().replace(/-/g, '');
    useSessionStore.getState().setBusy(true);
    const generation = epoch.current;
    try {
      const identity = await ensureSession(); activeSession.current = identity;
      if (generation !== epoch.current || cancelRequested.current) return;
      const response = await localFetch(`/sessions/${identity}/vision`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, model, prompt, images: images.map(({ data_url }) => ({ data_url })),
          sharing_confirmed: true, request_id: activeRequest.current }),
      });
      if (!response.ok) throw new Error(response.status === 409 ? 'Visual review cancelled or the session is busy.' :
        'Visual review unavailable. No automatic fallback or retry was made.');
      const reviewed = parseVisualResult(await response.json());
      if (reviewed.receipt.request_id !== activeRequest.current || reviewed.receipt.provider !== provider ||
        reviewed.receipt.requested_model !== model || reviewed.images.length !== images.length ||
        reviewed.images.some((image, index) => image.sha256 !== images[index].sha256)) {
        throw new Error('Visual receipt does not match the selected model and images.');
      }
      if (generation === epoch.current && useSessionStore.getState().sessionId === identity) setResult(reviewed);
    } catch (failure) { if (generation === epoch.current) setError(String(failure)); }
    finally {
      activeSession.current = null; useSessionStore.getState().setBusy(false);
      if (generation === epoch.current) setRunning(false);
    }
  };

  const cancel = async () => {
    cancelRequested.current = true;
    if (!activeSession.current) return;
    try {
      const response = await localFetch(`/sessions/${activeSession.current}/vision/cancel?request_id=${activeRequest.current}`, { method: 'POST' });
      if (!response.ok) throw new Error('Could not cancel visual review.');
    } catch (failure) { setError(String(failure)); }
  };

  return (
    <details className="border-b border-bifang-border p-4 bg-bifang-panel/50 animate-in">
      <summary className="cursor-pointer flex items-center gap-2 text-h5 text-bifang-text-primary">
        <Eye className="w-5 h-5 text-bifang-brand-orange" />
        Visual context
        <span className={`ml-2 text-caption font-medium ${running ? 'text-bifang-warning animate-pulse' : result ? 'text-bifang-success' : 'text-bifang-text-muted'}`}>
          {running ? 'reviewing' : result ? 'observed' : 'ready'}
        </span>
      </summary>

      <p className="mt-2 text-caption text-bifang-text-muted">Inspect screenshots, diagrams or code images. Choose what to pass into the coding conversation.</p>

      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="text-caption text-bifang-text-muted">Provider
          <select aria-label="Visual provider" className="input input-sm mt-1" value={provider} disabled={busy || loading}
            onChange={(event) => { setProvider(event.target.value); void refresh(event.target.value); }}>
            {providers.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
        <button className="btn-secondary btn-sm" disabled={busy || loading} onClick={() => void refresh()}>
          <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Refresh vision models
        </button>
      </div>

      <label className="mt-3 block text-caption text-bifang-text-muted">Exact image-capable model
        <select aria-label="Visual model" className="input input-sm mt-1 w-full" value={model} disabled={busy || loading}
          onChange={(event) => { setModel(event.target.value); setResult(null); }}>
          <option value="">Choose a model after refreshing capabilities</option>
          {models.map((entry) => <option key={entry.model} value={entry.model}>{entry.model}{entry.capability_source === 'operator-declared' ? ' · operator-declared' : ''}</option>)}
        </select>
      </label>

      <label className="mt-3 block text-caption text-bifang-text-muted">Local images · up to two
        <input ref={fileInput} aria-label="Visual images" type="file" accept="image/png,image/jpeg,image/webp" multiple
          disabled={busy || loading} className="input input-sm mt-2 block w-full" onChange={(event) => void chooseImages(event.target.files)} />
      </label>

      {images.length && (
        <div className="mt-3 flex flex-wrap gap-3">
          {images.map((image, index) => (
            <figure key={`${index}:${image.sha256}`} className="max-w-52 animate-in stagger-1">
              <img src={image.data_url} alt={`Prepared visual context ${index + 1}`} className="max-h-24 rounded-lg border-bifang-border object-contain" />
              <figcaption className="mt-1 text-caption text-bifang-text-muted">{image.width} × {image.height} · metadata removed</figcaption>
            </figure>
          ))}
        </div>
      )}

      <label className="mt-3 block text-caption text-bifang-text-muted">Visual question
        <textarea aria-label="Visual question" rows={2} maxLength={4000} className="input mt-1 h-auto w-full" value={prompt}
          disabled={busy || loading} onChange={(event) => { setPrompt(event.target.value); setResult(null); }} />
      </label>

      <div className="mt-3 flex flex-wrap gap-2">
        <button className="btn-secondary" disabled={busy || loading || !workspace || !model || !images.length || !prompt.trim()} onClick={() => setConfirming(true)}>
          <Sparkles className="w-4 h-4 mr-1.5" /> Review images
        </button>
        <button className="btn-secondary" disabled={!running} onClick={() => void cancel()}>
          <X className="w-4 h-4 mr-1.5" /> Cancel visual review
        </button>
        <button className="btn-secondary" disabled={busy || loading || !images.length} onClick={() => { setImages([]); setResult(null); if (fileInput.current) fileInput.current.value = ''; }}>
          <ImageIcon className="w-4 h-4 mr-1.5" /> Clear images
        </button>
      </div>

      {loading && <p role="status" className="mt-2 text-caption text-bifang-brand-orange flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" />Preparing image or model capabilities…</p>}
      {error && <p role="alert" className="mt-3 text-caption text-bifang-brand-red animate-in">{error}</p>}

      {result && (
        <section className="mt-3 rounded-xl border-bifang-border bg-bifang-panel p-3 animate-in">
          <h3 className="text-caption font-semibold text-bifang-warning flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5" />Visual observations · unverified model analysis</h3>
          <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words text-code text-bifang-text-secondary bg-bifang-canvas border border-bifang-border p-3 rounded-lg">{result.analysis}</pre>
          <p className="mt-2 break-all text-caption text-bifang-text-muted">
            Requested: {result.receipt.requested_model}<br />
            Reported: {result.receipt.reported_model || 'not supplied'} · {result.receipt.usage.total_tokens ?? 'unknown'} tokens
          </p>
          <details className="mt-2 text-caption">
            <summary className="cursor-pointer text-bifang-text-secondary">Image receipts</summary>
            {result.images.map((image, index) => <p key={`${index}:${image.sha256}`} className="mt-1 break-all font-mono">PNG SHA-256 {image.sha256}</p>)}
          </details>
          <button className="btn-secondary btn-sm mt-3" disabled={busy} onClick={() => onUse(visualObservations(result))}>
            <ImageIcon className="w-3.5 h-3.5 mr-1.5" /> Use observations in chat draft
          </button>
        </section>
      )}

      <dialog ref={dialog} aria-labelledby="visual-sharing-title" onCancel={(event) => { event.preventDefault(); setConfirming(false); }} className="m-auto max-w-xl rounded-2xl border-bifang-border bg-bifang-panel p-6 text-bifang-text-primary shadow-2xl glass-strong">
        <h2 id="visual-sharing-title" className="text-h4 text-bifang-text-primary">Share these images for visual review?</h2>
        <p className="mt-3 break-words text-body-sm text-bifang-text-secondary">Send {images.length} metadata-free image(s) and this question to {provider} · {model}. Provider usage and retention policies apply. Images stay out of Bifang chat history and audit contents; only image receipts are recorded. This reviewer has no tools.</p>
        <pre className="mt-3 max-h-32 overflow-auto whitespace-pre-wrap text-code text-bifang-brand-orange/80 bg-bifang-canvas border border-bifang-border p-3 rounded-lg">{prompt}</pre>
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-secondary" autoFocus onClick={() => setConfirming(false)}>Keep images local</button>
          <button className="btn-primary" onClick={() => void inspect()}>Share and review images</button>
        </div>
      </dialog>
    </details>
  );
}