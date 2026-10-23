import { useState, useEffect } from 'react';
import { 
  CheckCircle, 
  XCircle, 
  AlertCircle, 
  Clock, 
  FileText, 
  ChevronDown, 
  ChevronUp,
  Shield,
  Zap,
  Target,
  Download,
  Copy,
  ExternalLink,
  Eye,
  EyeOff,
  Filter,
  RefreshCw,
  MoreHorizontal,
  Trash2,
  Share2
} from 'lucide-react';
import { invoke } from '@tauri-apps/api/core';

interface TestResult {
  id: string;
  name: string;
  file: string;
  status: 'passed' | 'failed' | 'skipped' | 'running';
  duration: number;
  coverage?: number;
  error?: string;
  timestamp: number;
}

interface DiffCoverage {
  file: string;
  linesChanged: number;
  linesCovered: number;
  coveragePercent: number;
  status: 'covered' | 'partial' | 'uncovered';
}

interface VerificationStamp {
  id: string;
  sessionId: string;
  timestamp: number;
  type: 'verified' | 'failed' | 'partial';
  message: string;
  diffHash: string;
  testResults: TestResult[];
  coverage: DiffCoverage[];
  metadata: {
    model: string;
    provider: string;
    duration: number;
    tokensUsed: number;
  };
}

interface BenchmarkResult {
  name: string;
  before: number;
  after: number;
  unit: string;
  improvement: number;
  status: 'improved' | 'regressed' | 'unchanged';
}

