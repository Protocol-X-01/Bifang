import { useState, useEffect, useRef } from 'react';
import { 
  Brain, 
  ChevronDown, 
  ChevronUp, 
  ChevronLeft, 
  ChevronRight,
  Copy, 
  Download, 
  Search, 
  Filter,
  Eye,
  EyeOff,
  Zap,
  Clock,
  Layers,
  Code2,
  Terminal,
  MessageSquare,
  X,
  Check,
  AlertTriangle,
  Info,
  Sparkles,
  Minus,
  Plus
} from 'lucide-react';

interface ReasoningStep {
  id: string;
  index: number;
  type: 'thought' | 'action' | 'observation' | 'decision' | 'error' | 'summary';
  content: string;
  rawContent?: string; // Raw CoT from model
  timestamp: number;
  duration?: number;
  toolCalls?: ToolCall[];
  toolResults?: ToolResult[];
  confidence?: number;
  tokensUsed?: number;
  metadata?: Record<string, any>;
}

interface ToolCall {
  name: string;
  arguments: Record<string, any>;
  id: string;
}

interface ToolResult {
  toolCallId: string;
  success: boolean;
  output: string;
  error?: string;
}

interface ReasoningSession {
  id: string;
  prompt: string;
  steps: ReasoningStep[];
  startTime: number;
  endTime?: number;
  totalTokens: number;
  model: string;
  provider: string;
  status: 'running' | 'completed' | 'error';
}

