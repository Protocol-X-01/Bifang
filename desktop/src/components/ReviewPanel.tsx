import { useEffect, useRef, useState } from 'react';
import { useSessionStore } from '../stores/bifangStore';

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
        const response = await fetch(`http://127.0.0.1:8000/sessions/${sessionId}/review`, { signal: controller.signal });
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
        void fetch(`http://127.0.0.1:8000/sessions/${sessionId}/review/cancel`, { method: 'POST' });
      }
    };
  }, [sessionId]);

  const act = async (cancel: boolean) => {
    if (!sessionId || submitting || (!cancel && busy)) return;
    const current = sessionId;
    setSubmitting(true);
    setError('');
    try {
      const response = await fetch(`http://127.0.0.1:8000/sessions/${current}/review${cancel ? '/cancel' : ''}`, {
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

  return <details className="border-b border-surface-800 p-4">
    <summary className="cursor-pointer text-sm font-semibold">Read-only team review · {review.status}</summary>
    <dialog ref={budgetDialog} aria-labelledby="review-budget-title" onCancel={(event) => { event.preventDefault(); setConfirming(false); }}
      className="m-auto max-w-lg rounded-2xl border border-surface-700 bg-surface-900 p-6 text-white shadow-xl backdrop:bg-black/70">
      <h2 id="review-budget-title" className="text-lg font-semibold">Start two read-only workers?</h2>
      <p className="mt-3 text-sm">This can use up to eight model requests and provider credits. Workers can inspect files, but cannot edit or execute commands. Their analysis is not verified test evidence.</p>
      <div className="mt-5 flex justify-end gap-3">
        <button type="button" className="btn-secondary" autoFocus onClick={() => setConfirming(false)}>Not now</button>
        <button type="button" className="btn-primary" disabled={busy || submitting} onClick={() => { setConfirming(false); void act(false); }}>Confirm review budget</button>
      </div>
    </dialog>
    <p className="mt-2 text-xs text-surface-400">Investigator + reviewer. Up to four model steps each. Analysis is not verified test evidence.</p>
    <label className="mt-3 block text-xs" htmlFor="review-task">Subtask brief</label>
    <textarea id="review-task" className="mt-1 w-full rounded border border-surface-700 bg-surface-900 p-2 text-sm" maxLength={4000}
      rows={3} value={prompt} disabled={running || submitting} onChange={(event) => setPrompt(event.target.value)} />
    <div className="mt-2 flex gap-2">
      <button type="button" className="btn-secondary" disabled={!sessionId || busy || submitting || !prompt.trim()} onClick={() => setConfirming(true)}>Start two workers</button>
      <button type="button" className="btn-secondary" disabled={!running || submitting} onClick={() => void act(true)}>Cancel workers</button>
    </div>
    {!sessionId && <p className="mt-2 text-xs text-surface-400">Start a chat in your workspace to create a session first.</p>}
    {error && <p role="alert" className="mt-2 text-sm text-red-300">{error}</p>}
    <div aria-live="polite" className="mt-3 grid gap-3">
      {review.workers.map((worker) => <article key={worker.role} className="rounded border border-surface-700 p-3">
        <h3 className="text-sm font-semibold">{worker.role} · {worker.status}</h3>
        <p className="mt-1 text-xs text-amber-300">Unverified model analysis</p>
        <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words text-xs">{worker.analysis}</pre>
        <p className="mt-2 text-xs text-surface-400">{worker.routing.length} model receipts · {worker.observations.length} observed reads/searches</p>
        {worker.observations.map((observation, index) => <p key={index} className="mt-1 break-all text-xs text-surface-400">
          {observation.tool} {observation.path}{observation.start ? `:${observation.start}–${observation.end}` : ''} · SHA-256 {observation.result_sha256}
        </p>)}
      </article>)}
    </div>
  </details>;
}
