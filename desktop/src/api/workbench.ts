export interface PluginInfo {
  id: string; sha256: string; name: string; version: string; description: string;
  capabilities: string[]; source_path: string; manifest_path: string; execution: string;
}
export interface PluginEntry extends PluginInfo { trusted: boolean; state: 'enabled' | 'changed' | 'disabled' }
export interface PluginReview extends PluginInfo { source: string }
export interface PluginListing { plugins: PluginEntry[]; errors: { path: string; error: string }[]; execution: string }
export interface Toolchain {
  id: string; label: string; manager: string; available: boolean; manifests: string[];
  bootstrap_argv: string[]; may_execute_dependency_code: boolean; manager_selection_required?: boolean;
}
export type WorkbenchInvoke = <Result>(command: string, args: Record<string, unknown>) => Promise<Result>;

const record = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid workbench result');
  return value as Record<string, unknown>;
};
const text = (value: unknown, max = 8192): string => {
  if (typeof value !== 'string' || value.length > max) throw new Error('Invalid workbench text');
  return value;
};
const strings = (value: unknown, max = 32): string[] => {
  if (!Array.isArray(value) || value.length > max) throw new Error('Invalid workbench list');
  return value.map(item => text(item));
};
const flag = (value: unknown): boolean => {
  if (typeof value !== 'boolean') throw new Error('Invalid workbench flag');
  return value;
};
function plugin(value: unknown): PluginInfo {
  const item = record(value);
  const id = text(item.id), sha256 = text(item.sha256);
  if (!/^[a-f0-9]{24}$/.test(id) || !/^[a-f0-9]{64}$/.test(sha256)) throw new Error('Invalid plugin fingerprint');
  return { id, sha256, name: text(item.name, 40), version: text(item.version, 80), description: text(item.description, 1000),
    capabilities: strings(item.capabilities, 4), source_path: text(item.source_path), manifest_path: text(item.manifest_path), execution: text(item.execution) };
}
export function parsePlugins(value: unknown): PluginListing {
  const result = record(value);
  if (!Array.isArray(result.plugins) || result.plugins.length > 256 || !Array.isArray(result.errors) || result.errors.length > 256) throw new Error('Invalid plugin catalog');
  return { execution: text(result.execution), plugins: result.plugins.map(value => {
    const item = record(value), info = plugin(item);
    if (!['enabled', 'changed', 'disabled'].includes(String(item.state))) throw new Error('Invalid plugin state');
    const state = item.state as PluginEntry['state'], trusted = flag(item.trusted);
    if (trusted !== (state === 'enabled')) throw new Error('Inconsistent plugin trust state');
    return { ...info, state, trusted };
  }), errors: result.errors.map(value => { const error = record(value); return { path: text(error.path), error: text(error.error) }; }) };
}
export function parseToolchains(value: unknown): Toolchain[] {
  const result = record(value);
  if (!Array.isArray(result.profiles) || result.profiles.length > 16 || result.automatic_install !== false) throw new Error('Invalid toolchain preview');
  return result.profiles.map(value => {
    const item = record(value);
    return { id: text(item.id), label: text(item.label), manager: text(item.manager), available: flag(item.available),
      manifests: strings(item.manifests), bootstrap_argv: strings(item.bootstrap_argv), may_execute_dependency_code: flag(item.may_execute_dependency_code),
      manager_selection_required: item.manager_selection_required === undefined ? undefined : flag(item.manager_selection_required) };
  });
}
export class WorkbenchClient {
  private queue: Promise<unknown> = Promise.resolve();
  constructor(private invoke: WorkbenchInvoke) {}
  private call(workspace: string, action: string, extra: Record<string, unknown> = {}) {
    if (!workspace) return Promise.reject(new Error('Choose a local workspace first'));
    const pending = this.queue.catch(() => undefined).then(() => this.invoke<unknown>('workbench_request', { request: { version: 1, workspace, action, ...extra } }));
    this.queue = pending;
    return pending;
  }
  async list(workspace: string) { return parsePlugins(await this.call(workspace, 'plugins.list')); }
  async toolchains(workspace: string) { return parseToolchains(await this.call(workspace, 'toolchains.inspect')); }
  async metrics(workspace: string) { return parseSystemMetrics(await this.call(workspace, 'metrics.sample')); }
  async setupPlan(workspace: string, network: boolean, profile = 'javascript-npm', builds = false) {
    return profile === 'javascript-npm' ? this.call(workspace, 'setup.plan', { network })
      : this.call(workspace, 'setup.profile_plan', { network, profile, allow_builds: builds });
  }
  async review(workspace: string, id: string): Promise<PluginReview> {
    const result = record(await this.call(workspace, 'plugins.review', { id }));
    const info = plugin(result);
    if (info.id !== id) throw new Error('Plugin selection changed; refresh and review again');
    return { ...info, source: text(result.source, 256000) };
  }
  async trust(workspace: string, reviewed: PluginReview, confirmed: boolean) {
    if (!confirmed) throw new Error('Confirm full host-code trust before enabling');
    const result = record(await this.call(workspace, 'plugins.trust', { id: reviewed.id, sha256: reviewed.sha256, confirmed: true }));
    if (result.id !== reviewed.id || result.sha256 !== reviewed.sha256 || result.enabled !== true) throw new Error('Plugin enablement could not be verified; refresh');
  }
  async disable(workspace: string, id: string) {
    const result = record(await this.call(workspace, 'plugins.disable', { id }));
    if (result.id !== id || result.enabled !== false) throw new Error('Plugin disablement could not be verified; refresh');
  }
}
import { parseSystemMetrics } from './systemMetrics';

