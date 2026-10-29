type Unavailable = { available: false; reason: string };
type Cpu = Unavailable | { available: true; percent: number; sample_ms: number };
type Memory = Unavailable | { available: true; percent: number; total_bytes: number; available_bytes: number; used_bytes: number };
type Disk = Unavailable | { available: true; percent: number; total_bytes: number; free_bytes: number; used_bytes: number };
export interface SystemMetrics {
  schema: 1; sampled_at: string; collection_ms: number; scope: string;
  cpu: Cpu; memory: Memory; disk: Disk; gpu: Unavailable;
}
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid system reading');
  return value as Record<string, unknown>;
}
function text(value: unknown, max = 1000): string {
  if (typeof value !== 'string' || !value || value.length > max) throw new Error('Invalid metrics text');
  return value;
}
function number(value: unknown, max = Number.MAX_SAFE_INTEGER): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > max) throw new Error('Invalid metrics number');
  return value;
}
function bytes(value: unknown): number {
  const result = number(value);
  if (!Number.isSafeInteger(result)) throw new Error('Invalid byte counter');
  return result;
}
function unavailable(value: Record<string, unknown>): Unavailable | null {
  if (value.available === false) return { available: false, reason: text(value.reason) };
  if (value.available !== true) throw new Error('Invalid reading availability');
  return null;
}
export function parseSystemMetrics(value: unknown): SystemMetrics {
  const result = object(value);
  const sampled_at = text(result.sampled_at, 64);
  if (result.schema !== 1 || !Number.isFinite(Date.parse(sampled_at))) throw new Error('Invalid metrics sample');
  const cpu = object(result.cpu), memory = object(result.memory), disk = object(result.disk), gpu = object(result.gpu);
  const missingCpu = unavailable(cpu), missingMemory = unavailable(memory), missingDisk = unavailable(disk), missingGpu = unavailable(gpu);
  if (!missingGpu) throw new Error('Unsupported GPU telemetry source');
  const memoryData: Memory = missingMemory || { available: true, percent: number(memory.percent, 100), total_bytes: bytes(memory.total_bytes), available_bytes: bytes(memory.available_bytes), used_bytes: bytes(memory.used_bytes) };
  if (memoryData.available && (memoryData.total_bytes === 0 || memoryData.available_bytes + memoryData.used_bytes !== memoryData.total_bytes)) throw new Error('Inconsistent memory counters');
  const diskData: Disk = missingDisk || { available: true, percent: number(disk.percent, 100), total_bytes: bytes(disk.total_bytes), free_bytes: bytes(disk.free_bytes), used_bytes: bytes(disk.used_bytes) };
  if (diskData.available && (diskData.total_bytes === 0 || diskData.used_bytes > diskData.total_bytes || diskData.free_bytes > diskData.total_bytes)) throw new Error('Inconsistent disk counters');
  return { schema: 1, sampled_at, collection_ms: number(result.collection_ms, 60000), scope: text(result.scope),
    cpu: missingCpu || { available: true, percent: number(cpu.percent, 100), sample_ms: number(cpu.sample_ms, 1000) }, memory: memoryData, disk: diskData, gpu: missingGpu };
}
export function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value < 0) return 'Unavailable';
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];
  const index = Math.min(units.length - 1, Math.floor(Math.log2(Math.max(1, value)) / 10));
  return `${(value / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

export class MetricsPoller {
  private stopped = false;
  private started = false;
  private timer: ReturnType<typeof setTimeout> | null = null;
  constructor(private read: () => Promise<SystemMetrics>, private changed: (sample: SystemMetrics) => void,
              private failed: () => void,
              private schedule: (callback: () => void) => ReturnType<typeof setTimeout> = callback => setTimeout(callback, 5000),
              private cancel: (timer: ReturnType<typeof setTimeout>) => void = clearTimeout) {}
  start() {
    if (this.started || this.stopped) return;
    this.started = true;
    void this.poll();
  }
  private async poll() {
    if (this.stopped) return;
    try {
      const sample = await this.read();
      if (this.stopped) return;
      this.changed(sample);
      if (this.stopped) return;
      this.timer = this.schedule(() => { this.timer = null; void this.poll(); });
    } catch { if (!this.stopped) this.failed(); }
  }
  stop() {
    this.stopped = true;
    if (this.timer !== null) this.cancel(this.timer);
    this.timer = null;
  }
}
