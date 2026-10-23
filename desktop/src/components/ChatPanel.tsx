import { useState, useRef, useEffect } from 'react';
import { Send, Loader2, MessageSquare } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { useSessionStore, useWorkspaceStore } from '../stores/bifangStore';

interface Message {
  role: 'user' | 'assistant' | 'tool' | 'system';
  content: string;
  toolCalls?: Array<{ name: string; args: any }>;
  toolResult?: string;
  timestamp: number;
}

export function ChatPanel() {
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [pendingApproval, setPendingApproval] = useState<{ action: string; resolve: (approved: boolean) => void } | null>(null);
  const approvalDialog = useRef<HTMLDialogElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { sessionId, setSessionId, messages, addMessage, clearMessages } = useSessionStore();
  const workspacePath = useWorkspaceStore((state) => state.workspacePath);
  const setActiveWorkspace = useWorkspaceStore((state) => state.setActiveWorkspace);
  const previousWorkspace = useRef(workspacePath);

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
      setActiveWorkspace(workspacePath);
      previousWorkspace.current = workspacePath;
    }
  }, [workspacePath, setSessionId, clearMessages, setActiveWorkspace]);

  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    fetch(`http://127.0.0.1:8000/sessions/${sessionId}`)
      .then(async (response) => {
        if (!active) return;
        if (!response.ok) {
          setSessionId(null);
          clearMessages();
          setActiveWorkspace(workspacePath);
          return;
        }
        const session = await response.json();
        setActiveWorkspace(session.workspace);
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [sessionId, setSessionId, clearMessages, setActiveWorkspace, workspacePath]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading || isResetting) return;

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
        body: JSON.stringify({ prompt: userMessage }),
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
      if (!response.ok) throw new Error((await response.text()) || 'Chat request failed.');
      const data = await response.json();
      addMessage({ role: 'assistant', content: data.response });
    } catch (error) {
      addMessage({ role: 'assistant', content: `Error: ${error}` });
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewChat = async () => {
    if (isLoading || isResetting) return;
    setIsResetting(true);
    try {
      if (sessionId) {
        const diffResponse = await fetch(`http://127.0.0.1:8000/sessions/${sessionId}/diff`);
        if (!diffResponse.ok) throw new Error('Could not check the current workspace changes.');
        const { diff } = await diffResponse.json();
        if (diff && !window.confirm('Starting a new chat discards un-applied changes in this disposable worktree. Continue?')) return;

        const deleteResponse = await fetch(`http://127.0.0.1:8000/sessions/${sessionId}`, { method: 'DELETE' });
        if (!deleteResponse.ok) throw new Error('Could not close the current session.');
      }
      setSessionId(null);
      clearMessages();
      setActiveWorkspace(workspacePath);
    } catch (error) {
      window.alert(String(error));
    } finally {
      setIsResetting(false);
    }
  };

  const formatMessage = (msg: Message) => {
    const time = new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return (
      <div key={msg.timestamp} className={`flex gap-3 animate-in ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
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
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full bg-surface-950">
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
          <button className="p-2 rounded-lg hover:bg-surface-800 disabled:opacity-50" title="New chat" aria-label="New chat" onClick={handleNewChat} disabled={isLoading || isResetting}>
            <MessageSquare className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-surface-500">
            <MessageSquare className="w-12 h-12 mb-4 opacity-50" />
            <p className="text-lg font-medium">Start a conversation</p>
            <p className="text-sm">Ask Bifang to help with your code</p>
          </div>
        ) : (
          messages.map((msg) => formatMessage(msg))
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
              disabled={!input.trim() || isLoading || isResetting}
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
