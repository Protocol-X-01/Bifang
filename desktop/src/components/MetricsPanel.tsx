import { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { 
  Cpu, 
  MemoryStick, 
  HardDrive, 
  Network, 
  Thermometer, 
  Zap,
  Activity,
  ChevronDown,
  ChevronUp,
  Maximize2,
  Minimize2
} from 'lucide-react';

interface SystemMetrics {
  cpu: {
    usage: number;
    cores: number;
    model: string;
    frequencies: number[];
    temperatures: number[];
  };
  memory: {
    total: number;
    used: number;
    available: number;
    swapTotal: number;
    swapUsed: number;
  };
  disk: {
    total: number;
    used: number;
    available: number;
    readSpeed: number;
    writeSpeed: number;
  };
  network: {
    interfaces: NetworkInterface[];
    totalRx: number;
    totalTx: number;
  };
  gpu?: {
    name: string;
    usage: number;
    memoryUsed: number;
    memoryTotal: number;
    temperature: number;
    powerDraw: number;
  };
  processes: ProcessInfo[];
}

interface NetworkInterface {
  name: string;
  rx: number;
  tx: number;
  rxSpeed: number;
  txSpeed: number;
}

interface ProcessInfo {
  pid: number;
  name: string;
  cpuPercent: number;
  memoryPercent: number;
  memoryUsed: number;
  status: string;
  user: string;
}

export function MetricsPanel({ compact = false }: { compact?: boolean }) {
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [expanded, setExpanded] = useState(!compact);
  const [sortBy, setSortBy] = useState<'cpu' | 'memory' | 'name'>('cpu');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [selectedProcess, setSelectedProcess] = useState<ProcessInfo | null>(null);
  const [history, setHistory] = useState<{ cpu: number[]; memory: number[]; network: { rx: number[]; tx: number[] } }>({
    cpu: [],
    memory: [],
    network: { rx: [], tx: [] },
  });

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        // In real implementation, this would call Tauri commands
        // const data = await invoke<SystemMetrics>('get_system_metrics');
        // setMetrics(data);
        
        // Mock data for demonstration
        const mockMetrics: SystemMetrics = {
          cpu: {
            usage: Math.random() * 30 + 10,
            cores: 16,
            model: 'AMD Ryzen 9 7950X',
            frequencies: Array(16).fill(0).map(() => 4200 + Math.random() * 800),
            temperatures: Array(16).fill(0).map(() => 45 + Math.random() * 20),
          },
          memory: {
            total: 64 * 1024 * 1024 * 1024,
            used: (Math.random() * 20 + 10) * 1024 * 1024 * 1024,
            available: 0,
            swapTotal: 8 * 1024 * 1024 * 1024,
            swapUsed: Math.random() * 2 * 1024 * 1024 * 1024,
          },
          disk: {
            total: 2 * 1024 * 1024 * 1024 * 1024,
            used: 1.2 * 1024 * 1024 * 1024 * 1024,
            available: 0,
            readSpeed: Math.random() * 500 * 1024 * 1024,
            writeSpeed: Math.random() * 300 * 1024 * 1024,
          },
          network: {
            interfaces: [
              { name: 'eth0', rx: 0, tx: 0, rxSpeed: Math.random() * 50 * 1024 * 1024, txSpeed: Math.random() * 20 * 1024 * 1024 },
              { name: 'lo', rx: 0, tx: 0, rxSpeed: 0, txSpeed: 0 },
            ],
            totalRx: 0,
            totalTx: 0,
          },
          gpu: {
            name: 'NVIDIA RTX 4090',
            usage: Math.random() * 40,
            memoryUsed: 8 * 1024 * 1024 * 1024,
            memoryTotal: 24 * 1024 * 1024 * 1024,
            temperature: 55 + Math.random() * 20,
            powerDraw: 200 + Math.random() * 150,
          },
          processes: Array(50).fill(0).map((_, i) => ({
            pid: 1000 + i,
            name: ['bifang', 'node', 'python3', 'code', 'chrome', 'firefox', 'docker', 'postgres', 'redis', 'nginx'][i % 10] + (i > 9 ? ` ${i}` : ''),
            cpuPercent: Math.random() * 20,
            memoryPercent: Math.random() * 10,
            memoryUsed: Math.random() * 4 * 1024 * 1024 * 1024,
            status: ['R', 'S', 'D', 'Z'][Math.floor(Math.random() * 4)],
            user: 'user',
          })),
        };
        setMetrics(mockMetrics);
        
        // Update history
        setHistory(prev => ({
          cpu: [...prev.cpu.slice(-59), mockMetrics.cpu.usage],
          memory: [...prev.memory.slice(-59), (mockMetrics.memory.used / mockMetrics.memory.total) * 100],
          network: {
            rx: [...prev.network.rx.slice(-59), mockMetrics.network.totalRx],
            tx: [...prev.network.tx.slice(-59), mockMetrics.network.totalTx],
          },
        }));
      } catch (e) {
        console.error('Failed to fetch metrics:', e);
      }
    };

    fetchMetrics();
    const interval = setInterval(fetchMetrics, 2000);
    return () => clearInterval(interval);
  }, []);

  if (!metrics) {
    return (
      <div className="flex items-center justify-center h-full bg-brand-surface">
        <Activity className="w-8 h-8 animate-spin text-brand-primary" />
      </div>
    );
  }

  const formatBytes = (bytes: number) => {
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    while (bytes >= 1024 && i < units.length - 1) {
      bytes /= 1024;
      i++;
    }
    return `${bytes.toFixed(1)} ${units[i]}`;
  };

  const formatSpeed = (bytesPerSec: number) => {
    return `${formatBytes(bytesPerSec)}/s`;
  };

  const getUsageColor = (percent: number) => {
    if (percent >= 90) return 'text-status-error';
    if (percent >= 70) return 'text-status-warning';
    if (percent >= 50) return 'text-status-info';
    return 'text-status-success';
  };

  const Sparkline = ({ data, color, height = 40 }: { data: number[]; color: string; height?: number }) => {
    if (data.length < 2) return <div className="h-[40px]" />;
    
    const max = Math.max(...data, 1);
    const min = Math.min(...data);
    const range = max - min || 1;
    
    const points = data.map((value, i) => {
      const x = (i / (data.length - 1)) * 100;
      const y = 100 - ((value - min) / range) * 100;
      return `${x}%,${y}%`;
    }).join(' ');

    return (
      <svg viewBox="0 0 100 100" className="w-full h-[40px]" preserveAspectRatio="none">
        <defs>
          <linearGradient id="sparkline-gradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor={color} stopOpacity="0.8" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon
          points={`0,100 ${points} 100,100`}
          fill="url(#sparkline-gradient)"
        />
        <polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  };

  const sortedProcesses = [...metrics.processes].sort((a, b) => {
    let aVal = sortBy === 'cpu' ? a.cpuPercent : sortBy === 'memory' ? a.memoryPercent : a.name;
    let bVal = sortBy === 'cpu' ? b.cpuPercent : sortBy === 'memory' ? b.memoryPercent : b.name;
    if (sortDir === 'asc') return aVal > bVal ? 1 : -1;
    return aVal < bVal ? 1 : -1;
  });

  if (compact) {
    return (
      <div className="bg-brand-surface border border-brand-border rounded-xl p-4">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            icon={<Cpu className="w-5 h-5 text-brand-primary" />}
            label="CPU"
            value={`${metrics.cpu.usage.toFixed(1)}%`}
            sparkline={history.cpu}
            color="text-brand-primary"
            usage={metrics.cpu.usage}
          />
          <MetricCard
            icon={<MemoryStick className="w-5 h-5 text-brand-orange" />}
            label="Memory"
            value={`${((metrics.memory.used / metrics.memory.total) * 100).toFixed(1)}%`}
            detail={`${formatBytes(metrics.memory.used)} / ${formatBytes(metrics.memory.total)}`}
            sparkline={history.memory}
            color="text-brand-orange"
            usage={(metrics.memory.used / metrics.memory.total) * 100}
          />
          <MetricCard
            icon={<HardDrive className="w-5 h-5 text-status-info" />}
            label="Disk"
            value={`${((metrics.disk.used / metrics.disk.total) * 100).toFixed(1)}%`}
            detail={`${formatBytes(metrics.disk.used)} / ${formatBytes(metrics.disk.total)}`}
            sparkline={[]}
            color="text-status-info"
            usage={(metrics.disk.used / metrics.disk.total) * 100}
          />
          <MetricCard
            icon={<Network className="w-5 h-5 text-status-success" />}
            label="Network"
            value={formatSpeed(metrics.network.totalRx + metrics.network.totalTx)}
            detail={`↓ ${formatSpeed(metrics.network.interfaces[0]?.rxSpeed || 0)} ↑ ${formatSpeed(metrics.network.interfaces[0]?.txSpeed || 0)}`}
            sparkline={history.network.rx}
            color="text-status-success"
            usage={0}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="bg-brand-surface border border-brand-border rounded-xl overflow-hidden flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-brand-border flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-brand-primary/20 rounded-lg">
            <Activity className="w-5 h-5 text-brand-primary" />
          </div>
          <div>
            <h3 className="font-medium text-brand-text">Demo Metrics (Simulated)</h3>
            <p className="text-xs text-brand-text-muted">Illustrative values only; live hardware telemetry is not connected.</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1.5 rounded hover:bg-brand-surface-elevated transition-colors"
            title={expanded ? 'Collapse' : 'Expand'}
          >
            {expanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Overview Cards */}
      <div className="px-4 py-3 border-b border-brand-border">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            icon={<Cpu className="w-5 h-5 text-brand-primary" />}
            label="CPU"
            value={`${metrics.cpu.usage.toFixed(1)}%`}
            sparkline={history.cpu}
            color="text-brand-primary"
            usage={metrics.cpu.usage}
            detail={`${metrics.cpu.cores} cores • ${metrics.cpu.temperatures[0]?.toFixed(0)}°C`}
          />
          <MetricCard
            icon={<MemoryStick className="w-5 h-5 text-brand-orange" />}
            label="Memory"
            value={`${((metrics.memory.used / metrics.memory.total) * 100).toFixed(1)}%`}
            detail={`${formatBytes(metrics.memory.used)} / ${formatBytes(metrics.memory.total)}`}
            sparkline={history.memory}
            color="text-brand-orange"
            usage={(metrics.memory.used / metrics.memory.total) * 100}
          />
          <MetricCard
            icon={<HardDrive className="w-5 h-5 text-status-info" />}
            label="Disk"
            value={`${((metrics.disk.used / metrics.disk.total) * 100).toFixed(1)}%`}
            detail={`R: ${formatSpeed(metrics.disk.readSpeed)} W: ${formatSpeed(metrics.disk.writeSpeed)}`}
            sparkline={[]}
            color="text-status-info"
            usage={(metrics.disk.used / metrics.disk.total) * 100}
          />
          <MetricCard
            icon={metrics.gpu ? <Zap className="w-5 h-5 text-brand-orange" /> : <Network className="w-5 h-5 text-status-success" />}
            label={metrics.gpu ? 'GPU' : 'Network'}
            value={metrics.gpu ? `${metrics.gpu.usage.toFixed(1)}%` : formatSpeed(metrics.network.totalRx + metrics.network.totalTx)}
            detail={metrics.gpu 
              ? `${formatBytes(metrics.gpu.memoryUsed)} / ${formatBytes(metrics.gpu.memoryTotal)} • ${metrics.gpu.temperature.toFixed(0)}°C • ${metrics.gpu.powerDraw.toFixed(0)}W`
              : `↓ ${formatSpeed(metrics.network.interfaces[0]?.rxSpeed || 0)} ↑ ${formatSpeed(metrics.network.interfaces[0]?.txSpeed || 0)}`}
            sparkline={metrics.gpu ? [] : history.network.rx}
            color={metrics.gpu ? 'text-brand-orange' : 'text-status-success'}
            usage={metrics.gpu ? metrics.gpu.usage : 0}
          />
        </div>
      </div>

      {/* GPU Details */}
      {metrics.gpu && expanded && (
        <div className="px-4 py-3 border-b border-brand-border">
          <h4 className="flex items-center gap-2 text-sm font-medium text-brand-text mb-3">
            <Zap className="w-4 h-4 text-brand-orange" />
            GPU: {metrics.gpu.name}
          </h4>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-brand-surface-elevated rounded-lg p-4">
              <div className="text-xs text-brand-text-muted mb-1">GPU Usage</div>
              <div className="flex items-end gap-2">
                <span className="text-2xl font-bold font-mono text-brand-text">{metrics.gpu.usage.toFixed(1)}%</span>
                <span className="text-sm text-brand-text-muted mb-1">Temp: {metrics.gpu.temperature.toFixed(0)}°C</span>
              </div>
              <div className="h-2 bg-brand-surface rounded overflow-hidden mt-2">
                <div 
                  className="h-full bg-brand-primary rounded transition-all duration-300"
                  style={{ width: `${metrics.gpu.usage}%` }}
                />
              </div>
            </div>
            <div className="bg-brand-surface-elevated rounded-lg p-4">
              <div className="text-xs text-brand-text-muted mb-1">VRAM</div>
              <div className="flex items-end gap-2">
                <span className="text-2xl font-bold font-mono text-brand-text">
                  {((metrics.gpu.memoryUsed / metrics.gpu.memoryTotal) * 100).toFixed(1)}%
                </span>
              </div>
              <div className="h-2 bg-brand-surface rounded overflow-hidden mt-2">
                <div 
                  className="h-full bg-brand-orange rounded transition-all duration-300"
                  style={{ width: `${(metrics.gpu.memoryUsed / metrics.gpu.memoryTotal) * 100}%` }}
                />
              </div>
              <div className="text-xs text-brand-text-muted mt-1">
                {formatBytes(metrics.gpu.memoryUsed)} / {formatBytes(metrics.gpu.memoryTotal)}
              </div>
            </div>
            <div className="bg-brand-surface-elevated rounded-lg p-4">
              <div className="text-xs text-brand-text-muted mb-1">Temperature</div>
              <div className="text-2xl font-bold font-mono text-brand-text">{metrics.gpu.temperature.toFixed(0)}°C</div>
            </div>
            <div className="bg-brand-surface-elevated rounded-lg p-4">
              <div className="text-xs text-brand-text-muted mb-1">Power Draw</div>
              <div className="text-2xl font-bold font-mono text-brand-text">{metrics.gpu.powerDraw.toFixed(0)}W</div>
            </div>
          </div>
        </div>
      )}

      {/* Process Table */}
      {expanded && (
        <div className="flex-1 overflow-hidden p-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="flex items-center gap-2 text-sm font-medium text-brand-text">
              <Activity className="w-4 h-4" />
              Processes ({metrics.processes.length})
            </h4>
            <div className="flex items-center gap-2">
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as any)}
                className="px-2 py-1 bg-brand-surface-elevated border border-brand-border rounded text-sm text-brand-text focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary"
              >
                <option value="cpu">CPU %</option>
                <option value="memory">Memory %</option>
                <option value="name">Name</option>
              </select>
              <button
                onClick={() => setSortDir(sortDir === 'asc' ? 'desc' : 'asc')}
                className="p-1.5 rounded hover:bg-brand-surface-elevated transition-colors"
                title="Toggle sort direction"
              >
                {sortDir === 'asc' ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
            </div>
          </div>
          
          <div className="overflow-x-auto overflow-y-auto flex-1">
            <table className="w-full text-sm font-mono">
              <thead>
                <tr className="text-xs text-brand-text-muted border-b border-brand-border">
                  <th className="px-3 py-2 text-left cursor-pointer hover:text-brand-text" onClick={() => { setSortBy('name'); setSortDir('asc'); }}>
                    Name {sortBy === 'name' && (sortDir === 'asc' ? ' ▲' : ' ▼')}
                  </th>
                  <th className="px-3 py-2 text-right cursor-pointer hover:text-brand-text" onClick={() => { setSortBy('cpu'); setSortDir('desc'); }}>
                    CPU% {sortBy === 'cpu' && (sortDir === 'asc' ? ' ▲' : ' ▼')}
                  </th>
                  <th className="px-3 py-2 text-right cursor-pointer hover:text-brand-text" onClick={() => { setSortBy('memory'); setSortDir('desc'); }}>
                    MEM% {sortBy === 'memory' && (sortDir === 'asc' ? ' ▲' : ' ▼')}
                  </th>
                  <th className="px-3 py-2 text-right">MEM</th>
                  <th className="px-3 py-2 text-center">Status</th>
                  <th className="px-3 py-2 text-left">User</th>
                  <th className="px-3 py-2 text-right">PID</th>
                </tr>
              </thead>
              <tbody>
                {sortedProcesses.slice(0, 50).map((proc, i) => (
                  <tr
                    key={proc.pid}
                    className={`border-b border-brand-border/50 hover:bg-brand-surface-elevated/50 ${selectedProcess?.pid === proc.pid ? 'bg-brand-primary/10' : ''}`}
                    onClick={() => setSelectedProcess(selectedProcess?.pid === proc.pid ? null : proc)}
                  >
                    <td className="px-3 py-2 text-brand-text truncate max-w-[200px]">
                      {proc.name}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      <span className={getUsageColor(proc.cpuPercent)}>
                        {proc.cpuPercent.toFixed(1)}%
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      <span className={getUsageColor(proc.memoryPercent)}>
                        {proc.memoryPercent.toFixed(1)}%
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-brand-text-muted">
                      {formatBytes(proc.memoryUsed)}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span className={`px-1.5 py-0.5 rounded text-xs ${
                        proc.status === 'R' ? 'bg-status-success/20 text-status-success' :
                        proc.status === 'S' ? 'bg-status-info/20 text-status-info' :
                        proc.status === 'D' ? 'bg-status-warning/20 text-status-warning' :
                        'bg-status-error/20 text-status-error'
                      }`}>
                        {proc.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-brand-text-muted">{proc.user}</td>
                    <td className="px-3 py-2 text-right font-mono text-brand-text-muted">{proc.pid}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCard({ 
  icon, 
  label, 
  value, 
  detail, 
  sparkline, 
  color, 
  usage, 
  detail: detailProp 
}: { 
  icon: React.ReactNode; 
  label: string; 
  value: string; 
  detail?: string; 
  sparkline: number[]; 
  color: string; 
  usage: number;
  detail?: string;
}) {
  return (
    <div className="bg-brand-surface-elevated border border-brand-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <span className={`${color}`}>{icon}</span>
        <span className="text-xs text-brand-text-muted font-medium">{label}</span>
      </div>
      <div className="flex items-baseline gap-2 mb-2">
        <span className="text-2xl font-bold font-mono text-brand-text">{value}</span>
      </div>
      {detailProp && (
        <div className="text-xs text-brand-text-muted mb-2">{detailProp}</div>
      )}
      <div className="h-12 w-full relative">
        <div className="absolute inset-0 flex items-end">
          <Sparkline 
            data={sparkline} 
            color={color.replace('text-', '')} 
            height={40} 
          />
        </div>
        <div className="absolute bottom-0 left-0 right-0 h-2 bg-brand-surface rounded overflow-hidden">
          <div 
            className={`h-full rounded ${usage >= 90 ? 'bg-status-error' : usage >= 70 ? 'bg-status-warning' : usage >= 50 ? 'bg-status-info' : 'bg-status-success'}`}
            style={{ width: `${Math.min(usage, 100)}%` }}
          />
        </div>
      </div>
      {detailProp && (
        <div className="text-xs text-brand-text-muted mt-1 font-mono">{detailProp}</div>
      )}
    </div>
  );
}
