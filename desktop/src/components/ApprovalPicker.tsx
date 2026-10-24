import { useRef } from 'react';
import { ChevronDown, ShieldCheck, Zap } from 'lucide-react';
import type { ApprovalMode } from '../api/approvals';

const descriptions = {
  manual: 'Review edits, commands and external tool requests before they run.',
  auto: 'Auto-approve ordinary source edits in disposable worktrees. Commands, sensitive files and external tools still ask.',
  full: 'Tool requests are automatically approved. Existing path, command and sandbox restrictions still apply.',
};

export function ApprovalPicker({ mode, busy, onChange, onPause, pausing }: {
  mode: ApprovalMode; busy: boolean; onChange: (mode: ApprovalMode) => void;
  onPause?: () => void; pausing: boolean;
}) {
  const confirmation = useRef<HTMLDialogElement>(null);
  return (
    <div className={`border-b px-4 py-3 ${mode === 'full' ? 'border-amber-400/30 bg-amber-400/5' : 'border-surface-800'}`}>
      <div className="flex items-center gap-3">
        {mode === 'full' ? <Zap aria-hidden="true" className="h-4 w-4 text-amber-300" />
          : <ShieldCheck aria-hidden="true" className="h-4 w-4 text-emerald-300" />}
        <label htmlFor="approval-mode" className="text-xs font-semibold uppercase tracking-wide text-surface-400">Approvals</label>
        <div className="relative min-w-0 flex-1">
        <select id="approval-mode" value={mode} disabled={busy} aria-describedby="approval-description"
          className="w-full appearance-none rounded-lg border border-surface-700 bg-surface-900 px-3 py-2 pr-9 text-sm text-surface-100 disabled:opacity-50"
          onChange={(event) => {
            const next = event.target.value as ApprovalMode;
            if (next === 'full') confirmation.current?.showModal();
            else onChange(next);
          }}>
          <option value="manual">Off · manual review</option>
          <option value="auto">Auto · workspace edits</option>
          <option value="full">Full tool approval</option>
        </select>
        <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-surface-400" />
        </div>
      </div>
      <p id="approval-description" role="status" className={`mt-2 text-xs ${mode === 'full' ? 'text-amber-200' : 'text-surface-400'}`}>{descriptions[mode]}</p>
      {onPause && mode !== 'manual' && <button type="button" onClick={onPause} disabled={pausing}
        className="mt-2 text-xs font-semibold text-amber-200 underline disabled:opacity-50"
        title="The current action can finish; subsequent actions return to manual review.">{pausing ? 'Pausing…' : 'Pause auto approvals'}</button>}
      <dialog ref={confirmation} aria-labelledby="full-approval-title"
        className="m-auto w-full max-w-lg rounded-2xl border border-amber-400/30 bg-card p-6 text-card-foreground shadow-xl backdrop:bg-black/70">
        <h2 id="full-approval-title" className="text-xl font-semibold">Enable full tool approval?</h2>
        <p className="mt-4 text-sm text-surface-300">Bifang can run commands and use external tools without asking each time. These tools use their existing permissions and may change data, contact services or consume credits. Choose this for work you trust.</p>
        <p className="mt-3 text-sm text-surface-400">Reviewing and applying the final patch stays separate. This choice resets for a new chat, workspace, restored conversation or page reload.</p>
        <div className="mt-6 flex justify-end gap-3">
          <button type="button" className="btn-secondary" autoFocus onClick={() => confirmation.current?.close()}>Keep current mode</button>
          <button type="button" className="btn-primary" onClick={() => {
            onChange('full');
            confirmation.current?.close();
          }}>Enable full approval</button>
        </div>
      </dialog>
    </div>
  );
}
