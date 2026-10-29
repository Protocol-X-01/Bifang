import { localFetch } from '../api/localApi';
import { followViewportResize } from '../api/chatViewport';
import { useState, useRef, useEffect } from 'react';
import { Send, Loader2, MessageSquare, History, Sparkles, Zap, Mic2 } from 'lucide-react';
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
import { VisionPanel } from './VisionPanel';
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
  const [showWelcome, setShowWelcome] = useState(false);
  const approvalDialog = useRef<HTMLDialogElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesViewportRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { sessionId, setSessionId, messages, addMessage, clearMessages, setBusy, replaceConversation, busy: sessionBusy } = useSessionStore();
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
    if (messagesViewportRef.current) return followViewportResize(messagesViewportRef.current);
  }, []);

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
    localFetch(`/sessions/${sessionId}`)
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

  const ensureSession = async (): Promise<string> => {
    if (!workspacePath) throw new Error('Choose a workspace before starting a chat.');
    const existing = useSessionStore.getState().sessionId;
    if (existing) return existing;
    const created = await localFetch('/sessions', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace: workspacePath, max_steps: 12 }),
    });
    if (!created.ok) throw new Error('Could not create a workspace session.');
    const session = await created.json();
    setSessionId(session.session_id); setActiveWorkspace(session.workspace);
    return session.session_id;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || useSessionStore.getState().busy) return;
    setBusy(true);

    const userMessage = input;
    setInput('');
    setIsLoading(true);

    addMessage({ role: 'user', content: userMessage });

    try {
      const activeSessionId = await ensureSession();

      let chatFinished = false;
      const chatRequest = localFetch(`/sessions/${activeSessionId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: userMessage, selection: modelSelection, ...approvalRequest(approvalMode) }),
      });
      const pollApprovals = async () => {
        while (!chatFinished) {
          const stateResponse = await localFetch(`/sessions/${activeSessionId}/approval`);
          if (!stateResponse.ok) break;
          const approval = await stateResponse.json();
          if (approval.approval_id) {
            const approved = await new Promise<boolean>((resolve) => {
              setPendingApproval({ action: approval.action, resolve });
            });
            await localFetch(`/sessions/${activeSessionId}/approval`, {
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
      const response = await localFetch(`/sessions/${sessionId}/pause-auto-approval`, { method: 'POST' });
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
        const diffResponse = await localFetch(`/sessions/${sessionId}/diff`);
        if (!diffResponse.ok && diffResponse.status !== 404) throw new Error('Could not check the current workspace changes.');
        if (diffResponse.ok) {
          const { diff } = await diffResponse.json();
          if (diff && !window.confirm('Starting a new chat discards un-applied changes in this isolated workspace. Continue?')) return;
        }

        const deleteResponse = await localFetch(`/sessions/${sessionId}`, { method: 'DELETE' });
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
        const response = await localFetch(`/sessions/${sessionId}/diff`);
        if (!response.ok && response.status !== 404) throw new Error('Could not check the current workspace changes.');
        if (response.ok) {
          const { diff } = await response.json();
          if (diff && !window.confirm('Resuming a saved conversation discards un-applied changes in the current isolated workspace. Continue?')) return false;
        }
      }
      const response = await localFetch('/sessions', {
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
        const closed = await localFetch(`/sessions/${sessionId}`, { method: 'DELETE' });
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
          const cleanup = await localFetch(`/sessions/${candidate}`, { method: 'DELETE' });
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
      <div key={msg.id || `${index}:${msg.timestamp}:${msg.role}`} className={`flex gap-3 animate-in stagger-1 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
        <div className={`flex-1 max-w-[85%] ${msg.role === 'user' ? 'text-right' : ''}`}>
          <div className={`inline-block px-4 py-2.5 rounded-2xl ${msg.role === 'user'
            ? 'bg-gradient-to-r from-bifang-brand-red to-bifang-brand-orange text-bifang-brand-white rounded-tr-sm shadow-lg shadow-bifang-brand-red/20'
            : 'bg-bifang-panel border border-bifang-border text-bifang-text-primary rounded-tl-sm'}`}>
            {msg.role === 'user' ? (
              <p className="whitespace-pre-wrap text-body-sm">{msg.content}</p>
            ) : (
              <div className="text-body-sm leading-relaxed [&_pre_code]:bg-transparent [&_pre_code]:p-0">
                <ReactMarkdown skipHtml components={{
                  p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
                  pre: ({ children }) => <pre className="my-3 max-w-full overflow-x-auto rounded-lg bg-bifang-canvas border border-bifang-border p-3">{children}</pre>,
                  code: ({ children }) => <code className="rounded bg-bifang-surface px-1.5 py-0.5 font-mono text-xs text-bifang-brand-orange/90">{children}</code>,
                  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
                  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
                  h1: ({ children }) => <h3 className="mb-2 mt-4 text-h5 font-semibold text-bifang-text-primary">{children}</h3>,
                  h2: ({ children }) => <h3 className="mb-2 mt-4 text-h5 font-semibold text-bifang-text-primary">{children}</h3>,
                  h3: ({ children }) => <h3 className="mb-2 mt-3 font-semibold text-bifang-text-primary">{children}</h3>,
                  a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer noopener" className="text-bifang-brand-orange underline hover:text-bifang-brand-orange/80">{children}</a>,
                  blockquote: ({ children }) => <blockquote className="my-3 border-l-2 border-bifang-brand-red/50 pl-4 italic text-bifang-text-secondary">{children}</blockquote>,
                }}>{msg.content}</ReactMarkdown>
              </div>
            )}
          </div>
          <p className={`text-caption text-bifang-text-muted mt-1.5 ${msg.role === 'user' ? 'text-right' : ''}`}>{time}</p>
          {!!msg.routing?.length && <details className="mt-2 text-caption text-bifang-text-muted group">
            <summary className="cursor-pointer flex items-center gap-2 font-medium text-bifang-text-secondary hover:text-bifang-text-primary transition-colors">
              <Zap className="w-3.5 h-3.5 text-bifang-brand-orange" />
              Model receipts · {msg.routing.length} {msg.routing.length === 1 ? 'call' : 'calls'}
            </summary>
            <ul className="mt-2 space-y-2 break-all pl-2 border-l border-bifang-border/30">
              {msg.routing.map((receipt, call) => <li key={`${msg.id || index}:${call}`} className="pl-3">
                <p className="font-medium text-bifang-text-secondary">{receipt.provider} · {receipt.role} · {receipt.task_type}</p>
                <p className="text-bifang-text-muted">Requested: <span className="font-mono text-bifang-brand-orange">{receipt.requested_model}</span></p>
                <p className="text-bifang-text-muted">Server reported: <span className="font-mono">{receipt.reported_model || 'not supplied'}</span></p>
                {receipt.usage.prompt_tokens !== undefined && <p className="text-bifang-text-muted">{receipt.usage.prompt_tokens} input · {receipt.usage.completion_tokens ?? 'unknown'} output tokens</p>}
              </li>)}</ul>
            </details>}
        </div>
      </div>
    );
  };

  return (
    <div className="coding-canvas flex min-h-0 flex-col h-full bg-bifang-canvas">
      <div className="max-h-[40%] shrink-0 overflow-y-auto">
        <ReviewPanel />
        <CandidatePanel />
        <VisionPanel ensureSession={ensureSession} onUse={(text) => {
          const combined = input.trim() ? `${input}\n\n${text}` : text;
          if (combined.length > 20000) window.alert('The combined draft exceeds 20,000 characters. Shorten the current draft before adding observations.');
          else setInput(combined);
        }} />
      </div>
      {historyOpen && workspacePath && <ConversationHistory key={workspacePath} workspace={workspacePath}
        busy={isResuming} onResume={handleResume} onClose={() => setHistoryOpen(false)} />}
      <dialog ref={approvalDialog} onCancel={(event) => { event.preventDefault(); resolveApproval(false); }} aria-labelledby="approval-title" className="m-auto w-full max-w-xl rounded-2xl border-bifang-border bg-bifang-panel p-6 text-bifang-text-primary shadow-2xl glass-strong">
        <p className="text-overline text-bifang-brand-orange">Permission required</p>
        <h2 id="approval-title" className="mt-2 text-h4 text-bifang-text-primary">Review requested action</h2>
        <pre className="my-5 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-bifang-canvas border border-bifang-border p-4 text-body-sm text-bifang-brand-orange/90">{pendingApproval?.action}</pre>
        <p className="text-body-sm text-bifang-text-secondary">Your choice applies to this action only.</p>
        <div className="mt-6 flex justify-end gap-3">
          <button type="button" className="btn-secondary" onClick={() => resolveApproval(false)} autoFocus>Deny</button>
          <button type="button" className="btn-primary" onClick={() => resolveApproval(true)}>Allow once</button>
        </div>
      </dialog>

      {/* Header */}
      <header className="flex shrink-0 items-center justify-between p-4 border-b border-bifang-border bg-bifang-panel/50 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-gradient-to-r from-bifang-brand-red to-bifang-brand-orange">
            <MessageSquare className="w-5 h-5 text-bifang-brand-white" />
          </div>
          <h2 className="text-h5 text-bifang-text-primary font-bold">Code with Bifang</h2>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="btn-ghost" aria-label="Saved conversations" onClick={() => setHistoryOpen(true)} disabled={!workspacePath || sessionBusy || isLoading || isResetting || isResuming}>
            <History className="w-4 h-4" />
            <span className="hidden sm:inline">History</span>
          </button>
          <button className="btn-ghost" title="New chat" aria-label="New chat" onClick={handleNewChat} disabled={sessionBusy || isLoading || isResetting || isResuming}>
            <MessageSquare className="w-4 h-4" />
          </button>
        </div>
      </header>

      <ModelPicker selection={modelSelection} busy={sessionBusy || isLoading || isResetting || isResuming} onChange={setModelSelection} />
      <ApprovalPicker mode={approvalMode} busy={sessionBusy || isLoading || isResetting || isResuming} onChange={setApprovalMode}
        onPause={isLoading && sessionId ? handlePauseApprovals : undefined} pausing={isPausing} />
      {historyRestored && <div className="border-b border-bifang-border bg-bifang-surface/50 px-4 py-3 text-caption text-bifang-text-secondary animate-in slide-down">History restored. Review current files before continuing; no commands or approvals were replayed.</div>}
      {cacheWarning && <div className="border-b border-bifang-brand-red/30 bg-bifang-brand-red/10 px-4 py-3 text-caption text-bifang-brand-red animate-in slide-down" role="alert">The browser chat cache could not be saved. Saved conversations are stored separately on the local server; protect that data with backups.</div>}

      {/* Messages */}
      <div ref={messagesViewportRef} className="min-h-0 flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin bg-grid">
        {messages.length === 0 ? (
          <div className="coding-welcome flex min-h-full flex-col justify-center items-center px-4 py-8 text-center animate-in">
            <div className="welcome-mark animate-in stagger-1" aria-hidden="true">
              <img src="/favicon.svg" className="h-12 w-12" alt="" />
            </div>
            <p className="welcome-eyebrow animate-in stagger-2">Bifang / Coding workspace</p>
            <h3 className="welcome-title animate-in stagger-3">Make the next<br />change count.</h3>
            <p className="welcome-description animate-in stagger-4">Explore the code. Shape the patch. Build something worth keeping.</p>
            <div className="welcome-actions animate-in stagger-5" aria-label="Start a coding task">
              {[
                ['Explore', 'Explain this workspace\'s architecture and identify its main entry points. Inspect the source before drawing conclusions.'],
                ['Debug', 'Help me investigate a bug. First inspect the project and ask which behavior I want to fix.'],
                ['Build', 'Help me build a new feature. First inspect the workspace and ask what I want to create.'],
              ].map(([label, prompt]) => <button key={label} type="button" disabled={!workspacePath || sessionBusy} className="btn-secondary"
                onClick={() => setInput(prompt)}><span>{label}</span><span aria-hidden="true" className="ml-1">→</span></button>)}
            </div>
            {!workspacePath && <p className="welcome-hint animate-in stagger-6">Open a workspace or create one in the sidebar to begin.</p>}
          </div>
        ) : (
          messages.map(formatMessage)
        )}
        <div ref={messagesEndRef} />
        {isLoading && <div className="flex items-center justify-center gap-2 text-body-sm text-bifang-text-muted py-4 animate-in fade-in">
          <Loader2 className="w-5 h-5 animate-spin text-bifang-brand-orange" />
          {pendingApproval ? 'Waiting for your approval' : 'Bifang is working in your workspace…'}
        </div>}
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="shrink-0 p-4 border-t border-bifang-border bg-bifang-panel/50 backdrop-blur-sm">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask Bifang..."
              rows={1}
              className="input w-full bg-bifang-surface border-bifang-border pr-14 resize-none focus:border-bifang-brand-orange focus:ring-bifang-focus-ring focus:ring-offset-bifang-focus-offset"
              style={{ minHeight: '48px', maxHeight: '200px' }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e as any);
                }
              }}
            />
            <button
              type="submit"
              disabled={!input.trim() || sessionBusy || isLoading || isResetting || isResuming}
              className="absolute right-2 bottom-2 p-2 rounded-lg bg-gradient-to-r from-bifang-brand-red to-bifang-brand-orange text-bifang-brand-white hover:from-bifang-brand-red/90 hover:to-bifang-brand-orange/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 hover:shadow-lg hover:shadow-bifang-brand-red/20"
              aria-label={isLoading ? 'Working…' : 'Send message'}
            >
              {isLoading ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Send className="w-5 h-5" />
              )}
            </button>
          </div>
        </div>
        <p className="text-caption text-bifang-text-muted text-center mt-2">
          Press <kbd className="px-2 py-0.5 bg-bifang-surface border border-bifang-border rounded">Enter</kbd> to send, <kbd className="px-2 py-0.5 bg-bifang-surface border border-bifang-border rounded">Shift+Enter</kbd> for new line
        </p>
      </form>
    </div>
  );
}