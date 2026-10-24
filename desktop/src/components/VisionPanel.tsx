import { useEffect, useRef, useState } from 'react';
import { useSessionStore, useWorkspaceStore } from '../stores/bifangStore';
import { parsePreparedImages, parseVisualCatalog, parseVisualResult, visualObservations, visualUploadError,
  type PreparedImage, type VisualModel, type VisualResult } from '../api/vision';

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
    if (activeSession.current) void fetch(`http://127.0.0.1:8000/sessions/${activeSession.current}/vision/cancel?request_id=${activeRequest.current}`, { method: 'POST' }).catch(() => {});
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
    if (activeSession.current) void fetch(`http://127.0.0.1:8000/sessions/${activeSession.current}/vision/cancel?request_id=${activeRequest.current}`, { method: 'POST' }).catch(() => {});
  }, []);
  useEffect(() => { if (confirming) dialog.current?.showModal(); else dialog.current?.close(); }, [confirming]);

  const refresh = async (selected = provider) => {
    if (busy || loading) return;
    const generation = epoch.current;
    setLoading(true); setError(''); setModel(''); setModels([]); setResult(null);
    try {
      const response = await fetch(`http://127.0.0.1:8000/vision/models?provider=${encodeURIComponent(selected)}`);
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
      const response = await fetch('http://127.0.0.1:8000/vision/prepare', {
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
      const response = await fetch(`http://127.0.0.1:8000/sessions/${identity}/vision`, {
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
      const response = await fetch(`http://127.0.0.1:8000/sessions/${activeSession.current}/vision/cancel?request_id=${activeRequest.current}`, { method: 'POST' });
      if (!response.ok) throw new Error('Could not cancel visual review.');
    } catch (failure) { setError(String(failure)); }
  };

  return <details className="border-b border-surface-800 p-4">
    <summary className="cursor-pointer text-sm font-semibold">Visual context · {running ? 'reviewing' : result ? 'observed' : 'ready'}</summary>
    <p className="mt-2 text-xs text-surface-400">Inspect screenshots, diagrams or code images. Choose what to pass into the coding conversation.</p>
    <div className="mt-3 flex flex-wrap items-end gap-2">
      <label className="text-xs">Provider<select aria-label="Visual provider" className="input mt-1" value={provider} disabled={busy || loading}
        onChange={(event) => { setProvider(event.target.value); void refresh(event.target.value); }}>
        {providers.map((name) => <option key={name} value={name}>{name}</option>)}
      </select></label>
      <button className="btn-secondary" disabled={busy || loading} onClick={() => void refresh()}>Refresh vision models</button>
    </div>
    <label className="mt-3 block text-xs">Exact image-capable model<select aria-label="Visual model" className="input mt-1 w-full" value={model} disabled={busy || loading}
      onChange={(event) => { setModel(event.target.value); setResult(null); }}>
      <option value="">Choose a model after refreshing capabilities</option>
      {models.map((entry) => <option key={entry.model} value={entry.model}>{entry.model}{entry.capability_source === 'operator-declared' ? ' · operator-declared' : ''}</option>)}
    </select></label>
    <label className="mt-3 block text-xs">Local images · up to two<input ref={fileInput} aria-label="Visual images" type="file" accept="image/png,image/jpeg,image/webp" multiple
      disabled={busy || loading} className="mt-2 block w-full text-xs" onChange={(event) => void chooseImages(event.target.files)} /></label>
    {!!images.length && <div className="mt-3 flex flex-wrap gap-3">{images.map((image, index) => <figure key={`${index}:${image.sha256}`} className="max-w-52">
      <img src={image.data_url} alt={`Prepared visual context ${index + 1}`} className="max-h-24 rounded-lg border border-surface-700 object-contain" />
      <figcaption className="mt-1 text-xs text-surface-400">{image.width} × {image.height} · metadata removed</figcaption>
    </figure>)}</div>}
    <label className="mt-3 block text-xs">Visual question<textarea aria-label="Visual question" rows={2} maxLength={4000} className="input mt-1 h-auto w-full" value={prompt}
      disabled={busy || loading} onChange={(event) => { setPrompt(event.target.value); setResult(null); }} /></label>
    <div className="mt-3 flex flex-wrap gap-2">
      <button className="btn-secondary" disabled={busy || loading || !workspace || !model || !images.length || !prompt.trim()} onClick={() => setConfirming(true)}>Review images</button>
      <button className="btn-secondary" disabled={!running} onClick={() => void cancel()}>Cancel visual review</button>
      <button className="btn-secondary" disabled={busy || loading || !images.length} onClick={() => {
        setImages([]); setResult(null); if (fileInput.current) fileInput.current.value = '';
      }}>Clear images</button>
    </div>
    {loading && <p role="status" className="mt-2 text-xs">Preparing image or model capabilities…</p>}
    {error && <p role="alert" className="mt-3 text-xs text-red-300">{error}</p>}
    {result && <section className="mt-3 rounded-xl border border-surface-700 bg-surface-900 p-3">
      <h3 className="text-xs font-semibold text-orange-300">Visual observations · unverified model analysis</h3>
      <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words text-xs">{result.analysis}</pre>
      <p className="mt-2 break-all text-xs text-surface-400">Requested: {result.receipt.requested_model}<br />Reported: {result.receipt.reported_model || 'not supplied'} · {result.receipt.usage.total_tokens ?? 'unknown'} tokens</p>
      <details className="mt-2 text-xs"><summary>Image receipts</summary>{result.images.map((image, index) => <p className="mt-1 break-all" key={`${index}:${image.sha256}`}>PNG SHA-256 {image.sha256}</p>)}</details>
      <button className="btn-secondary mt-3" disabled={busy} onClick={() => onUse(visualObservations(result))}>Use observations in chat draft</button>
    </section>}
    <dialog ref={dialog} aria-labelledby="visual-sharing-title" onCancel={(event) => { event.preventDefault(); setConfirming(false); }}
      className="m-auto max-w-xl rounded-2xl border border-border bg-card p-6 text-card-foreground backdrop:bg-black/70">
      <h2 id="visual-sharing-title" className="font-semibold">Share these images for visual review?</h2>
      <p className="mt-3 break-words text-sm">Send {images.length} metadata-free image(s) and this question to {provider} · {model}. Provider usage and retention policies apply. Images stay out of Bifang chat history and audit contents; only image receipts are recorded. This reviewer has no tools.</p>
      <pre className="mt-3 max-h-32 overflow-auto whitespace-pre-wrap text-xs">{prompt}</pre>
      <div className="mt-4 flex justify-end gap-2"><button className="btn-secondary" autoFocus onClick={() => setConfirming(false)}>Keep images local</button>
        <button className="btn-primary" onClick={() => void inspect()}>Share and review images</button></div>
    </dialog>
  </details>;
}
