import { useRef } from 'react';
import { ChevronDown, ShieldCheck, Zap, AlertTriangle } from 'lucide-react';
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

  const modeColors = {
    manual: { icon: <ShieldCheck className="w-4 h-4 text-bifang-success" />, border: 'border-bifang-border', desc: 'text-bifang-text-secondary' },
    auto: { icon: <Zap className="w-4 h-4 text-bifang-brand-orange" />, border: 'border-bifang-brand-orange/30 bg-bifang-brand-orange/5', desc: 'text-bifang-brand-orange' },
    full: { icon: <Zap className="w-4 h-4 text-bifang-brand-red" />, border: 'border-bifang-brand-red/30 bg-bifang-brand-red/5', desc: 'text-bifang-brand-red' },
  };

  const current = modeColors[mode];

  return (
    <div className={`border-b px-4 py-3 ${current.border}`}>
      <div className="flex items-center gap-3">
        <span aria-hidden="true">{current.icon}</span>
        <label htmlFor="approval-mode" className="text-overline text-bifang-brand-orange">Approvals</label>
        <div className="relative min-w-0 flex-1">
          <select id="approval-mode" value={mode} disabled={busy} aria-describedby="approval-description"
            onChange={(event) => {
              const next = event.target.value as ApprovalMode;
              if (next === 'full') confirmation.current?.showModal();
              else onChange(next);
            }}
            className="input appearance-none pr-10">
            <option value="manual">Off · manual review</option>
            <option value="auto">Auto · workspace edits</option>
            <option value="full">Full tool approval</option>
          </select>
          <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-bifang-text-muted" />
        </div>
      </div>
      <p id="approval-description" role="status" className={`mt-2 text-caption ${current.desc}`}>{descriptions[mode]}</p>
      {mode !== 'manual' && (
        <button type="button" onClick={() => onPause?.()} disabled={pausing} className="mt-2 text-caption font-semibold text-bifang-brand-orange underline disabled:opacity-50" title="The current action can finish; subsequent actions return to manual review.">{pausing ? 'Pausing…' : 'Pause auto approvals'}</button>
      )}
      <dialog ref={confirmation} aria-labelledby="full-approval-title" className="m-auto max-w-lg rounded-2xl border-bifang-brand-red/30 bg-bifang-panel p-6 text-bifang-text-primary shadow-2xl glass-strong">
        <h2 id="full-approval-title" className="text-h4 text-bifang-text-primary flex items-center gap-2"><AlertTriangle className="w-5 h-5 text-bifang-brand-red" />Enable full tool approval?</h2>
        <p className="mt-4 text-body-sm text-bifang-text-secondary">Bifang can run commands and use external tools without asking each time. These tools use their existing permissions and may change data, contact services or consume credits. Choose this for work you trust.</p>
        <p className="mt-3 text-body-sm text-bifang-text-muted">Reviewing and applying the final patch stays separate. This choice resets for a new chat, workspace, restored conversation or page reload.</p>
        <div className="mt-6 flex justify-end gap-3">
          <button type="button" className="btn-secondary" autoFocus onClick={() => confirmation.current?.close()}>Keep current mode</button>
          <button type="button" className="btn-primary" onClick={() => { onChange('full'); confirmation.current?.close(); }}>Enable full approval</button>
        </div>
      </dialog>
    </div>
  );
}