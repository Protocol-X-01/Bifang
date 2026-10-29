import { localFetch } from '../api/localApi';
import { useEffect, useRef, useState } from 'react';
import { useSessionStore } from '../stores/bifangStore';
import { Loader2, AlertTriangle, CheckCircle, Play, X, Code2, Shield, GitBranch, FileText } from 'lucide-react';

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
  const base = `/sessions/${sessionId}/candidate`;

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
        const response = await localFetch(`/sessions/${sessionId}/candidate`, { signal: controller.signal });
        if (!response.ok) throw new Error('Candidate status unavailable.');
        const next: CandidateState = await response.json();
        if (!active || useSessionStore.getState().sessionId !== sessionId) return;
        setState(next);
        const inProgress = ['pending', 'running', 'checking'].includes(next.status);
        if (inProgress) { ownsBusy.current = true; useSessionStore.getState().setBusy(true); }
        else if (ownsBusy.current) { ownsBusy.current = false; useSessionStore.getState().setBusy(false); }
        if (inProgress) {
          const pending = await localFetch(`/sessions/${sessionId}/approval`, { signal: controller.signal });
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
        void localFetch(`/sessions/${sessionId}/candidate/cancel`, { method: 'POST' }).catch(() => {});
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
      const response = await localFetch(`${base}${action === 'start' ? '' : `/${action}`}`, {
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
    const response = await localFetch(`/sessions/${sessionId}/approval`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approval_id: approval.approval_id, approved }),
    }).catch(() => null);
    if (response?.ok) setApproval(null);
    else setError('Could not record the action decision. Retry or cancel the worker.');
  };

  const getStatusStyle = (status: string) => {
    switch (status) {
      case 'running': return 'text-bifang-warning animate-pulse';
      case 'pending': return 'text-bifang-warning';
      case 'ready': return 'text-bifang-brand-orange';
      case 'verified': return 'text-bifang-success';
      case 'check_failed': return 'text-bifang-brand-red';
      default: return 'text-bifang-text-muted';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running': return <Loader2 className="w-4 h-4 animate-spin" />;
      case 'pending': return <Loader2 className="w-4 h-4" />;
      case 'ready': return <Code2 className="w-4 h-4" />;
      case 'verified': return <CheckCircle className="w-4 h-4" />;
      case 'check_failed': return <AlertTriangle className="w-4 h-4" />;
      default: return <Shield className="w-4 h-4" />;
    }
  };

  return (
    <details className="border-b border-bifang-border p-4 bg-bifang-panel/50 animate-in">
      <summary className="cursor-pointer flex items-center gap-2 text-h5 text-bifang-text-primary">
        <Shield className="w-5 h-5 text-bifang-brand-orange" />
        Isolated engineering
        <span className={`ml-2 text-caption font-medium ${getStatusStyle(state.status)}`}>{state.status}</span>
      </summary>

      <p className="mt-2 text-caption text-bifang-text-muted">Selected files → private implementer → independent check → reviewed staging. Original Apply stays separate.</p>

      <label className="mt-3 block text-caption text-bifang-text-muted">Existing source paths, one per line (optional for a new project)
        <textarea aria-label="Candidate source paths" value={files} disabled={running || submitting} onChange={(event) => setFiles(event.target.value)} rows={2} className="input mt-1 h-auto" />
      </label>
      <label className="mt-3 block text-caption text-bifang-text-muted">Editable paths, including new files (blank = selected files)
        <textarea aria-label="Candidate editable paths" value={writable} disabled={running || submitting} onChange={(event) => setWritable(event.target.value)} rows={2} className="input mt-1 h-auto" />
      </label>
      <label className="mt-3 block text-caption text-bifang-text-muted">Engineering brief
        <textarea aria-label="Engineering brief" value={brief} maxLength={4000} disabled={running || submitting} onChange={(event) => setBrief(event.target.value)} rows={2} className="input mt-1 h-auto" />
      </label>

      <div className="mt-3 flex flex-wrap gap-2">
        <button className="btn-secondary" disabled={!sessionId || busy || submitting || (!files.trim() && !writable.trim()) || !brief.trim()} onClick={() => setIntent('start')}>
          <Play className="w-4 h-4 mr-1.5" />
          Prepare candidate
        </button>
        <button className="btn-secondary" disabled={!running || submitting} onClick={() => void act('cancel')}>
          <X className="w-4 h-4 mr-1.5" />
          Cancel candidate work
        </button>
      </div>

      {state.result && (
        <>
          <p className="mt-3 text-caption text-bifang-warning">Unverified implementer analysis</p>
          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-code text-bifang-text-secondary bg-bifang-canvas border border-bifang-border p-3 rounded-lg">{state.result.analysis}</pre>
        </>
      )}

      <label className="mt-3 block text-caption text-bifang-text-muted">Exact check arguments (JSON array)
        <textarea aria-label="Candidate check arguments" value={command} onChange={(event) => setCommand(event.target.value)} disabled={busy || submitting} rows={2} className="input mt-1 h-auto" />
      </label>

      <div className="mt-3 flex flex-wrap gap-2">
        <button className="btn-secondary" disabled={busy || submitting || !['ready', 'verified', 'check_failed'].includes(state.status)} onClick={() => setIntent('check')}>
          <Play className="w-4 h-4 mr-1.5" />
          Run independent check
        </button>
        <button className="btn-secondary" disabled={busy || submitting || !state.candidate_sha256} onClick={() => void act('patch')}>
          <FileText className="w-4 h-4 mr-1.5" />
          Review candidate patch
        </button>
        <button className="btn-secondary" disabled={busy || submitting || state.status !== 'verified' || reviewedHash !== state.candidate_sha256} onClick={() => setIntent('stage')}>
          <GitBranch className="w-4 h-4 mr-1.5" />
          Stage reviewed candidate
        </button>
      </div>

      {state.receipt && (
        <p className="mt-3 break-all text-caption text-bifang-text-secondary">
          Executed check: exit {state.receipt.returncode} · {state.receipt.passed ? 'passed' : 'not passed'} · {state.receipt.scope} · SHA-256 {state.receipt.candidate_sha256}
        </p>
      )}
      {patch && <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words text-code text-bifang-text-secondary bg-bifang-canvas border border-bifang-border p-3 rounded-lg">{patch}</pre>}
      {(error || state.error) && <p role="alert" className="mt-3 text-caption text-bifang-brand-red animate-in">{error || state.error}</p>}

      <dialog ref={dialog} aria-labelledby="candidate-confirm-title" onCancel={(event) => { event.preventDefault(); setIntent(null); }} className="m-auto max-w-xl rounded-2xl border-bifang-border bg-bifang-panel p-6 text-bifang-text-primary shadow-2xl glass-strong">
        <h2 id="candidate-confirm-title" className="text-h4 text-bifang-text-primary">
          {intent === 'start' ? 'Prepare an isolated candidate?' : intent === 'check' ? 'Run this exact check?' : 'Stage this reviewed patch?'}
        </h2>
        <p className="mt-3 text-body-sm text-bifang-text-secondary">
          {intent === 'start'
            ? 'Up to six model steps use provider credits. Only selected files enter the private candidate; each write needs approval.'
            : intent === 'check'
            ? 'The approved command runs on a read-only snapshot in Bubblewrap without network or provider credentials. This proves only that exact check.'
            : 'This copies the checked patch into the isolated session worktree. The original repository still requires the separate Apply action.'}
        </p>
        {intent === 'check' && <pre className="mt-3 whitespace-pre-wrap break-all text-code text-bifang-brand-orange/80 bg-bifang-canvas border border-bifang-border p-3 rounded-lg">{command}</pre>}
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-secondary" autoFocus onClick={() => setIntent(null)}>Not now</button>
          <button className="btn-primary" onClick={() => intent && void act(intent)}>Confirm candidate action</button>
        </div>
      </dialog>

      <dialog ref={approvalDialog} aria-labelledby="candidate-write-title" onCancel={(event) => { event.preventDefault(); void approve(false); }} className="m-auto max-w-xl rounded-2xl border-bifang-border bg-bifang-panel p-6 text-bifang-text-primary shadow-2xl glass-strong">
        <h2 id="candidate-write-title" className="text-h4 text-bifang-text-primary">Approve candidate write?</h2>
        <pre className="mt-3 whitespace-pre-wrap break-all text-code text-bifang-brand-orange/80 bg-bifang-canvas border border-bifang-border p-3 rounded-lg">{approval?.action}</pre>
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-secondary" autoFocus onClick={() => void approve(false)}>Deny candidate write</button>
          <button className="btn-primary" onClick={() => void approve(true)}>Approve candidate write</button>
        </div>
      </dialog>
    </details>
  );
}