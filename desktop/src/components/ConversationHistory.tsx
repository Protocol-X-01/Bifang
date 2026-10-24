import { useEffect, useRef, useState } from 'react';
import { Clock3, History, Loader2 } from 'lucide-react';
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
    }} className="m-auto w-full max-w-2xl rounded-2xl border border-border bg-card p-6 text-card-foreground shadow-xl backdrop:bg-black/70">
      <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-brand-primary"><History className="h-4 w-4" />Pick up where you left off</p>
      <h2 id="history-title" className="mt-2 text-2xl font-semibold">Saved conversations</h2>
      <p className="mt-3 text-sm text-muted-foreground">History from this project only. Resuming restores context, not an old worktree. No commands or approvals are replayed.</p>
      <div className="my-5 max-h-[50vh] space-y-3 overflow-y-auto">
        {!loading && !error && items.length === 0 && <p className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">No saved conversations yet. Your first completed chat will appear here.</p>}
        {items.map((item) => (
          <div key={item.conversation_id} className="flex items-center justify-between gap-4 rounded-xl border border-border bg-background p-4">
            <div className="min-w-0">
              <p className="truncate font-mono text-sm">Conversation {item.conversation_id.slice(0, 8)}</p>
              <p className="mt-2 flex items-center gap-2 text-xs text-muted-foreground"><Clock3 className="h-3 w-3" />{new Date(item.updated_at * 1000).toLocaleString()}</p>
              <p className="mt-1 text-xs text-muted-foreground">{item.turn_count} recorded {item.turn_count === 1 ? 'turn' : 'turns'}</p>
            </div>
            <button type="button" className="btn-primary shrink-0" disabled={busy || loading || selected !== null}
              aria-label={`Resume conversation ${item.conversation_id.slice(0, 8)}`} onClick={() => resume(item.conversation_id)}>
              {selected === item.conversation_id ? 'Restoring…' : 'Resume'}
            </button>
          </div>
        ))}
        {loading && <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Loading saved conversations…</p>}
        {error && <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</p>}
        {hasMore && <button type="button" className="btn-secondary" disabled={busy || loading} onClick={() => setOffset((previous) => previous + 20)}>Load older conversations</button>}
      </div>
      <div className="flex justify-end"><button type="button" className="btn-secondary" autoFocus disabled={busy} onClick={onClose}>Close</button></div>
    </dialog>
  );
}