export function ReasoningPanel({ 
  sessionId, 
  onClose,
  compact = false 
}: { 
  sessionId: string | null; 
  onClose?: () => void;
  compact?: boolean;
}) {
  const [sessions, setSessions] = useState<ReasoningSession[]>([]);
  const [selectedSession, setSelectedSession] = useState<ReasoningSession | null>(null);
  const [selectedStep, setSelectedStep] = useState<ReasoningStep | null>(null);
  const [filter, setFilter] = useState<'all' | 'thought' | 'action' | 'observation' | 'decision' | 'error'>('all');
  const [showRaw, setShowRaw] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());
  const stepsEndRef = useRef<HTMLDivElement>(null);
  const [showConfidence, setShowConfidence] = useState(true);
  const [showTiming, setShowTiming] = useState(true);

  // Mock data for demonstration
  useEffect(() => {
    if (!sessionId) return;
    
    // Mock reasoning session data
    const mockSession: ReasoningSession = {
      id: sessionId,
      prompt: "Find the performance bottleneck in the vector search, optimize it, and prove the result with benchmarks.",
      startTime: Date.now() - 125000,
      endTime: Date.now(),
      totalTokens: 45230,
      model: 'nemotron-3-ultra',
      provider: 'nvidia',
      status: 'completed',
      steps: [
        {
          id: 'step-1',
          index: 0,
          type: 'thought',
          content: "The user wants me to find a performance bottleneck in vector search, optimize it, and verify with benchmarks. I need to first explore the codebase to understand the current implementation.",
          rawContent: "<|begin_of_thought|> The user wants me to find a performance bottleneck in vector search, optimize it, and verify with benchmarks. I need to first explore the codebase to understand the current implementation. Let me start by mapping the repository structure to locate the vector search implementation. <|end_of_thought|>",
          timestamp: Date.now() - 120000,
          duration: 1200,
          confidence: 0.95,
          tokensUsed: 1240,
        },
        {
          id: 'step-2',
          index: 1,
          type: 'action',
          content: "Mapping repository structure to find vector search related files",
          timestamp: Date.now() - 118000,
          duration: 850,
          toolCalls: [
            { name: 'list_files', arguments: { limit: 500 }, id: 'tc-1' },
          ],
          toolResults: [
            { toolCallId: 'tc-1', success: true, output: 'src/search/vector.rs\nsrc/search/index.rs\nsrc/index.rs\nbenches/vector_search.rs\ntests/search_test.rs' },
          ],
          confidence: 0.92,
          tokensUsed: 890,
        },
        {
          id: 'step-3',
          index: 2,
          type: 'observation',
          content: "Found vector search implementation in src/search/vector.rs and benchmarks in benches/vector_search.rs. Need to examine the implementation for bottlenecks.",
          timestamp: Date.now() - 117000,
          duration: 300,
          confidence: 0.98,
          tokensUsed: 450,
        },
        {
          id: 'step-4',
          index: 3,
          type: 'thought',
          content: "Reading the vector search implementation to identify potential bottlenecks. Key areas to check: similarity computation algorithm, memory access patterns, indexing strategy, and any unnecessary allocations.",
          rawContent: "<|begin_of_thought|> Reading the vector search implementation to identify potential bottlenecks. Key areas to check: 1) Similarity computation - are they using efficient SIMD operations? 2) Memory access patterns - are they cache-friendly? 3) Indexing strategy - are they using HNSW, IVF, or brute force? 4) Unnecessary allocations in hot paths. Let me read the files. <|end_of_thought|>",
          timestamp: Date.now() - 115000,
          duration: 2100,
          confidence: 0.94,
          tokensUsed: 1890,
        },
        {
          id: 'step-5',
          index: 4,
          type: 'action',
          content: "Reading vector search implementation files",
          timestamp: Date.now() - 113000,
          duration: 1200,
          toolCalls: [
            { name: 'read_file', arguments: { path: 'src/search/vector.rs' }, id: 'tc-2' },
            { name: 'read_file', arguments: { path: 'benches/vector_search.rs' }, id: 'tc-3' },
          ],
          toolResults: [
            { toolCallId: 'tc-2', success: true, output: '// Vector search implementation\npub fn search(query: &[f32], index: &HnswIndex, k: u32) -> Vec<Result> {\n    let mut results = Vec::with_capacity(k as usize);\n    for item in index.iter() {\n        let dist = cosine_distance(query, item.vector); // Bottleneck: no SIMD\n        results.push(Result { id: item.id, score: dist });\n    }\n    results.sort_by(|a, b| a.score.partial_cmp(&b.score).unwrap());\n    results.truncate(k as usize);\n    results\n}' },
            { toolCallId: 'tc-3', success: true, output: '#[bench]\nfn bench_vector_search(b: &mut Bencher) {\n    let index = build_test_index();\n    let query = random_vector();\n    b.iter(|| search(&query, &index, 10)); // Baseline benchmark\n}' },
          ],
          confidence: 0.96,
          tokensUsed: 2100,
        },
        {
          id: 'step-6',
          index: 5,
          type: 'observation',
          content: "Found the bottleneck: cosine_distance uses scalar operations without SIMD, and the search iterates through all vectors without early termination. Also sorting all results instead of using a min-heap for top-k.",
          timestamp: Date.now() - 111000,
          duration: 500,
          confidence: 0.99,
          tokensUsed: 670,
        },
        {
          id: 'step-7',
          index: 6,
          type: 'decision',
          content: "Optimization plan: 1) Add SIMD-accelerated cosine similarity using std::arch::x86_64 2) Use min-heap (BinaryHeap) for top-k instead of sorting all 3) Add early termination with distance threshold 4) Consider product quantization for large indices",
          timestamp: Date.now() - 110000,
          duration: 1800,
          confidence: 0.93,
          tokensUsed: 1450,
        },
        {
          id: 'step-8',
          index: 7,
          type: 'action',
          content: "Implementing SIMD-accelerated cosine similarity and min-heap top-k",
          timestamp: Date.now() - 108000,
          duration: 8500,
          toolCalls: [
            { name: 'write_file', arguments: { path: 'src/search/vector.rs', content: '// Preview example only' }, id: 'tc-4' },
          ],
          toolResults: [
            { toolCallId: 'tc-4', success: true, output: 'File written successfully' },
          ],
          confidence: 0.91,
          tokensUsed: 3200,
        },
        {
          id: 'step-9',
          index: 8,
          type: 'action',
          content: "Running benchmarks to verify optimization",
          timestamp: Date.now() - 100000,
          duration: 15000,
          toolCalls: [
            { name: 'run_command', arguments: { command: 'cargo bench --bench vector_search' }, id: 'tc-5' },
          ],
          toolResults: [
            { toolCallId: 'tc-5', success: true, output: 'vector_search/bench_vector_search  4.82 ms → 3.31 ms  (-31.4%)\nvector_search/bench_vector_search_large  12.4 ms → 8.2 ms  (-33.9%)\nAll tests passed!' },
          ],
          confidence: 0.98,
          tokensUsed: 2800,
        },
        {
          id: 'step-10',
          index: 9,
          type: 'summary',
          content: "Successfully optimized vector search with 31.4% latency improvement. Key changes: 1) Added AVX2-accelerated cosine similarity (4.2x faster per comparison) 2) Replaced full sort with min-heap top-k (O(n log k) vs O(n log n)) 3) Added distance threshold for early termination. All tests pass, benchmarks show 31.4% latency reduction.",
          timestamp: Date.now() - 85000,
          duration: 3000,
          confidence: 0.99,
          tokensUsed: 2100,
        },
      ],
    };
    
    setSessions([mockSession]);
    setSelectedSession(mockSession);
  }, [sessionId]);

  if (!sessionId) {
    return (
      <div className="flex flex-col h-full bg-brand-background">
        <div className="p-4 border-b border-brand-border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="p-2 bg-brand-primary/20 rounded-lg">
                <Brain className="w-5 h-5 text-brand-primary" />
              </div>
              <div>
                <h3 className="font-medium text-brand-text">Reasoning Panel</h3>
                <p className="text-xs text-brand-text-muted">Nemotron 3 Ultra chain-of-thought</p>
              </div>
            </div>
            {onClose && (
              <button onClick={onClose} className="p-1.5 rounded hover:bg-brand-surface-elevated">
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
        <div className="flex-1 flex items-center justify-center text-brand-text-muted">
          <div className="text-center">
            <Brain className="w-12 h-12 mx-auto mb-4 opacity-30" />
            <p className="text-lg font-medium">No active reasoning session</p>
            <p className="text-sm mt-1">Start a task to see Nemotron 3 Ultra's reasoning</p>
          </div>
        </div>
      </div>
    );
  }

  const session = selectedSession || sessions[0];
  const filteredSteps = session.steps.filter(step => {
    if (filter === 'all') return true;
    return step.type === filter;
  });
  
  const searchedSteps = filteredSteps.filter(step => 
    step.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
    step.rawContent?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    step.toolCalls?.some(tc => tc.name.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'thought': return <Brain className="w-4 h-4 text-brand-primary" />;
      case 'action': return <Zap className="w-4 h-4 text-brand-orange" />;
      case 'observation': return <Eye className="w-4 h-4 text-status-info" />;
      case 'decision': return <Target className="w-4 h-4 text-status-warning" />;
      case 'error': return <AlertTriangle className="w-4 h-4 text-status-error" />;
      case 'summary': return <Sparkles className="w-4 h-4 text-status-success" />;
      default: return <MessageSquare className="w-4 h-4 text-brand-text-muted" />;
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'thought': return 'border-brand-primary/30 bg-brand-primary/5';
      case 'action': return 'border-brand-orange/30 bg-brand-orange/5';
      case 'observation': return 'border-status-info/30 bg-status-info/5';
      case 'decision': return 'border-status-warning/30 bg-status-warning/5';
      case 'error': return 'border-status-error/30 bg-status-error/5';
      case 'summary': return 'border-status-success/30 bg-status-success/5';
      default: return 'border-brand-border bg-brand-surface';
    }
  };

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  const formatTimestamp = (ts: number) => {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  if (compact) {
    return (
      <div className="flex flex-col h-full bg-brand-background">
        <div className="p-3 border-b border-brand-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-brand-primary/20 rounded">
              <Brain className="w-4 h-4 text-brand-primary" />
            </div>
            <div>
              <p className="font-medium text-xs text-brand-text">Reasoning</p>
              <p className="text-[10px] text-brand-text-muted">{session.steps.length} steps • {formatDuration(session.endTime ? session.endTime - session.startTime : Date.now() - session.startTime)}</p>
            </div>
          </div>
          {onClose && (
            <button onClick={onClose} className="p-1 rounded hover:bg-brand-surface-elevated">
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
        <div className="flex-1 overflow-y-auto p-2 scrollbar-thin">
          {searchedSteps.map(step => (
            <CompactStepCard key={step.id} step={step} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-brand-background">
      {/* Header */}
      <div className="p-3 border-b border-brand-border">
        <div className="flex items-center justify-between flex-wrap gap-3 mb-3">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-brand-primary/20 rounded-lg">
              <Brain className="w-5 h-5 text-brand-primary" />
            </div>
            <div>
              <h3 className="font-medium text-brand-text">Reasoning Panel</h3>
              <p className="text-xs text-brand-text-muted">
                {session.steps.length} steps • {session.steps.filter(s => s.type === 'thought').length} thoughts • 
                {session.steps.filter(s => s.type === 'action').length} actions • 
                {formatDuration(session.endTime ? session.endTime - session.startTime : Date.now() - session.startTime)}
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-brand-text-muted" />
              <input
                type="text"
                placeholder="Search reasoning..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="px-8 pr-2 py-1 bg-brand-surface border border-brand-border rounded text-xs text-brand-text placeholder-brand-text-muted focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary w-48"
              />
            </div>
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value as any)}
              className="px-2 py-1 bg-brand-surface border border-brand-border rounded text-xs text-brand-text focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary"
            >
              <option value="all">All</option>
              <option value="thought">💭 Thoughts</option>
              <option value="action">⚡ Actions</option>
              <option value="observation">👁 Observations</option>
              <option value="decision">🎯 Decisions</option>
              <option value="error">⚠ Errors</option>
            </select>
            <label className="flex items-center gap-1 text-xs text-brand-text-muted cursor-pointer">
              <input
                type="checkbox"
                checked={showRaw}
                onChange={(e) => setShowRaw(e.target.checked)}
                className="w-3 h-3 accent-brand-primary"
              />
              Raw CoT
            </label>
            <label className="flex items-center gap-1 text-xs text-brand-text-muted cursor-pointer">
              <input
                type="checkbox"
                checked={showConfidence}
                onChange={(e) => setShowConfidence(e.target.checked)}
                className="w-3 h-3 accent-brand-primary"
              />
              Confidence
            </label>
            <label className="flex items-center gap-1 text-xs text-brand-text-muted cursor-pointer">
              <input
                type="checkbox"
                checked={showTiming}
                onChange={(e) => setShowTiming(e.target.checked)}
                className="w-3 h-3 accent-brand-primary"
              />
              Timing
            </label>
            <label className="flex items-center gap-1 text-xs text-brand-text-muted cursor-pointer">
              <input
                type="checkbox"
                checked={autoScroll}
                onChange={(e) => setAutoScroll(e.target.checked)}
                className="w-3 h-3 accent-brand-primary"
              />
              Auto-scroll
            </label>
            {onClose && (
              <button onClick={onClose} className="p-1.5 rounded hover:bg-brand-surface-elevated transition-colors" title="Close">
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Session Stats */}
        <div className="flex flex-wrap gap-3 text-xs text-brand-text-muted">
          <span className="flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-status-success" />
            Total tokens: {session.totalTokens.toLocaleString()}
          </span>
          <span className="flex items-center gap-1">
            <Zap className="w-3 h-3 text-brand-orange" />
            Model: {session.model} ({session.provider})
          </span>
          <span className="flex items-center gap-1">
            <Info className="w-3 h-3 text-status-info" />
            Status: {session.status}
          </span>
        </div>
      </div>

      {/* Steps Timeline */}
      <div className="flex-1 overflow-y-auto p-3 scrollbar-thin">
        {searchedSteps.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-brand-text-muted">
            <Brain className="w-12 h-12 mb-4 opacity-30" />
            <p className="text-lg font-medium">No reasoning steps match filter</p>
            <p className="text-sm mt-1">Try adjusting search or filter</p>
          </div>
        ) : (
          <div className="space-y-2" ref={stepsEndRef}>
            {searchedSteps.map((step, i) => (
              <ReasoningStepCard
                key={step.id}
                step={step}
                index={i}
                showRaw={showRaw}
                showConfidence={showConfidence}
                showTiming={showTiming}
                isSelected={selectedStep?.id === step.id}
                onSelect={() => setSelectedStep(step)}
                onToggleExpand={() => {
                  setExpandedSteps(prev => {
                    const next = new Set(prev);
                    if (next.has(step.id)) next.delete(step.id);
                    else next.add(step.id);
                    return next;
                  });
                }}
                isExpanded={expandedSteps.has(step.id)}
              />
            ))}
            <div ref={stepsEndRef} />
          </div>
        )}

        {/* Selected Step Detail */}
        {selectedStep && (
          <div className="border-t border-brand-border p-3 bg-brand-surface animate-in">
            <div className="flex items-center justify-between mb-3">
              <h4 className="flex items-center gap-2 text-sm font-medium text-brand-text">
                {getTypeIcon(selectedStep.type)}
                Step Detail: {selectedStep.type}
              </h4>
              <button
                onClick={() => setSelectedStep(null)}
                className="p-1 rounded hover:bg-brand-surface-elevated"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            
            <div className="space-y-3 max-h-96 overflow-y-auto scrollbar-thin">
              <div className="p-3 bg-brand-surface-elevated rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono text-xs text-brand-text">{selectedStep.id}</span>
                  <span className="text-xs text-brand-text-muted">
                    {formatTimestamp(selectedStep.timestamp)} • {formatDuration(selectedStep.duration || 0)}
                  </span>
                </div>
                <div className="whitespace-pre-wrap text-sm text-brand-text">
                  {showRaw && selectedStep.rawContent ? selectedStep.rawContent : selectedStep.content}
                </div>
              </div>

              {selectedStep.toolCalls && selectedStep.toolCalls.length > 0 && (
                <div className="space-y-2">
                  <h5 className="flex items-center gap-1 text-xs font-medium text-brand-text-muted">
                    <Terminal className="w-3 h-3" />
                    Tool Calls ({selectedStep.toolCalls.length})
                  </h5>
                  {selectedStep.toolCalls.map((tc, ti) => (
                    <div key={tc.id} className="p-2 bg-brand-surface-elevated rounded border border-brand-border">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium text-brand-text flex items-center gap-1">
                          <Code2 className="w-3 h-3" />
                          {tc.name}
                        </span>
                        <span className="text-xs font-mono text-brand-text-muted">#{tc.id.slice(-6)}</span>
                      </div>
                      <pre className="text-xs text-brand-text overflow-x-auto font-mono max-h-32 overflow-y-auto">
                        {JSON.stringify(tc.arguments, null, 2)}
                      </pre>
                    </div>
                  ))}
                </div>
              )}

              {selectedStep.toolResults && selectedStep.toolResults.length > 0 && (
                <div className="space-y-2">
                  <h5 className="flex items-center gap-1 text-xs font-medium text-brand-text-muted">
                    <Info className="w-3 h-3" />
                    Tool Results
                  </h5>
                  {selectedStep.toolResults.map((tr, ti) => (
                    <div key={ti} className={`p-2 rounded border ${tr.success ? 'border-status-success/30 bg-status-success/5' : 'border-status-error/30 bg-status-error/5'}`}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-mono text-brand-text-muted">#{tr.toolCallId.slice(-6)}</span>
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${tr.success ? 'bg-status-success/20 text-status-success' : 'bg-status-error/20 text-status-error'}`}>
                          {tr.success ? 'SUCCESS' : 'FAILED'}
                        </span>
                      </div>
                      <pre className="text-xs text-brand-text overflow-x-auto font-mono max-h-32 overflow-y-auto">
                        {tr.output.slice(0, 2000)}
                      </pre>
                      {tr.error && (
                        <div className="mt-1 p-1 bg-status-error/10 rounded text-xs text-status-error font-mono">
                          {tr.error}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {selectedStep.confidence !== undefined && showConfidence && (
                <div className="p-2 bg-brand-surface-elevated rounded border border-brand-border">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-brand-text">Confidence</span>
                    <span className={`text-sm font-bold ${selectedStep.confidence! >= 0.9 ? 'text-status-success' : selectedStep.confidence! >= 0.7 ? 'text-status-warning' : 'text-status-error'}`}>
                      {(selectedStep.confidence! * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="h-2 bg-brand-surface rounded overflow-hidden">
                    <div 
                      className={`h-full rounded ${selectedStep.confidence! >= 0.9 ? 'bg-status-success' : selectedStep.confidence! >= 0.7 ? 'bg-status-warning' : 'bg-status-error'}`}
                      style={{ width: `${selectedStep.confidence! * 100}%` }}
                    />
                  </div>
                </div>
              )}

              {selectedStep.metadata && Object.keys(selectedStep.metadata).length > 0 && (
                <div className="p-2 bg-brand-surface-elevated rounded border border-brand-border">
                  <h5 className="text-xs font-medium text-brand-text-muted mb-1">Metadata</h5>
                  <pre className="text-[10px] text-brand-text-muted overflow-x-auto font-mono">
                    {JSON.stringify(selectedStep.metadata, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function CompactStepCard({ step }: { step: ReasoningStep }) {
  const getTypeColor = (type: string) => {
    switch (type) {
      case 'thought': return 'text-brand-primary';
      case 'action': return 'text-brand-orange';
      case 'observation': return 'text-status-info';
      case 'decision': return 'text-status-warning';
      case 'error': return 'text-status-error';
      case 'summary': return 'text-status-success';
      default: return 'text-brand-text-muted';
    }
  };

  return (
    <div className="p-2 bg-brand-surface-elevated/50 rounded border-l-2 border-brand-primary/20">
      <div className="flex items-center gap-1.5 mb-1">
        <span className={getTypeColor(step.type)}>{getTypeIcon(step.type)}</span>
        <span className="text-xs font-medium text-brand-text truncate">{step.type.toUpperCase()}</span>
        <span className="text-[10px] text-brand-text-muted ml-auto font-mono">
          {step.duration ? `${step.duration}ms` : ''}
        </span>
      </div>
      <p className="text-xs text-brand-text-muted line-clamp-2">{step.content}</p>
      {step.confidence !== undefined && (
        <div className="mt-1 flex items-center gap-1">
          <div className="flex-1 h-1 bg-brand-surface rounded">
            <div 
              className={`h-full rounded ${step.confidence! >= 0.9 ? 'bg-status-success' : step.confidence! >= 0.7 ? 'bg-status-warning' : 'bg-status-error'}`}
              style={{ width: `${step.confidence! * 100}%` }}
            />
          </div>
          <span className="text-[10px] font-mono text-brand-text-muted">
            {(step.confidence! * 100).toFixed(0)}%
          </span>
        </div>
      )}
    </div>
  );
}

function ReasoningStepCard({ 
  step, 
  index, 
  showRaw, 
  showConfidence, 
  showTiming, 
  isSelected, 
  onSelect, 
  onToggleExpand, 
  isExpanded 
}: { 
  step: ReasoningStep; 
  index: number; 
  showRaw: boolean; 
  showConfidence: boolean; 
  showTiming: boolean; 
  isSelected: boolean; 
  onSelect: () => void; 
  onToggleExpand: () => void; 
  isExpanded: boolean; 
}) {
  const getTypeColor = (type: string) => {
    switch (type) {
      case 'thought': return 'border-brand-primary/30 bg-brand-primary/5';
      case 'action': return 'border-brand-orange/30 bg-brand-orange/5';
      case 'observation': return 'border-status-info/30 bg-status-info/5';
      case 'decision': return 'border-status-warning/30 bg-status-warning/5';
      case 'error': return 'border-status-error/30 bg-status-error/5';
      case 'summary': return 'border-status-success/30 bg-status-success/5';
      default: return 'border-brand-border bg-brand-surface';
    }
  };

  return (
    <div
      className={`group p-3 rounded-xl transition-all duration-200 ${getTypeColor(step.type)} ${isSelected ? 'ring-2 ring-brand-primary' : ''}`}
      onClick={onSelect}
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 w-8 text-center">
          <span className="text-xs text-brand-text-muted font-mono font-bold">{index + 1}</span>
        </div>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-medium text-brand-text">{step.type.toUpperCase()}</span>
            {showTiming && step.duration && (
              <span className="text-xs font-mono text-brand-text-muted px-1.5 py-0.5 rounded bg-brand-surface">
                {formatDuration(step.duration)}
              </span>
            )}
            {showConfidence && step.confidence !== undefined && (
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                step.confidence! >= 0.9 ? 'bg-status-success/20 text-status-success' :
                step.confidence! >= 0.7 ? 'bg-status-warning/20 text-status-warning' :
                'bg-status-error/20 text-status-error'
              }`}>
                {(step.confidence! * 100).toFixed(0)}%
              </span>
            )}
            <span className="text-[10px] text-brand-text-muted font-mono ml-auto">
              {formatTimestamp(step.timestamp)}
            </span>
          </div>
          
          <div className="text-sm text-brand-text line-clamp-2 mb-2">
            {showRaw && step.rawContent ? step.rawContent : step.content}
          </div>

          {/* Tool calls summary */}
          {(step.toolCalls && step.toolCalls.length > 0) && (
            <div className="flex flex-wrap gap-1 mb-2">
              {step.toolCalls.slice(0, 3).map((tc, ti) => (
                <span key={ti} className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-brand-surface text-brand-text-muted border border-brand-border">
                  {tc.name}
                </span>
              ))}
              {step.toolCalls.length > 3 && (
                <span className="px-1.5 py-0.5 rounded text-[10px] text-brand-text-muted">
                  +{step.toolCalls.length - 3} more
                </span>
              )}
            </div>
          )}

          {/* Tool results summary */}
          {(step.toolResults && step.toolResults.length > 0) && (
            <div className="flex items-center gap-1.5 text-[10px] mb-2">
              <span className="flex items-center gap-1 text-status-success">
                <Check className="w-3 h-3" />
                {step.toolResults.filter(r => r.success).length}
              </span>
              <span className="flex items-center gap-1 text-status-error">
                <X className="w-3 h-3" />
                {step.toolResults.filter(r => !r.success).length}
              </span>
            </div>
          )}
        </div>

        <div className="flex-shrink-0 flex items-center gap-1">
          <button
            onClick={(e) => { e.stopPropagation(); onToggleExpand(); }}
            className="p-1 rounded hover:bg-brand-surface-elevated transition-colors"
          >
            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="mt-3 pt-3 border-t border-brand-border/50 animate-in">
          <div className="space-y-3">
            {/* Full Content */}
            <div className="p-3 bg-brand-surface-elevated rounded border border-brand-border">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-brand-text">Full Content</span>
                <label className="flex items-center gap-1 text-xs text-brand-text-muted cursor-pointer">
                  <input
                    type="checkbox"
                    checked={showRaw}
                    onChange={(e) => { /* would need parent callback */ }}
                    className="w-3 h-3 accent-brand-primary"
                  />
                  Raw
                </label>
              </div>
              <pre className="whitespace-pre-wrap text-sm text-brand-text font-mono max-h-60 overflow-y-auto">
                {showRaw && step.rawContent ? step.rawContent : step.content}
              </pre>
            </div>

            {/* Tool Calls */}
            {step.toolCalls && step.toolCalls.length > 0 && (
              <div className="space-y-2">
                <h5 className="flex items-center gap-1 text-xs font-medium text-brand-text-muted">
                  <Terminal className="w-3 h-3" />
                  Tool Calls ({step.toolCalls.length})
                </h5>
                {step.toolCalls.map((tc, ti) => (
                  <div key={tc.id} className="p-2 bg-brand-surface-elevated rounded border border-brand-border">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium text-brand-text flex items-center gap-1">
                        <Code2 className="w-3 h-3" />
                        {tc.name}
                      </span>
                      <span className="text-xs font-mono text-brand-text-muted">#{tc.id.slice(-6)}</span>
                    </div>
                    <pre className="text-xs text-brand-text overflow-x-auto font-mono max-h-32 overflow-y-auto">
                      {JSON.stringify(tc.arguments, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            )}

            {/* Tool Results */}
            {step.toolResults && step.toolResults.length > 0 && (
              <div className="space-y-2">
                <h5 className="flex items-center gap-1 text-xs font-medium text-brand-text-muted">
                  <Info className="w-3 h-3" />
                  Tool Results ({step.toolResults.length})
                </h5>
                {step.toolResults.map((tr, ti) => (
                  <div key={ti} className={`p-2 rounded border ${tr.success ? 'border-status-success/30 bg-status-success/5' : 'border-status-error/30 bg-status-error/5'}`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-mono text-brand-text-muted">#{tr.toolCallId.slice(-6)}</span>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${tr.success ? 'bg-status-success/20 text-status-success' : 'bg-status-error/20 text-status-error'}`}>
                        {tr.success ? 'SUCCESS' : 'FAILED'}
                      </span>
                    </div>
                    <pre className="text-xs text-brand-text overflow-x-auto font-mono max-h-32 overflow-y-auto">
                      {tr.output.slice(0, 3000)}
                    </pre>
                    {tr.error && (
                      <div className="mt-1 p-1 bg-status-error/10 rounded text-xs text-status-error font-mono">
                        {tr.error}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Confidence Bar */}
            {step.confidence !== undefined && (
              <div className="p-2 bg-brand-surface-elevated rounded border border-brand-border">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-brand-text">Confidence</span>
                  <span className={`text-sm font-bold ${step.confidence! >= 0.9 ? 'text-status-success' : step.confidence! >= 0.7 ? 'text-status-warning' : 'text-status-error'}`}>
                    {(step.confidence! * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="h-2 bg-brand-surface rounded overflow-hidden">
                  <div 
                    className={`h-full rounded ${step.confidence! >= 0.9 ? 'bg-status-success' : step.confidence! >= 0.7 ? 'bg-status-warning' : 'bg-status-error'}`}
                    style={{ width: `${step.confidence! * 100}%` }}
                  />
                </div>
              </div>
            )}

            {/* Metadata */}
            {step.metadata && Object.keys(step.metadata).length > 0 && (
              <div className="p-2 bg-brand-surface-elevated rounded border border-brand-border">
                <h5 className="text-xs font-medium text-brand-text-muted mb-1">Metadata</h5>
                <pre className="text-[10px] text-brand-text-muted overflow-x-auto font-mono">
                  {JSON.stringify(step.metadata, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function formatDuration(ms: number) {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatTimestamp(ts: number) {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function getTypeIcon(type: string) {
  switch (type) {
    case 'thought': return <Brain className="w-4 h-4 text-brand-primary" />;
    case 'action': return <Zap className="w-4 h-4 text-brand-orange" />;
    case 'observation': return <Eye className="w-4 h-4 text-status-info" />;
    case 'decision': return <Target className="w-4 h-4 text-status-warning" />;
    case 'error': return <AlertTriangle className="w-4 h-4 text-status-error" />;
    case 'summary': return <Sparkles className="w-4 h-4 text-status-success" />;
    default: return <MessageSquare className="w-4 h-4 text-brand-text-muted" />;
  }
}
