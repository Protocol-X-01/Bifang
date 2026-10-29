import { useEffect, useRef, useState } from 'react';
import { Clock, History, Loader2 } from 'lucide-react';
import { savedConversations, type SavedConversation } from '../api/conversations';

interface Props {
  workspace: string;
  busy: boolean;
  onResume: (identity: string) => Promise<boolean>;
  onClose: () => void;
}

export function ConversationHistory({ workspace, busy, onResume, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [items, setItems] = useState<SavedConversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    dialog.current?.showModal();
    return () => dialog.current?.close();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    savedConversations(workspace, offset, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return;
        setItems((previous) => {
          const merged = new Map((offset === 0 ? [] : previous).map((item) => [item.conversation_id, item]));
          page.forEach((item) => merged.set(item.conversation_id, item));
          return [...merged.values()];
        });
        setHasMore(page.length === 20);
      })
      .catch((failure) => { if (!controller.signal.aborted) setError(String(failure)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [workspace, offset]);

  const resume = async (identity: string) => {
    if (busy || loading) return;
    setError('');
    setSelected(identity);
    try {
      if (await onResume(identity)) onClose();
    } catch (failure) {
      setError(String(failure));
    } finally {
      setSelected(null);
    }
  };

  return (
    <dialog ref={dialog} aria-labelledby="history-title" onCancel={(event) => {
      event.preventDefault();
      if (!busy) onClose();
    }} className="m-auto w-full max-w-2xl rounded-2xl border-bifang-border bg-bifang-panel p-6 text-bifang-text-primary shadow-2xl glass-strong">
      <p className="flex items-center gap-2 text-overline text-bifang-brand-orange"><History className="w-4 h-4" />Pick up where you left off</p>
      <h2 id="history-title" className="mt-2 text-h4 text-bifang-text-primary">Saved conversations</h2>
      <p className="mt-3 text-body-sm text-bifang-text-secondary">History from this project only. Resuming restores context, not an old worktree. No commands or approvals are replayed.</p>
      <div className="my-5 max-h-[50vh] space-y-3 overflow-y-auto">
        {!loading && !error && items.length === 0 && (
          <p className="rounded-xl border-2 border-dashed border-bifang-border p-6 text-center text-body-sm text-bifang-text-muted">No saved conversations yet. Your first completed chat will appear here.</p>
        )}
        {items.map((item) => (
          <div key={item.conversation_id} className="flex items-center justify-between gap-4 rounded-xl border-bifang-border bg-bifang-surface p-4 animate-in panel-hover">
            <div className="min-w-0">
              <p className="truncate font-mono text-body-sm text-bifang-text-primary">Conversation {item.conversation_id.slice(0, 8)}</p>
              <p className="mt-2 flex items-center gap-2 text-caption text-bifang-text-muted"><Clock className="w-3.5 h-3.5" />{new Date(item.updated_at * 1000).toLocaleString()}</p>
              <p className="mt-1 text-caption text-bifang-text-muted">{item.turn_count} recorded {item.turn_count === 1 ? 'turn' : 'turns'}</p>
            </div>
            <button type="button" className="btn-primary shrink-0" disabled={busy || loading || selected !== null}
              aria-label={`Resume conversation ${item.conversation_id.slice(0, 8)}`} onClick={() => resume(item.conversation_id)}>
              {selected === item.conversation_id ? 'Restoring…' : 'Resume'}
            </button>
          </div>
        ))}
        {loading && <p role="status" className="flex items-center gap-2 text-body-sm text-bifang-text-muted"><Loader2 className="w-4 h-4 animate-spin text-bifang-brand-orange" />Loading saved conversations…</p>}
        {error && <p role="alert" className="rounded-lg border-bifang-brand-red/30 bg-bifang-brand-red/10 p-3 text-body-sm text-bifang-brand-red">{error}</p>}
        {hasMore && <button type="button" className="btn-secondary btn-sm" disabled={busy || loading} onClick={() => setOffset((previous) => previous + 20)}><Loader2 className="w-3.5 h-3.5 mr-1.5" /> Load older conversations</button>}
      </div>
      <div className="flex justify-end"><button type="button" className="btn-secondary" autoFocus disabled={busy} onClick={onClose}>Close</button></div>
    </dialog>
  );
}