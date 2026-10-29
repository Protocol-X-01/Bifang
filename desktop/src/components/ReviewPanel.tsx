import { localFetch } from '../api/localApi';
import { useEffect, useRef, useState } from 'react';
import { useSessionStore } from '../stores/bifangStore';
import { X, Loader2, AlertTriangle, CheckCircle, MessageSquare, Eye } from 'lucide-react';

type Worker = {
  role: string;
  status: string;
  analysis: string;
  observations: { tool: string; path: string | null; start: number | null; end: number | null; result_sha256: string }[];
  routing: { requested_model?: string; reported_model?: string }[];
};
type Review = { status: string; workers: Worker[] };

export function ReviewPanel() {
  const sessionId = useSessionStore((state) => state.sessionId);
  const busy = useSessionStore((state) => state.busy);
  const [prompt, setPrompt] = useState('Investigate this project and independently review correctness risks. Cite inspected files and distinguish observations from hypotheses.');
  const [review, setReview] = useState<Review>({ status: 'idle', workers: [] });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const budgetDialog = useRef<HTMLDialogElement>(null);
  const ownsBusy = useRef(false);
  const running = review.status === 'running' || review.status === 'pending';

  useEffect(() => {
    if (confirming) budgetDialog.current?.showModal();
    else budgetDialog.current?.close();
  }, [confirming]);

  useEffect(() => {
    setReview({ status: 'idle', workers: [] });
    setError('');
    setConfirming(false);
    if (!sessionId) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    const update = async () => {
      try {
        const response = await localFetch(`/sessions/${sessionId}/review`, { signal: controller.signal });
        if (!response.ok) throw new Error('Could not read worker status.');
        const next: Review = await response.json();
        if (!active || useSessionStore.getState().sessionId !== sessionId) return;
        setReview(next);
        const inProgress = next.status === 'running' || next.status === 'pending';
        if (inProgress) {
          ownsBusy.current = true;
          useSessionStore.getState().setBusy(true);
        } else if (ownsBusy.current) {
          ownsBusy.current = false;
          useSessionStore.getState().setBusy(false);
        }
      } catch {
        if (active) setError('Worker status unavailable. Retry cancellation if a review was running.');
      } finally {
        if (active) timer = setTimeout(update, 1000);
      }
    };
    void update();
    return () => {
      active = false;
      controller.abort();
      clearTimeout(timer);
      if (ownsBusy.current) {
        ownsBusy.current = false;
        void localFetch(`/sessions/${sessionId}/review/cancel`, { method: 'POST' });
      }
    };
  }, [sessionId]);

  const act = async (cancel: boolean) => {
    if (!sessionId || submitting || (!cancel && busy)) return;
    const current = sessionId;
    setSubmitting(true);
    setError('');
    try {
      const response = await localFetch(`/sessions/${current}/review${cancel ? '/cancel' : ''}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: cancel ? undefined : JSON.stringify({ prompt, inference_confirmed: true }),
      });
      if (!response.ok) throw new Error('Review request failed; check the server and session status.');
      const next: Review = await response.json();
      if (useSessionStore.getState().sessionId !== current) return;
      setReview(next);
      ownsBusy.current = next.status === 'pending' || next.status === 'running';
      useSessionStore.getState().setBusy(ownsBusy.current);
    } catch (failure) {
      if (useSessionStore.getState().sessionId === current) setError(failure instanceof Error ? failure.message : 'Review unavailable');
    } finally {
      setSubmitting(false);
    }
  };

  const getStatusStyle = (status: string) => {
    switch (status) {
      case 'running': return 'text-bifang-warning animate-pulse';
      case 'pending': return 'text-bifang-warning';
      case 'completed': return 'text-bifang-success';
      case 'failed': return 'text-bifang-brand-red';
      default: return 'text-bifang-text-muted';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running': return <Loader2 className="w-4 h-4 animate-spin" />;
      case 'pending': return <Loader2 className="w-4 h-4" />;
      case 'completed': return <CheckCircle className="w-4 h-4" />;
      case 'failed': return <AlertTriangle className="w-4 h-4" />;
      default: return <MessageSquare className="w-4 h-4" />;
    }
  };

  return (
    <details className="border-b border-bifang-border p-4 bg-bifang-panel/50 animate-in">
      <summary className="cursor-pointer flex items-center gap-2 text-h5 text-bifang-text-primary">
        <Eye className="w-5 h-5 text-bifang-brand-orange" />
        Read-only team review
        <span className={`ml-2 text-caption font-medium ${getStatusStyle(review.status)}`}>{review.status}</span>
      </summary>

      <dialog ref={budgetDialog} aria-labelledby="review-budget-title" onCancel={(event) => { event.preventDefault(); setConfirming(false); }} className="m-auto max-w-lg rounded-2xl border-bifang-border bg-bifang-panel p-6 text-bifang-text-primary shadow-2xl glass-strong">
        <h2 id="review-budget-title" className="text-h4 text-bifang-text-primary">Start two read-only workers?</h2>
        <p className="mt-3 text-body-sm text-bifang-text-secondary">This can use up to eight model requests and provider credits. Workers can inspect files, but cannot edit or execute commands. Their analysis is not verified test evidence.</p>
        <div className="mt-5 flex justify-end gap-3">
          <button type="button" className="btn-secondary" autoFocus onClick={() => setConfirming(false)}>Not now</button>
          <button type="button" className="btn-primary" disabled={busy || submitting} onClick={() => { setConfirming(false); void act(false); }}>Confirm review budget</button>
        </div>
      </dialog>

      <p className="mt-2 text-caption text-bifang-text-muted">Investigator + reviewer. Up to four model steps each. Analysis is not verified test evidence.</p>

      <label className="mt-3 block text-caption text-bifang-text-muted" htmlFor="review-task">Subtask brief</label>
      <textarea id="review-task" className="input mt-1 max-h-32" maxLength={4000} rows={3} value={prompt} disabled={running || submitting} onChange={(event) => setPrompt(event.target.value)} />

      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="btn-secondary" disabled={!sessionId || busy || submitting || !prompt.trim()} onClick={() => setConfirming(true)}>
          <MessageSquare className="w-4 h-4 mr-1.5" />
          Start two workers
        </button>
        <button type="button" className="btn-secondary" disabled={!running || submitting} onClick={() => void act(true)}>
          <X className="w-4 h-4 mr-1.5" />
          Cancel workers
        </button>
      </div>

      {!sessionId && <p className="mt-2 text-caption text-bifang-text-muted">Start a chat in your workspace to create a session first.</p>}
      {error && <p role="alert" className="mt-2 text-body-sm text-bifang-brand-red animate-in">{error}</p>}

      <div aria-live="polite" className="mt-4 grid gap-3">
        {review.workers.map((worker) => (
          <article key={worker.role} className="rounded-xl border border-bifang-border bg-bifang-surface p-4 animate-in stagger-1 panel-hover">
            <div className="flex items-center gap-2 mb-2">
              <h3 className="text-h5 text-bifang-text-primary">{worker.role}</h3>
              <span className={`ml-auto flex items-center gap-1.5 text-caption font-medium ${getStatusStyle(worker.status)}`}>
                {getStatusIcon(worker.status)}
                {worker.status}
              </span>
            </div>
            <p className="text-caption text-bifang-warning mb-2">Unverified model analysis</p>
            <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words text-code text-bifang-text-secondary bg-bifang-canvas border border-bifang-border p-3 rounded-lg">{worker.analysis}</pre>
            <p className="mt-2 text-caption text-bifang-text-muted">{worker.routing.length} model receipts · {worker.observations.length} observed reads/searches</p>
            {worker.observations.map((observation, index) => (
              <p key={index} className="mt-1 break-all text-caption text-bifang-text-muted font-mono">
                {observation.tool} {observation.path}{observation.start ? `:${observation.start}–${observation.end}` : ''} · SHA-256 {observation.result_sha256}
              </p>
            ))}
          </article>
        ))}
      </div>
    </details>
  );
}