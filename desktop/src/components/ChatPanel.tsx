import { useState, useRef, useEffect } from 'react';
import { Send, Loader2, MessageSquare, History } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { sessionCacheWarning, useSessionStore, useWorkspaceStore } from '../stores/bifangStore';
import { parseRoutingReceipts, sessionHistory, type SessionMessage } from '../api/conversations';
import type { ModelSelection } from '../api/models';
import { chatErrorMessage } from '../api/errors';
import { ConversationHistory } from './ConversationHistory';
import { ModelPicker } from './ModelPicker';
import { ApprovalPicker } from './ApprovalPicker';
import { ReviewPanel } from './ReviewPanel';
import { CandidatePanel } from './CandidatePanel';
import { approvalRequest, type ApprovalMode } from '../api/approvals';

export function ChatPanel() {
  const [input, setInput] = useState('');
  const [modelSelection, setModelSelection] = useState<ModelSelection | null>(null);
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>('manual');
  const [isPausing, setIsPausing] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [isResuming, setIsResuming] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyRestored, setHistoryRestored] = useState(false);
  const [cacheWarning, setCacheWarning] = useState(sessionCacheWarning);
  const [pendingApproval, setPendingApproval] = useState<{ action: string; resolve: (approved: boolean) => void } | null>(null);
  const approvalDialog = useRef<HTMLDialogElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { sessionId, setSessionId, messages, addMessage, clearMessages, setBusy, replaceConversation } = useSessionStore();
  const workspacePath = useWorkspaceStore((state) => state.workspacePath);
  const setActiveWorkspace = useWorkspaceStore((state) => state.setActiveWorkspace);
  const previousWorkspace = useRef(workspacePath);

  useEffect(() => {
    const warn = () => setCacheWarning(true);
    window.addEventListener('bifang-cache-warning', warn);
    return () => window.removeEventListener('bifang-cache-warning', warn);
  }, []);

  useEffect(() => {
    if (pendingApproval) approvalDialog.current?.showModal();
    else approvalDialog.current?.close();
  }, [pendingApproval]);

  const resolveApproval = (approved: boolean) => {
    pendingApproval?.resolve(approved);
    setPendingApproval(null);
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (previousWorkspace.current !== workspacePath) {
      setSessionId(null);
      clearMessages();
      setHistoryOpen(false);
      setHistoryRestored(false);
      setApprovalMode('manual');
      setActiveWorkspace(workspacePath);
      previousWorkspace.current = workspacePath;
    }
  }, [workspacePath, setSessionId, clearMessages, setActiveWorkspace]);

  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    const stillCurrent = () => active && useSessionStore.getState().sessionId === sessionId &&
      useWorkspaceStore.getState().workspacePath === workspacePath;
    fetch(`http://127.0.0.1:8000/sessions/${sessionId}`)
      .then(async (response) => {
        if (!stillCurrent()) return;
        if (!response.ok) {
          setSessionId(null);
          clearMessages();
          setActiveWorkspace(workspacePath);
          return;
        }
        const session = await response.json();
        if (stillCurrent()) setActiveWorkspace(session.workspace);
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [sessionId, setSessionId, clearMessages, setActiveWorkspace, workspacePath]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || useSessionStore.getState().busy) return;
    setBusy(true);

    const userMessage = input;
    setInput('');
    setIsLoading(true);

    addMessage({ role: 'user', content: userMessage });

    try {
      if (!workspacePath) throw new Error('Choose a workspace before starting a chat.');
      let activeSessionId = sessionId;
      if (!activeSessionId) {
        const created = await fetch('http://127.0.0.1:8000/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ workspace: workspacePath, max_steps: 12 }),
        });
        if (!created.ok) throw new Error((await created.text()) || 'Could not create a session.');
        const session = await created.json();
        activeSessionId = session.session_id;
        setSessionId(activeSessionId);
        setActiveWorkspace(session.workspace);
      }

      let chatFinished = false;
      const chatRequest = fetch(`http://127.0.0.1:8000/sessions/${activeSessionId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: userMessage, selection: modelSelection, ...approvalRequest(approvalMode) }),
      });
      const pollApprovals = async () => {
        while (!chatFinished) {
          const stateResponse = await fetch(`http://127.0.0.1:8000/sessions/${activeSessionId}/approval`);
          if (!stateResponse.ok) break;
          const approval = await stateResponse.json();
          if (approval.approval_id) {
            const approved = await new Promise<boolean>((resolve) => {
              setPendingApproval({ action: approval.action, resolve });
            });
            await fetch(`http://127.0.0.1:8000/sessions/${activeSessionId}/approval`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ approval_id: approval.approval_id, approved }),
            });
          } else {
            await new Promise((resolve) => window.setTimeout(resolve, 400));
          }
        }
      };
      const approvalPolling = pollApprovals();
      const response = await chatRequest;
      chatFinished = true;
      await approvalPolling;
      if (!response.ok) throw new Error(await chatErrorMessage(response));
      const data = await response.json();
      addMessage({ role: 'assistant', content: data.response, routing: parseRoutingReceipts(data.routing) });
    } catch (error) {
      addMessage({ role: 'assistant', content: `Error: ${error}` });
    } finally {
      setIsLoading(false);
      setBusy(false);
    }
  };

  const handlePauseApprovals = async () => {
    if (!sessionId || isPausing) return;
    setIsPausing(true);
    try {
      const response = await fetch(`http://127.0.0.1:8000/sessions/${sessionId}/pause-auto-approval`, { method: 'POST' });
      if (!response.ok) throw new Error('Could not pause automatic approvals.');
      setApprovalMode('manual');
    } catch (error) {
      window.alert(String(error));
    } finally {
      setIsPausing(false);
    }
  };

  const handleNewChat = async () => {
    if (useSessionStore.getState().busy) return;
    setBusy(true);
    setIsResetting(true);
    try {
      if (sessionId) {
        const diffResponse = await fetch(`http://127.0.0.1:8000/sessions/${sessionId}/diff`);
        if (!diffResponse.ok && diffResponse.status !== 404) throw new Error('Could not check the current workspace changes.');
        if (diffResponse.ok) {
          const { diff } = await diffResponse.json();
          if (diff && !window.confirm('Starting a new chat discards un-applied changes in this disposable worktree. Continue?')) return;
        }

        const deleteResponse = await fetch(`http://127.0.0.1:8000/sessions/${sessionId}`, { method: 'DELETE' });
        if (!deleteResponse.ok && deleteResponse.status !== 404) throw new Error('Could not close the current session.');
      }
      setSessionId(null);
      clearMessages();
      setHistoryRestored(false);
      setApprovalMode('manual');
      setActiveWorkspace(workspacePath);
    } catch (error) {
      window.alert(String(error));
    } finally {
      setIsResetting(false);
      setBusy(false);
    }
  };

  const handleResume = async (identity: string): Promise<boolean> => {
    if (!workspacePath || useSessionStore.getState().busy) return false;
    setBusy(true);
    setIsResuming(true);
    let candidate: string | null = null;
    try {
      if (sessionId) {
        const response = await fetch(`http://127.0.0.1:8000/sessions/${sessionId}/diff`);
        if (!response.ok && response.status !== 404) throw new Error('Could not check the current workspace changes.');
        if (response.ok) {
          const { diff } = await response.json();
          if (diff && !window.confirm('Resuming a saved conversation discards un-applied changes in the current worktree. Continue?')) return false;
        }
      }
      const response = await fetch('http://127.0.0.1:8000/sessions', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workspace: workspacePath, conversation_id: identity, max_steps: 12 }),
      });
      if (!response.ok) throw new Error(`Could not resume this conversation (HTTP ${response.status}).`);
      const restored = await response.json();
      if (typeof restored.session_id !== 'string' || typeof restored.workspace !== 'string') {
        throw new Error('The server returned an invalid resumed session.');
      }
      candidate = restored.session_id;
      const restoredMessages = await sessionHistory(restored.session_id);
      if (useWorkspaceStore.getState().workspacePath !== workspacePath) throw new Error('The selected workspace changed. Please try again.');
      if (sessionId) {
        const closed = await fetch(`http://127.0.0.1:8000/sessions/${sessionId}`, { method: 'DELETE' });
        if (!closed.ok && closed.status !== 404) throw new Error('Could not close the current session. It has been kept open.');
      }
      replaceConversation(restored.session_id, restoredMessages);
      setActiveWorkspace(restored.workspace);
      setHistoryRestored(true);
      setApprovalMode('manual');
      candidate = null;
      return true;
    } catch (failure) {
      if (candidate) {
        try {
          const cleanup = await fetch(`http://127.0.0.1:8000/sessions/${candidate}`, { method: 'DELETE' });
          if (!cleanup.ok && cleanup.status !== 404) throw new Error('Cleanup failed.');
        } catch {
          throw new Error(`${String(failure)} The unused resumed session could not be closed; restart the local server before retrying.`);
        }
      }
      throw failure;
    } finally {
      setBusy(false);
      setIsResuming(false);
    }
  };

  const formatMessage = (msg: SessionMessage, index: number) => {
    const time = new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return (
      <div key={msg.id || `${index}:${msg.timestamp}:${msg.role}`} className={`flex gap-3 animate-in ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
        <div className={`flex-1 max-w-[80%] ${msg.role === 'user' ? 'text-right' : ''}`}>
          <div className={`inline-block px-4 py-2 rounded-2xl ${msg.role === 'user' ? 'bg-bifang-500 text-white rounded-tr-sm' : 'bg-surface-800 text-surface-100 rounded-tl-sm'}`}>
            {msg.role === 'user' ? <p className="whitespace-pre-wrap text-sm">{msg.content}</p> : (
              <div className="text-sm leading-relaxed [&_pre_code]:bg-transparent [&_pre_code]:p-0">
                <ReactMarkdown skipHtml components={{
                  p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
                  pre: ({ children }) => <pre className="my-3 max-w-full overflow-x-auto rounded-lg bg-surface-950 p-3">{children}</pre>,
                  code: ({ children }) => <code className="rounded bg-surface-950/60 px-1 py-0.5 font-mono text-xs">{children}</code>,
                  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
                  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
                  h1: ({ children }) => <h3 className="mb-2 mt-4 text-lg font-semibold">{children}</h3>,
                  h2: ({ children }) => <h3 className="mb-2 mt-4 text-lg font-semibold">{children}</h3>,
                  h3: ({ children }) => <h3 className="mb-2 mt-3 font-semibold">{children}</h3>,
                  a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer noopener" className="text-orange-300 underline">{children}</a>,
                }}>{msg.content}</ReactMarkdown>
              </div>
            )}
          </div>
          <p className={`text-xs text-surface-500 mt-1 ${msg.role === 'user' ? 'text-right' : ''}`}>{time}</p>
          {!!msg.routing?.length && <details className="mt-2 text-xs text-surface-400">
            <summary className="cursor-pointer">Model receipts · {msg.routing.length} {msg.routing.length === 1 ? 'call' : 'calls'}</summary>
            <ul className="mt-2 space-y-2 break-all">{msg.routing.map((receipt, call) => <li key={`${msg.id || index}:${call}`}>
              <p>{receipt.provider} · {receipt.role} · {receipt.task_type}</p>
              <p>Requested: {receipt.requested_model}</p>
              <p>Server reported: {receipt.reported_model || 'not supplied'}</p>
              {receipt.usage.prompt_tokens !== undefined && <p>{receipt.usage.prompt_tokens} input tokens · {receipt.usage.completion_tokens ?? 'unknown'} output tokens</p>}
            </li>)}</ul>
          </details>}
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full bg-surface-950">
      <ReviewPanel />
      <CandidatePanel />
      {historyOpen && workspacePath && <ConversationHistory key={workspacePath} workspace={workspacePath}
        busy={isResuming} onResume={handleResume} onClose={() => setHistoryOpen(false)} />}
      <dialog ref={approvalDialog} onCancel={(event) => { event.preventDefault(); resolveApproval(false); }} aria-labelledby="approval-title" className="m-auto w-full max-w-xl rounded-2xl border border-border bg-card p-6 text-card-foreground shadow-xl backdrop:bg-black/70">
        <p className="text-xs font-semibold uppercase tracking-widest text-brand-primary">Permission required</p>
        <h2 id="approval-title" className="mt-2 text-xl font-semibold">Review requested action</h2>
        <pre className="my-5 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-background p-4 text-sm">{pendingApproval?.action}</pre>
        <p className="text-sm text-muted-foreground">Your choice applies to this action only.</p>
        <div className="mt-6 flex justify-end gap-3">
          <button type="button" className="btn-secondary" onClick={() => resolveApproval(false)} autoFocus>Deny</button>
          <button type="button" className="btn-primary" onClick={() => resolveApproval(true)}>Allow once</button>
        </div>
      </dialog>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-surface-800">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-5 h-5 text-bifang-500" />
          <h2 className="text-lg font-semibold">Chat</h2>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="flex items-center gap-2 rounded-lg p-2 text-sm text-surface-300 hover:bg-surface-800 disabled:opacity-50"
            aria-label="Saved conversations" onClick={() => setHistoryOpen(true)} disabled={!workspacePath || isLoading || isResetting || isResuming}>
            <History className="h-4 w-4" />History
          </button>
          <button className="p-2 rounded-lg hover:bg-surface-800 disabled:opacity-50" title="New chat" aria-label="New chat" onClick={handleNewChat} disabled={isLoading || isResetting || isResuming}>
            <MessageSquare className="w-4 h-4" />
          </button>
        </div>
      </div>

      <ModelPicker selection={modelSelection} busy={isLoading || isResetting || isResuming} onChange={setModelSelection} />
      <ApprovalPicker mode={approvalMode} busy={isLoading || isResetting || isResuming} onChange={setApprovalMode}
        onPause={isLoading && sessionId ? handlePauseApprovals : undefined} pausing={isPausing} />
      {historyRestored && <p role="status" className="border-b border-surface-800 bg-surface-900 px-4 py-3 text-xs text-surface-300">History restored. Review current files before continuing; no commands or approvals were replayed.</p>}
      {cacheWarning && <p role="alert" className="border-b border-red-500/30 bg-red-500/10 px-4 py-3 text-xs text-red-200">The browser chat cache could not be saved. Saved conversations are stored separately on the local server; protect that data with backups.</p>}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-surface-500">
            <MessageSquare className="w-12 h-12 mb-4 opacity-50" />
            <p className="text-lg font-medium">Start a conversation</p>
            <p className="text-sm">Ask Bifang to help with your code</p>
          </div>
        ) : (
          messages.map(formatMessage)
        )}
        <div ref={messagesEndRef} />
        {isLoading && <p role="status" className="flex items-center gap-2 text-sm text-surface-400"><Loader2 className="h-4 w-4 animate-spin" />{pendingApproval ? 'Waiting for your approval' : 'Bifang is working in your workspace…'}</p>}
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4 border-t border-surface-800">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask Bifang..."
              rows={1}
              className="w-full bg-surface-800 border border-surface-700 rounded-lg p-3 pr-12 text-sm resize-none focus:border-bifang-500 focus:outline-none focus:ring-1 focus:ring-bifang-500"
              style={{ minHeight: '44px', maxHeight: '200px' }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e as any);
                }
              }}
            />
            <button
              type="submit"
              disabled={!input.trim() || isLoading || isResetting || isResuming}
              className="absolute right-2 bottom-2 p-2 rounded-lg bg-bifang-500 text-white hover:bg-bifang-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>
        <p className="text-xs text-surface-500 text-center mt-2">
          Press <kbd className="px-1.5 py-0.5 bg-surface-800 rounded">Enter</kbd> to send, <kbd className="px-1.5 py-0.5 bg-surface-800 rounded">Shift+Enter</kbd> for new line
        </p>
      </form>
    </div>
  );
}
