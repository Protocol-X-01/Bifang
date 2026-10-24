import { useEffect, useRef, useState } from 'react';
import { useSessionStore } from '../stores/bifangStore';

type CandidateState = {
  status: string;
  candidate_sha256?: string;
  changed_files?: string[];
  error?: string;
  result?: { analysis: string; verification: string };
  receipt?: { passed: boolean; returncode: number; candidate_sha256: string; scope: string };
};
type Intent = 'start' | 'check' | 'stage';

export function CandidatePanel() {
  const sessionId = useSessionStore((state) => state.sessionId);
  const busy = useSessionStore((state) => state.busy);
  const [state, setState] = useState<CandidateState>({ status: 'idle' });
  const [files, setFiles] = useState('');
  const [writable, setWritable] = useState('');
  const [brief, setBrief] = useState('Implement the requested fix in the selected files.');
  const [command, setCommand] = useState('["/usr/bin/python3", "-B", "-m", "unittest", "discover"]');
  const [patch, setPatch] = useState('');
  const [reviewedHash, setReviewedHash] = useState('');
  const [error, setError] = useState('');
  const [intent, setIntent] = useState<Intent | null>(null);
  const [approval, setApproval] = useState<{ approval_id: string; action: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const approvalDialog = useRef<HTMLDialogElement>(null);
  const ownsBusy = useRef(false);
  const running = ['pending', 'running', 'checking'].includes(state.status);
  const paths = (value: string) => value.split('\n').map((entry) => entry.trim()).filter(Boolean);
  const base = `http://127.0.0.1:8000/sessions/${sessionId}/candidate`;

  useEffect(() => {
    if (intent) dialog.current?.showModal();
    else dialog.current?.close();
  }, [intent]);
  useEffect(() => {
    if (approval) approvalDialog.current?.showModal();
    else approvalDialog.current?.close();
  }, [approval]);
  useEffect(() => {
    setState({ status: 'idle' }); setPatch(''); setReviewedHash(''); setError(''); setIntent(null); setApproval(null);
    if (!sessionId) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    const update = async () => {
      try {
        const response = await fetch(`http://127.0.0.1:8000/sessions/${sessionId}/candidate`, { signal: controller.signal });
        if (!response.ok) throw new Error('Candidate status unavailable.');
        const next: CandidateState = await response.json();
        if (!active || useSessionStore.getState().sessionId !== sessionId) return;
        setState(next);
        const inProgress = ['pending', 'running', 'checking'].includes(next.status);
        if (inProgress) { ownsBusy.current = true; useSessionStore.getState().setBusy(true); }
        else if (ownsBusy.current) { ownsBusy.current = false; useSessionStore.getState().setBusy(false); }
        if (inProgress) {
          const pending = await fetch(`http://127.0.0.1:8000/sessions/${sessionId}/approval`, { signal: controller.signal });
          if (pending.ok) {
            const requested = await pending.json();
            if (active && useSessionStore.getState().sessionId === sessionId) {
              setApproval(typeof requested.approval_id === 'string' ? requested : null);
            }
          }
        } else setApproval(null);
      } catch {
        if (active) setError('Candidate status unavailable. Retry cancellation if work was running.');
      } finally {
        if (active) timer = setTimeout(update, 1000);
      }
    };
    void update();
    return () => {
      active = false; controller.abort(); clearTimeout(timer);
      if (ownsBusy.current) {
        ownsBusy.current = false;
        void fetch(`http://127.0.0.1:8000/sessions/${sessionId}/candidate/cancel`, { method: 'POST' }).catch(() => {});
      }
    };
  }, [sessionId]);

  const act = async (action: Intent | 'cancel' | 'patch') => {
    if (!sessionId || submitting || (busy && action !== 'cancel')) return;
    setIntent(null); setSubmitting(true); setError('');
    try {
      let body;
      if (action === 'start') {
        const selected = paths(files);
        body = { prompt: brief, files: selected, writable: writable.trim() ? paths(writable) : selected, inference_confirmed: true };
        setPatch(''); setReviewedHash('');
      } else if (action === 'check') {
        const argumentsList = JSON.parse(command);
        if (!Array.isArray(argumentsList) || !argumentsList.length || argumentsList.some((part) => typeof part !== 'string' || !part)) {
          throw new Error('Use a nonempty JSON array of command arguments.');
        }
        body = { command: argumentsList, confirmed: true };
      } else if (action === 'stage') body = { candidate_sha256: reviewedHash, confirmed: true };
      const response = await fetch(`${base}${action === 'start' ? '' : `/${action}`}`, {
        method: action === 'patch' ? 'GET' : 'POST', headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!response.ok) throw new Error('Request unavailable: check selected paths, sandbox, current evidence and worktree status.');
      const next = await response.json();
      if (useSessionStore.getState().sessionId !== sessionId) return;
      if (action === 'patch') { setPatch(next.patch); setReviewedHash(next.candidate_sha256); }
      else {
        setState(next);
        ownsBusy.current = ['pending', 'running', 'checking'].includes(next.status);
        useSessionStore.getState().setBusy(ownsBusy.current);
      }
    } catch (failure) {
      if (useSessionStore.getState().sessionId === sessionId) setError(failure instanceof Error ? failure.message : 'Candidate unavailable');
    } finally { setSubmitting(false); }
  };

  const approve = async (approved: boolean) => {
    if (!approval || !sessionId) return;
    const response = await fetch(`http://127.0.0.1:8000/sessions/${sessionId}/approval`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approval_id: approval.approval_id, approved }),
    }).catch(() => null);
    if (response?.ok) setApproval(null);
    else setError('Could not record the action decision. Retry or cancel the worker.');
  };

  return <details className="border-b border-surface-800 p-4">
    <summary className="cursor-pointer text-sm font-semibold">Isolated engineering · {state.status}</summary>
    <p className="mt-2 text-xs text-surface-400">Selected files → private implementer → independent check → reviewed staging. Original Apply stays separate.</p>
    <label className="mt-3 block text-xs">Source paths, one per line<textarea aria-label="Candidate source paths" value={files} disabled={running || submitting} onChange={(event) => setFiles(event.target.value)} rows={2} className="input mt-1 h-auto" /></label>
    <label className="mt-3 block text-xs">Editable paths, including new files (blank = selected files)<textarea aria-label="Candidate editable paths" value={writable} disabled={running || submitting} onChange={(event) => setWritable(event.target.value)} rows={2} className="input mt-1 h-auto" /></label>
    <label className="mt-3 block text-xs">Engineering brief<textarea aria-label="Engineering brief" value={brief} maxLength={4000} disabled={running || submitting} onChange={(event) => setBrief(event.target.value)} rows={2} className="input mt-1 h-auto" /></label>
    <div className="mt-3 flex gap-2">
      <button className="btn-secondary" disabled={!sessionId || busy || submitting || !files.trim() || !brief.trim()} onClick={() => setIntent('start')}>Prepare candidate</button>
      <button className="btn-secondary" disabled={!running || submitting} onClick={() => void act('cancel')}>Cancel candidate work</button>
    </div>
    {state.result && <><p className="mt-3 text-xs text-amber-300">Unverified implementer analysis</p><pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-xs">{state.result.analysis}</pre></>}
    <label className="mt-3 block text-xs">Exact check arguments (JSON array)<textarea aria-label="Candidate check arguments" value={command} onChange={(event) => setCommand(event.target.value)} disabled={busy || submitting} rows={2} className="input mt-1 h-auto" /></label>
    <div className="mt-3 flex flex-wrap gap-2">
      <button className="btn-secondary" disabled={busy || submitting || !['ready', 'verified', 'check_failed'].includes(state.status)} onClick={() => setIntent('check')}>Run independent check</button>
      <button className="btn-secondary" disabled={busy || submitting || !state.candidate_sha256} onClick={() => void act('patch')}>Review candidate patch</button>
      <button className="btn-secondary" disabled={busy || submitting || state.status !== 'verified' || reviewedHash !== state.candidate_sha256} onClick={() => setIntent('stage')}>Stage reviewed candidate</button>
    </div>
    {state.receipt && <p className="mt-3 break-all text-xs">Executed check: exit {state.receipt.returncode} · {state.receipt.passed ? 'passed' : 'not passed'} · {state.receipt.scope} · SHA-256 {state.receipt.candidate_sha256}</p>}
    {patch && <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs">{patch}</pre>}
    {(error || state.error) && <p role="alert" className="mt-3 text-xs text-red-300">{error || state.error}</p>}
    <dialog ref={dialog} aria-labelledby="candidate-confirm-title" onCancel={(event) => { event.preventDefault(); setIntent(null); }} className="m-auto max-w-xl rounded-2xl border border-border bg-card p-6 text-card-foreground backdrop:bg-black/70">
      <h2 id="candidate-confirm-title" className="font-semibold">{intent === 'start' ? 'Prepare an isolated candidate?' : intent === 'check' ? 'Run this exact check?' : 'Stage this reviewed patch?'}</h2>
      <p className="mt-3 text-sm">{intent === 'start' ? 'Up to six model steps use provider credits. Only selected files enter the private candidate; each write needs approval.' : intent === 'check' ? 'The approved command runs on a read-only snapshot in Bubblewrap without network or provider credentials. This proves only that exact check.' : 'This copies the checked patch into the isolated session worktree. The original repository still requires the separate Apply action.'}</p>
      {intent === 'check' && <pre className="mt-3 whitespace-pre-wrap break-all text-xs">{command}</pre>}
      <div className="mt-4 flex justify-end gap-2"><button className="btn-secondary" autoFocus onClick={() => setIntent(null)}>Not now</button><button className="btn-primary" onClick={() => intent && void act(intent)}>Confirm candidate action</button></div>
    </dialog>
    <dialog ref={approvalDialog} aria-labelledby="candidate-write-title" onCancel={(event) => { event.preventDefault(); void approve(false); }} className="m-auto max-w-xl rounded-2xl border border-border bg-card p-6 text-card-foreground backdrop:bg-black/70">
      <h2 id="candidate-write-title" className="font-semibold">Approve candidate write?</h2><pre className="mt-3 whitespace-pre-wrap break-all text-xs">{approval?.action}</pre>
      <div className="mt-4 flex justify-end gap-2"><button className="btn-secondary" autoFocus onClick={() => void approve(false)}>Deny candidate write</button><button className="btn-primary" onClick={() => void approve(true)}>Approve candidate write</button></div>
    </dialog>
  </details>;
}
