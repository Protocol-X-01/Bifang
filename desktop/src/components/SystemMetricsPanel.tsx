import { useEffect, useState } from 'react';
import { formatBytes, MetricsPoller, type SystemMetrics } from '../api/systemMetrics';
import { Loader2, AlertTriangle, CheckCircle, Cpu, HardDrive, MemoryStick, Zap } from 'lucide-react';

interface MetricsClient { metrics(workspace: string): Promise<SystemMetrics> }

export function SystemMetricsPanel({ client, workspace }: { client: { metrics: (workspace: string) => Promise<SystemMetrics> }; workspace: string | null }) {
  const [sample, setSample] = useState<SystemMetrics | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    setSample(null); setFailed(false);
    if (!workspace) return;
    const poller = new MetricsPoller(() => client.metrics(workspace), reading => { setSample(reading); setFailed(false); }, () => setFailed(true));
    poller.start();
    return () => poller.stop();
  }, [client, workspace, attempt]);

  const readings = sample ? [
    { name: 'CPU', icon: <Cpu className="w-4 h-4 text-bifang-brand-orange" />, value: sample.cpu.available ? `${sample.cpu.percent.toFixed(1)}%` : 'Unavailable', percent: sample.cpu.available ? sample.cpu.percent : null, detail: sample.cpu.available ? `${sample.cpu.sample_ms} ms target interval · host-wide` : sample.cpu.reason, color: 'text-bifang-brand-orange' },
    { name: 'Memory', icon: <MemoryStick className="w-4 h-4 text-bifang-brand-red" />, value: sample.memory.available ? `${sample.memory.percent.toFixed(1)}%` : 'Unavailable', percent: sample.memory.available ? sample.memory.percent : null, detail: sample.memory.available ? `${formatBytes(sample.memory.available_bytes)} available / ${formatBytes(sample.memory.total_bytes)}` : sample.memory.reason, color: 'text-bifang-brand-red' },
    { name: 'Workspace disk', icon: <HardDrive className="w-4 h-4 text-bifang-brand-orange" />, value: sample.disk.available ? `${sample.disk.percent.toFixed(1)}%` : 'Unavailable', percent: sample.disk.available ? sample.disk.percent : null, detail: sample.disk.available ? `${formatBytes(sample.disk.free_bytes)} free / ${formatBytes(sample.disk.total_bytes)}` : sample.disk.reason, color: 'text-bifang-brand-orange' },
  ] : [];

  return (
    <section aria-label="Local system metrics" className="mt-6 rounded-2xl border-bifang-border bg-bifang-panel p-5 animate-in panel-hover">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h3 className="text-h5 text-bifang-text-primary flex items-center gap-2"><Zap className="w-5 h-5 text-bifang-brand-orange" />Forge pulse</h3>
          <p className="mt-1 text-body-sm text-bifang-text-secondary">Local system readings · refreshes every five seconds while open</p>
        </div>
        {failed && <button className="btn-secondary btn-sm" disabled={!workspace} onClick={() => setAttempt(value => value + 1)}><Loader2 className="w-3.5 h-3.5 mr-1.5" /> Retry readings</button>}
      </div>
      {!workspace && <p className="mt-4 text-body-sm text-bifang-text-muted">Choose a local workspace to see its system and filesystem readings.</p>}
      {workspace && !sample && !failed && <p role="status" className="mt-4 text-body-sm text-bifang-text-muted flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin text-bifang-brand-orange" />Sampling your local system…</p>}
      {failed && <p role="status" className="mt-4 text-body-sm text-bifang-warning">{sample ? 'Last reading shown; refresh is unavailable.' : 'System readings unavailable. Use the latest native desktop build, then retry.'}</p>}
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        {readings.map(reading => (
          <article key={reading.name} className="rounded-xl border-bifang-border bg-bifang-surface p-4 panel-hover animate-in">
            <div className="flex items-center gap-2 mb-2">{reading.icon} <p className="text-overline text-bifang-text-muted">{reading.name}</p></div>
            <p className={`text-2xl font-bold tabular-nums ${reading.color}`}>{reading.value}</p>
            {reading.percent !== null && <progress aria-label={`${reading.name} utilization`} max={100} value={reading.percent} className="mt-3 h-2 w-full accent-bifang-brand-orange" />}
            <p className="mt-2 text-caption text-bifang-text-muted">{reading.detail}</p>
          </article>
        ))}
      </div>
      {sample && (
        <footer className="mt-4 flex flex-wrap justify-between gap-2 text-caption text-bifang-text-muted">
          <p>Sampled <time dateTime={sample.sampled_at}>{new Date(sample.sampled_at).toLocaleTimeString()}</time> · {sample.gpu.reason}</p>
          <p>Local measurements only · separate from model usage and inference latency</p>
        </footer>
      )}
    </section>
  );
}