export function VerifyPanel({ sessionId }: { sessionId: string | null }) {
  const [stamps, setStamps] = useState<VerificationStamp[]>([]);
  const [selectedStamp, setSelectedStamp] = useState<VerificationStamp | null>(null);
  const [benchmarks, setBenchmarks] = useState<BenchmarkResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<'all' | 'verified' | 'failed' | 'partial'>('all');
  const [showDetails, setShowDetails] = useState<Record<string, boolean>>({});

  // Load verification stamps from session
  useEffect(() => {
    if (!sessionId) return;
    loadStamps();
  }, [sessionId]);

  const loadStamps = async () => {
    setLoading(true);
    try {
      // In real implementation, this would call the bifang API
      // const data = await invoke('get_verification_stamps', { sessionId });
      // setStamps(data);
      
      // Mock data for demonstration
      const mockStamps: VerificationStamp[] = [
        {
          id: 'stamp-1',
          sessionId: sessionId!,
          timestamp: Date.now() - 3600000,
          type: 'verified',
          message: 'Performance bottleneck optimized - 31.4% improvement',
          diffHash: 'a1b2c3d4',
          testResults: [
            { id: 't1', name: 'test_vector_search', file: 'src/search.rs', status: 'passed', duration: 142, coverage: 94 },
            { id: 't2', name: 'test_benchmark_suite', file: 'benches/main.rs', status: 'passed', duration: 287, coverage: 89 },
            { id: 't3', name: 'test_memory_usage', file: 'src/memory.rs', status: 'passed', duration: 89, coverage: 91 },
          ],
          coverage: [
            { file: 'src/search.rs', linesChanged: 47, linesCovered: 44, coveragePercent: 94, status: 'covered' },
            { file: 'src/memory.rs', linesChanged: 23, linesCovered: 21, coveragePercent: 91, status: 'covered' },
            { file: 'src/index.rs', linesChanged: 12, linesCovered: 8, coveragePercent: 67, status: 'partial' },
          ],
          metadata: { model: 'nemotron-3-ultra', provider: 'nvidia', duration: 12500, tokensUsed: 45230 },
        },
        {
          id: 'stamp-2',
          sessionId: sessionId!,
          timestamp: Date.now() - 7200000,
          type: 'partial',
          message: 'Memory leak fix - partial coverage on new code',
          diffHash: 'e5f6g7h8',
          testResults: [
            { id: 't4', name: 'test_memory_leak', file: 'src/allocator.rs', status: 'passed', duration: 203, coverage: 78 },
            { id: 't5', name: 'test_stress', file: 'tests/stress.rs', status: 'failed', duration: 512, coverage: 0, error: 'Timeout after 30s' },
          ],
          coverage: [
            { file: 'src/allocator.rs', linesChanged: 34, linesCovered: 28, coveragePercent: 82, status: 'covered' },
            { file: 'src/cache.rs', linesChanged: 18, linesCovered: 0, coveragePercent: 0, status: 'uncovered' },
          ],
          metadata: { model: 'nemotron-3-ultra', provider: 'nvidia', duration: 8200, tokensUsed: 28450 },
        },
        {
          id: 'stamp-3',
          sessionId: sessionId!,
          timestamp: Date.now() - 10800000,
          type: 'failed',
          message: 'Refactor introduced regression in parser',
          diffHash: 'i9j0k1l2',
          testResults: [
            { id: 't6', name: 'test_parser_edge_cases', file: 'src/parser.rs', status: 'failed', duration: 89, coverage: 0, error: 'Unexpected token at line 42' },
            { id: 't7', name: 'test_ast_generation', file: 'src/ast.rs', status: 'passed', duration: 156, coverage: 87 },
          ],
          coverage: [
            { file: 'src/parser.rs', linesChanged: 52, linesCovered: 0, coveragePercent: 0, status: 'uncovered' },
            { file: 'src/lexer.rs', linesChanged: 15, linesCovered: 13, coveragePercent: 87, status: 'covered' },
          ],
          metadata: { model: 'nemotron-3-ultra', provider: 'nvidia', duration: 5400, tokensUsed: 18900 },
        },
      ];
      setStamps(mockStamps);
      
      // Mock benchmarks
      const mockBenchmarks: BenchmarkResult[] = [
        { name: 'Vector Search Latency', before: 4.82, after: 3.31, unit: 'ms', improvement: -31.4, status: 'improved' },
        { name: 'Memory Allocation', before: 2.14, after: 1.87, unit: 'MB', improvement: -12.6, status: 'improved' },
        { name: 'Cache Hit Rate', before: 87.3, after: 91.2, unit: '%', improvement: 4.5, status: 'improved' },
        { name: 'Cold Start Time', before: 1.24, after: 1.38, unit: 's', improvement: 11.3, status: 'regressed' },
      ];
      setBenchmarks(mockBenchmarks);
    } catch (e) {
      console.error('Failed to load verification stamps:', e);
    } finally {
      setLoading(false);
    }
  };

  const filteredStamps = stamps.filter(stamp => {
    if (filter === 'all') return true;
    return stamp.type === filter;
  });

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  const formatTimestamp = (ts: number) => {
    return new Date(ts).toLocaleString([], { 
      month: 'short', day: 'numeric', 
      hour: '2-digit', minute: '2-digit' 
    });
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'verified': return <CheckCircle className="w-5 h-5 text-status-success" />;
      case 'failed': return <XCircle className="w-5 h-5 text-status-error" />;
      case 'partial': return <AlertCircle className="w-5 h-5 text-status-warning" />;
      default: return <Clock className="w-5 h-5 text-status-info" />;
    }
  };

  const getTestIcon = (status: string) => {
    switch (status) {
      case 'passed': return <CheckCircle className="w-4 h-4 text-status-success" />;
      case 'failed': return <XCircle className="w-4 h-4 text-status-error" />;
      case 'running': return <Clock className="w-4 h-4 text-status-info animate-spin" />;
      default: return <AlertCircle className="w-4 h-4 text-status-warning" />;
    }
  };

  const getCoverageColor = (percent: number) => {
    if (percent >= 90) return 'text-status-success';
    if (percent >= 70) return 'text-status-warning';
    return 'text-status-error';
  };

  const handleExport = async (stamp: VerificationStamp) => {
    // Generate HTML report
    const report = generateReportHTML(stamp);
    const blob = new Blob([report], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bifang-verify-${stamp.id}.html`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleShare = async (stamp: VerificationStamp) => {
    const report = generateReportHTML(stamp);
    if (navigator.share) {
      const blob = new Blob([report], { type: 'text/html' });
      const file = new File([blob], `bifang-verify-${stamp.id}.html`, { type: 'text/html' });
      await navigator.share({ files: [file], title: `Bifang Verification: ${stamp.message}` });
    }
  };

  const generateReportHTML = (stamp: VerificationStamp): string => {
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Bifang Verification Report - ${stamp.message}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Inter', system-ui, sans-serif; background: #0F1728; color: #F7F7F7; line-height: 1.6; padding: 2rem; max-width: 900px; margin: 0 auto; }
    .header { border-bottom: 1px solid #2D3A50; padding-bottom: 1.5rem; margin-bottom: 2rem; }
    .badge { display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }
    .verified { background: #064E3B; color: #10B981; }
    .failed { background: #7F1D1D; color: #EF4444; }
    .partial { background: #78350F; color: #F59E0B; }
    h1 { font-size: 2rem; font-weight: 700; margin-bottom: 0.5rem; }
    .meta { display: flex; flex-wrap: wrap; gap: 1rem; color: #A0A8B8; font-size: 0.875rem; }
    .section { margin: 2rem 0; }
    h2 { font-size: 1.25rem; font-weight: 600; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; }
    table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; }
    th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid #2D3A50; }
    th { color: #A0A8B8; font-weight: 500; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
    .passed { color: #10B981; }
    .failed { color: #EF4444; }
    .skipped { color: #F59E0B; }
    .running { color: #3B82F6; }
    .coverage-bar { height: 6px; background: #1A2338; border-radius: 3px; overflow: hidden; }
    .coverage-fill { height: 100%; border-radius: 3px; transition: width 0.3s ease; }
    .covered { background: linear-gradient(90deg, #10B981, #059669); }
    .partial { background: linear-gradient(90deg, #F59E0B, #D97706); }
    .uncovered { background: linear-gradient(90deg, #EF4444, #DC2626); }
    .benchmarks { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; }
    .benchmark-card { background: #1A2338; border: 1px solid #2D3A50; border-radius: 0.75rem; padding: 1.5rem; }
    .improved { border-left: 4px solid #10B981; }
    .regressed { border-left: 4px solid #EF4444; }
    .unchanged { border-left: 4px solid #3B82F6; }
    .benchmark-value { font-size: 2rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
    .benchmark-delta { font-size: 1.125rem; font-weight: 600; }
    .improved .benchmark-delta { color: #10B981; }
    .regressed .benchmark-delta { color: #EF4444; }
  </style>
</head>
<body>
  <div class="header">
    <h1>Bifang Verification Report</h1>
    <p style="color: #A0A8B8; margin-top: 0.5rem;">${stamp.message}</p>
    <div class="meta">
      <span><strong>Session:</strong> ${stamp.sessionId.slice(0, 12)}</span>
      <span><strong>Time:</strong> ${new Date(stamp.timestamp).toLocaleString()}</span>
      <span><strong>Model:</strong> ${stamp.metadata.model} (${stamp.metadata.provider})</span>
      <span><strong>Duration:</strong> ${formatDuration(stamp.metadata.duration)}</span>
      <span><strong>Tokens:</strong> ${stamp.metadata.tokensUsed.toLocaleString()}</span>
    </div>
    <span class="badge ${stamp.type}">${stamp.type.toUpperCase()}</span>
  </div>

  <div class="section">
    <h2>📊 Benchmarks</h2>
    <div class="benchmarks">
      ${benchmarks.map(b => `
        <div class="benchmark-card ${b.status}">
          <div style="color: #A0A8B8; font-size: 0.75rem; margin-bottom: 0.5rem;">${b.name}</div>
          <div class="benchmark-value">${b.after.toFixed(2)} ${b.unit}</div>
          <div class="benchmark-delta ${b.status === 'improved' ? 'improved' : b.status === 'regressed' ? 'regressed' : ''}">
            ${b.improvement > 0 ? '+' : ''}${b.improvement.toFixed(1)}%
          </div>
          <div style="color: #A0A8B8; font-size: 0.75rem; margin-top: 0.5rem;">
            Before: ${b.before.toFixed(2)} ${b.unit}
          </div>
        </div>
      `).join('')}
    </div>
  </div>

  <div class="section">
    <h2>🧪 Test Results</h2>
    <table>
      <thead>
        <tr>
          <th>Test</th>
          <th>File</th>
          <th>Status</th>
          <th>Duration</th>
          <th>Coverage</th>
        </tr>
      </thead>
      <tbody>
        ${stamp.testResults.map(t => `
          <tr>
            <td>${t.name}</td>
            <td style="font-family: monospace; font-size: 0.875rem;">${t.file}</td>
            <td><span class="${t.status}">${t.status.toUpperCase()}</span></td>
            <td style="font-family: monospace;">${formatDuration(t.duration)}</td>
            <td>${t.coverage !== undefined ? t.coverage + '%' : 'N/A'}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
    ${stamp.testResults.some(t => t.error) ? `
      <div style="margin-top: 1rem; padding: 1rem; background: #7F1D1D; border-radius: 0.5rem; color: #FECACA;">
        <strong>Errors:</strong>
        <ul style="margin-top: 0.5rem; margin-left: 1.5rem;">
          ${stamp.testResults.filter(t => t.error).map(t => `<li>${t.name}: ${t.error}</li>`).join('')}
        </ul>
      </div>
    ` : ''}
  </div>

  <div class="section">
    <h2>📈 Diff Coverage</h2>
    <table>
      <thead>
        <tr>
          <th>File</th>
          <th>Lines Changed</th>
          <th>Lines Covered</th>
          <th>Coverage</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        ${stamp.coverage.map(c => `
          <tr>
            <td style="font-family: monospace; font-size: 0.875rem;">${c.file}</td>
            <td style="font-family: monospace;">${c.linesChanged}</td>
            <td style="font-family: monospace;">${c.linesCovered}</td>
            <td>
              <div class="coverage-bar">
                <div class="coverage-fill ${c.status}" style="width: ${c.coveragePercent}%"></div>
              </div>
              <span class="${getCoverageColor(c.coveragePercent)}" style="font-family: monospace;">${c.coveragePercent}%</span>
            </td>
            <td>
              <span class="badge ${c.status === 'covered' ? 'verified' : c.status === 'partial' ? 'partial' : 'failed'}">
                ${c.status.toUpperCase()}
              </span>
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2>📋 Metadata</h2>
    <pre style="background: #1A2338; padding: 1rem; border-radius: 0.5rem; overflow-x: auto; font-size: 0.75rem;">${JSON.stringify(stamp.metadata, null, 2)}</pre>
  </div>
</body>
</html>`;
  };

  // Helper functions for HTML generation
  const formatDuration = (ms: number) => ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(2)}s`;
  const getCoverageColor = (percent: number) => percent >= 90 ? 'text-status-success' : percent >= 70 ? 'text-status-warning' : 'text-status-error';

  if (!sessionId) {
    return (
      <div className="flex flex-col h-full bg-brand-background">
        <div className="p-4 border-b border-brand-border">
          <h3 className="font-medium text-brand-text">Verification Panel</h3>
          <p className="text-sm text-brand-text-muted mt-1">Open a workspace session to see verification history</p>
        </div>
        <div className="flex-1 flex items-center justify-center text-brand-text-muted">
          <div className="text-center">
            <Shield className="w-12 h-12 mx-auto mb-4 opacity-30" />
            <p className="text-lg font-medium">No active session</p>
            <p className="text-sm mt-1">Start a chat session to track verifications</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-brand-background">
      {/* Header */}
      <div className="p-4 border-b border-brand-border flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-brand-primary/20 rounded-lg">
            <Shield className="w-5 h-5 text-brand-primary" />
          </div>
          <div>
            <h3 className="font-medium text-brand-text">Verify Panel</h3>
            <p className="text-xs text-brand-text-muted">
              {stamps.length} verification{stamps.length !== 1 ? 's' : ''} • 
              {stamps.filter(s => s.type === 'verified').length} verified • 
              {stamps.filter(s => s.type === 'failed').length} failed
            </p>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as any)}
            className="px-3 py-1.5 bg-brand-surface border border-brand-border rounded-lg text-sm text-brand-text focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary"
          >
            <option value="all">All</option>
            <option value="verified">✓ Verified</option>
            <option value="failed">✗ Failed</option>
            <option value="partial">⚠ Partial</option>
          </select>
          
          <button
            onClick={loadStamps}
            disabled={loading}
            className="p-2 rounded-lg hover:bg-brand-surface-elevated transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Benchmarks Overview */}
      {benchmarks.length > 0 && (
        <div className="px-4 py-3 border-b border-brand-border">
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-medium text-brand-text flex items-center gap-2">
              <Zap className="w-4 h-4 text-brand-orange" />
              Performance Benchmarks
            </h4>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {benchmarks.map((b) => (
              <div
                key={b.name}
                className={`p-3 rounded-lg ${b.status === 'improved' ? 'bg-status-success/10 border-l-4 border-status-success' : 
                  b.status === 'regressed' ? 'bg-status-error/10 border-l-4 border-status-error' : 
                  'bg-status-info/10 border-l-4 border-status-info'} border border-brand-border`}
              >
                <div className="text-xs text-brand-text-muted mb-1">{b.name}</div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-bold font-mono text-brand-text">{b.after.toFixed(2)}</span>
                  <span className="text-sm text-brand-text-muted">{b.unit}</span>
                </div>
                <div className="flex items-center gap-1 mt-1">
                  <span className={`text-sm font-semibold ${b.status === 'improved' ? 'text-status-success' : 
                    b.status === 'regressed' ? 'text-status-error' : 'text-status-info'}`}>
                    {b.improvement > 0 ? '+' : ''}{b.improvement.toFixed(1)}%
                  </span>
                  <span className="text-xs text-brand-text-muted">vs {b.before.toFixed(2)} {b.unit}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Verification Stamps */}
      <div className="flex-1 overflow-y-auto p-4 scrollbar-thin">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <RefreshCw className="w-8 h-8 animate-spin text-brand-primary" />
          </div>
        ) : filteredStamps.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-brand-text-muted">
            <Shield className="w-12 h-12 mb-4 opacity-30" />
            <p className="text-lg font-medium">No verification stamps yet</p>
            <p className="text-sm mt-1">Run tests or ask Bifang to verify changes</p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredStamps.map((stamp) => (
              <VerificationStampCard
                key={stamp.id}
                stamp={stamp}
                benchmarks={benchmarks}
                onSelect={setSelectedStamp}
                onExport={() => handleExport(stamp)}
                onShare={() => handleShare(stamp)}
                isSelected={selectedStamp?.id === stamp.id}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function VerificationStampCard({ 
  stamp, 
  benchmarks,
  onSelect, 
  onExport, 
  onShare,
  isSelected 
}: { 
  stamp: VerificationStamp; 
  benchmarks: BenchmarkResult[];
  onSelect: () => void;
  onExport: () => void;
  onShare: () => void;
  isSelected: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'verified': return 'border-status-success bg-status-success/10';
      case 'failed': return 'border-status-error bg-status-error/10';
      case 'partial': return 'border-status-warning bg-status-warning/10';
      default: return 'border-brand-border bg-brand-surface';
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'verified': return <CheckCircle className="w-5 h-5 text-status-success" />;
      case 'failed': return <XCircle className="w-5 h-5 text-status-error" />;
      case 'partial': return <AlertCircle className="w-5 h-5 text-status-warning" />;
      default: return <Clock className="w-5 h-5 text-status-info" />;
    }
  };

  return (
    <div
      className={`group relative p-4 rounded-xl border transition-all duration-200 ${getTypeColor(stamp.type)} ${isSelected ? 'ring-2 ring-brand-primary' : ''}`}
      onClick={onSelect}
    >
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-lg bg-brand-surface-elevated flex-shrink-0">
          {getTypeIcon(stamp.type)}
        </div>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
              stamp.type === 'verified' ? 'bg-status-success/20 text-status-success' :
              stamp.type === 'failed' ? 'bg-status-error/20 text-status-error' :
              'bg-status-warning/20 text-status-warning'
            }`}>
              {stamp.type.toUpperCase()}
            </span>
            <span className="text-xs text-brand-text-muted">
              {new Date(stamp.timestamp).toLocaleString([], { 
                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' 
              })}
            </span>
            <span className="text-xs text-brand-text-muted font-mono">
              #{stamp.diffHash.slice(0, 8)}
            </span>
          </div>
          
          <p className="text-sm text-brand-text font-medium mb-2">{stamp.message}</p>
          
          {/* Quick Stats */}
          <div className="flex flex-wrap gap-4 text-xs text-brand-text-muted mb-2">
            <span className="flex items-center gap-1">
              <CheckCircle className="w-3 h-3 text-status-success" />
              {stamp.testResults.filter(t => t.status === 'passed').length} passed
            </span>
            <span className="flex items-center gap-1">
              <XCircle className="w-3 h-3 text-status-error" />
              {stamp.testResults.filter(t => t.status === 'failed').length} failed
            </span>
            <span className="flex items-center gap-1">
              <Zap className="w-3 h-3 text-brand-orange" />
              {formatDuration(stamp.metadata.duration)}
            </span>
            <span className="flex items-center gap-1">
              <Target className="w-3 h-3 text-brand-primary" />
              {Math.round(stamp.coverage.reduce((a, c) => a + c.coveragePercent, 0) / stamp.coverage.length)}% avg coverage
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 ml-auto">
          <button
            onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
            className="p-1.5 rounded hover:bg-brand-surface-elevated transition-colors"
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onExport(); }}
            className="p-1.5 rounded hover:bg-brand-surface-elevated transition-colors"
            title="Export HTML report"
          >
            <Download className="w-4 h-4" />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onShare(); }}
            className="p-1.5 rounded hover:bg-brand-surface-elevated transition-colors"
            title="Share"
          >
            <Share2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Expanded Details */}
      {expanded && (
        <div className="mt-4 pt-4 border-t border-brand-border animate-in">
          {/* Test Results */}
          <div className="mb-4">
            <h5 className="flex items-center gap-2 text-sm font-medium text-brand-text mb-3">
              <FileText className="w-4 h-4" />
              Test Results ({stamp.testResults.length})
            </h5>
            <div className="space-y-2 max-h-60 overflow-y-auto scrollbar-thin">
              {stamp.testResults.map((test) => (
                <div key={test.id} className="flex items-center gap-3 p-3 bg-brand-surface-elevated rounded-lg">
                  <div className="flex-shrink-0">
                    {test.status === 'passed' ? (
                      <CheckCircle className="w-5 h-5 text-status-success" />
                    ) : test.status === 'failed' ? (
                      <XCircle className="w-5 h-5 text-status-error" />
                    ) : (
                      <Clock className="w-5 h-5 text-status-info animate-spin" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm text-brand-text">{test.name}</span>
                      <span className="px-1.5 py-0.5 rounded text-xs font-medium ${
                        test.status === 'passed' ? 'bg-status-success/20 text-status-success' :
                        test.status === 'failed' ? 'bg-status-error/20 text-status-error' :
                        'bg-status-info/20 text-status-info'
                      }">
                        {test.status.toUpperCase()}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-brand-text-muted">
                      <span className="flex items-center gap-1">
                        <FileText className="w-3 h-3" />
                        {test.file}
                      </span>
                      <span className="font-mono">{formatDuration(test.duration)}</span>
                      {test.coverage !== undefined && (
                        <span className={`font-medium ${test.coverage >= 90 ? 'text-status-success' : test.coverage >= 70 ? 'text-status-warning' : 'text-status-error'}`}>
                          {test.coverage}%
                        </span>
                      )}
                    </div>
                  </div>
                  {test.error && (
                    <div className="ml-10 mt-2 p-2 bg-status-error/10 rounded text-xs text-status-error font-mono">
                      {test.error}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Coverage */}
          <div className="mb-4">
            <h5 className="flex items-center gap-2 text-sm font-medium text-brand-text mb-3">
              <Target className="w-4 h-4" />
              Diff Coverage
            </h5>
            <div className="space-y-2">
              {stamp.coverage.map((cov) => (
                <div key={cov.file} className="p-3 bg-brand-surface-elevated rounded-lg">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-sm text-brand-text truncate flex-1">{cov.file}</span>
                    <span className={`font-mono font-medium ${cov.coveragePercent >= 90 ? 'text-status-success' : cov.coveragePercent >= 70 ? 'text-status-warning' : 'text-status-error'}`}>
                      {cov.coveragePercent}%
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-2 bg-brand-surface rounded overflow-hidden">
                      <div 
                        className={`h-full rounded ${cov.status === 'covered' ? 'bg-status-success' : cov.status === 'partial' ? 'bg-status-warning' : 'bg-status-error'}`}
                        style={{ width: `${cov.coveragePercent}%` }}
                      />
                    </div>
                    <span className="text-xs text-brand-text-muted font-mono w-20 text-right">
                      {cov.linesCovered}/{cov.linesChanged}
                    </span>
                    <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                      cov.status === 'covered' ? 'bg-status-success/20 text-status-success' :
                      cov.status === 'partial' ? 'bg-status-warning/20 text-status-warning' :
                      'bg-status-error/20 text-status-error'
                    }`}>
                      {cov.status.toUpperCase()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Metadata */}
          <div className="mb-4">
            <h5 className="flex items-center gap-2 text-sm font-medium text-brand-text mb-3">
              <Shield className="w-4 h-4" />
              Metadata
            </h5>
            <pre className="p-3 bg-brand-surface rounded-lg text-xs text-brand-text-muted overflow-x-auto font-mono">
              {JSON.stringify(stamp.metadata, null, 2)}
            </pre>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 pt-4 border-t border-brand-border">
            <button
              onClick={(e) => { e.stopPropagation(); onExport(); }}
              className="flex-1 btn btn-sm btn-secondary"
            >
              <Download className="w-4 h-4 mr-1" />
              Export HTML Report
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onShare(); }}
              className="flex-1 btn btn-sm btn-ghost"
            >
              <Share2 className="w-4 h-4 mr-1" />
              Share
            </button>
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