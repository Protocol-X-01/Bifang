export type SetupProfile = 'javascript-npm' | 'python-uv' | 'rust-cargo';
export interface SetupPlan {
  version: 'npm-locked-v1' | 'project-setup-v2'; profile: SetupProfile; sha256: string; workspace: string;
  argv: string[]; inputs: Record<string, string | null>; executable: string; executable_sha256: string;
  network: 'offline-v1' | 'host-network'; registry: string; cache_path: string; scripts: 'disabled' | 'build-code-enabled';
  timeout_seconds: number; output_limit_bytes: number; writes: string[]; isolation: string; warning: string;
  allow_builds?: boolean; runtime_mounts?: string[]; runtime_tools?: Record<string, string>; runtime_aliases?: Record<string, string>;
  sandbox_env?: Record<string, string>; execution?: string; environment_path?: string; environment_generation?: number; python_version?: string;
}
export interface SetupReceipt {
  plan_sha256: string; plan: SetupPlan; workspace: string; argv: string[]; network: SetupPlan['network']; scripts: SetupPlan['scripts'];
  status: string; returncode: number | null; started_at: string; elapsed_seconds: number;
  output_bytes: number; output_sha256: string; inputs_unchanged: boolean; rollback: string;
  receipt_saved: boolean; receipt_path: string | null;
}
export interface SetupChannel { onmessage: (event: unknown) => void }
export type SetupInvoke = <Result>(command: string, args: Record<string, unknown>) => Promise<Result>;

const object = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid setup response');
  return value as Record<string, unknown>;
};
const text = (value: unknown, limit = 8192): string => {
  if (typeof value !== 'string' || value.length > limit || value.includes('\0')) throw new Error('Invalid setup text');
  return value;
};
const hash = (value: unknown): string => {
  const result = text(value, 64);
  if (!/^[a-f0-9]{64}$/.test(result)) throw new Error('Invalid setup fingerprint');
  return result;
};
const number = (value: unknown, max: number): number => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > max) throw new Error('Invalid setup measurement');
  return value;
};
const flag = (value: unknown): boolean => {
  if (typeof value !== 'boolean') throw new Error('Invalid setup flag');
  return value;
};
const strings = (value: unknown): string[] => {
  if (!Array.isArray(value) || value.length > 64) throw new Error('Invalid setup arguments');
  return value.map(item => text(item));
};

export function parseSetupPlan(value: unknown): SetupPlan {
  const plan = object(value);
  const schemas: Record<string, string[]> = {
    'javascript-npm': ['package.json', 'package-lock.json', 'npm-shrinkwrap.json', '.npmrc', 'pnpm-lock.yaml', 'yarn.lock', 'bun.lock', 'bun.lockb'],
    'python-uv': ['pyproject.toml', 'uv.lock', 'uv.toml', '.python-version', 'poetry.lock', 'pdm.lock'],
    'rust-cargo': ['Cargo.toml', 'Cargo.lock', '.cargo/config', '.cargo/config.toml', 'rust-toolchain', 'rust-toolchain.toml', 'build.rs'],
  };
  const profile = text(plan.profile), fields = schemas[profile];
  if (JSON.stringify(plan).length > 32768 || !fields || plan.version !== (profile === 'javascript-npm' ? 'npm-locked-v1' : 'project-setup-v2')
    || !['disabled', 'build-code-enabled'].includes(String(plan.scripts)) || !['offline-v1', 'host-network'].includes(String(plan.network))) throw new Error('Unsupported setup plan');
  const builds = profile === 'javascript-npm' ? false : flag(plan.allow_builds);
  if ((plan.scripts === 'build-code-enabled') !== builds) throw new Error('Inconsistent build-code permission');
  const inputs = object(plan.inputs);
  if (Object.keys(inputs).length !== fields.length) throw new Error('Invalid setup input snapshot');
  for (const name of fields) {
    if (!(name in inputs)) throw new Error('Missing setup input');
    if (inputs[name] !== null) hash(inputs[name]);
  }
  if (fields.slice(0, 2).some(name => inputs[name] === null)) throw new Error('Missing locked project inputs');
  const argv = strings(plan.argv);
  if (profile === 'javascript-npm' && (argv[0] !== '/usr/bin/npm' || argv[1] !== 'ci' || !argv.includes('--ignore-scripts'))) throw new Error('Invalid installer command');
  if (profile === 'python-uv' && (argv[0] !== '/bifang-tools/uv' || argv[1] !== 'sync' || !argv.includes('--locked') || !argv.includes('--no-install-project') || (!builds && !argv.includes('--no-build')))) throw new Error('Invalid Python setup command');
  if (profile === 'rust-cargo' && (argv[1] !== (builds ? 'check' : 'fetch') || !argv.includes('--locked'))) throw new Error('Invalid Rust setup command');
  const result: SetupPlan = { version: plan.version as SetupPlan['version'], profile: profile as SetupProfile, sha256: hash(plan.sha256), workspace: text(plan.workspace),
    argv, inputs: inputs as Record<string, string | null>, executable: text(plan.executable), executable_sha256: hash(plan.executable_sha256),
    network: plan.network as SetupPlan['network'], registry: text(plan.registry, 2048), cache_path: text(plan.cache_path), scripts: plan.scripts as SetupPlan['scripts'],
    timeout_seconds: number(plan.timeout_seconds, 300), output_limit_bytes: number(plan.output_limit_bytes, 1_000_000),
    writes: strings(plan.writes), isolation: text(plan.isolation), warning: text(plan.warning) };
  if (profile !== 'javascript-npm') {
    const mapping = (value: unknown, validate: (entry: unknown) => string) => {
      const entries = Object.entries(object(value));
      if (entries.length > 64) throw new Error('Invalid runtime metadata');
      return Object.fromEntries(entries.map(([key, entry]) => [text(key), validate(entry)]));
    };
    result.allow_builds = builds;
    result.runtime_mounts = strings(plan.runtime_mounts);
    result.runtime_tools = mapping(plan.runtime_tools, hash);
    result.sandbox_env = mapping(plan.sandbox_env, text);
    result.execution = text(plan.execution);
    if (profile === 'python-uv') {
      result.environment_path = text(plan.environment_path);
      result.environment_generation = number(plan.environment_generation, 255);
      result.python_version = text(plan.python_version, 80);
    } else result.runtime_aliases = mapping(plan.runtime_aliases, text);
  }
  return result;
}

export function parseSetupReceipt(value: unknown, reviewed: SetupPlan): SetupReceipt {
  const item = object(value), plan = parseSetupPlan(item.plan);
  const status = text(item.status);
  if (!['succeeded', 'failed', 'cancelled', 'timed_out', 'output_limit', 'inputs_changed', 'output_error', 'start_failed'].includes(status)
    || hash(item.plan_sha256) !== reviewed.sha256 || plan.sha256 !== reviewed.sha256 || plan.workspace !== reviewed.workspace
    || item.workspace !== reviewed.workspace || item.network !== reviewed.network || item.scripts !== reviewed.scripts) throw new Error('Setup receipt does not match the reviewed plan');
  const canonical = (value: unknown): unknown => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object'
    ? Object.fromEntries(Object.entries(value).sort(([first], [second]) => first.localeCompare(second)).map(([key, entry]) => [key, canonical(entry)])) : value;
  const signature = (value: SetupPlan) => JSON.stringify(canonical(value));
  if (signature(plan) !== signature(parseSetupPlan(reviewed)) || JSON.stringify(item.argv) !== JSON.stringify(reviewed.argv)) throw new Error('Setup receipt changed the reviewed parameters');
  if (item.returncode !== null && (typeof item.returncode !== 'number' || !Number.isInteger(item.returncode))) throw new Error('Invalid setup exit code');
  if (status === 'succeeded' && (item.returncode !== 0 || item.inputs_unchanged !== true)) throw new Error('Unverified setup success');
  const saved = flag(item.receipt_saved);
  if ((saved && typeof item.receipt_path !== 'string') || (!saved && item.receipt_path !== null)) throw new Error('Invalid receipt persistence result');
  return { plan_sha256: reviewed.sha256, plan, workspace: reviewed.workspace, argv: strings(item.argv), network: reviewed.network,
    scripts: reviewed.scripts, status, returncode: item.returncode as number | null, started_at: text(item.started_at, 80),
    elapsed_seconds: number(item.elapsed_seconds, 3600), output_bytes: number(item.output_bytes, 1_100_000),
    output_sha256: hash(item.output_sha256), inputs_unchanged: flag(item.inputs_unchanged), rollback: text(item.rollback),
    receipt_saved: saved, receipt_path: saved ? text(item.receipt_path) : null };
}

export class SetupClient {
  constructor(private invoke: SetupInvoke, private channel: () => SetupChannel,
    private reviewer?: (workspace: string, network: boolean, profile: SetupProfile, builds: boolean) => Promise<unknown>) {}

  async review(workspace: string, network: boolean, profile: SetupProfile = 'javascript-npm', builds = false) {
    if (!workspace) throw new Error('Choose a local project first');
    const value = this.reviewer ? await this.reviewer(workspace, network, profile, builds) : await this.invoke('workbench_request', {
      request: { version: 1, workspace, action: profile === 'javascript-npm' ? 'setup.plan' : 'setup.profile_plan', network,
        ...(profile === 'javascript-npm' ? {} : { profile, allow_builds: builds }) } });
    const plan = parseSetupPlan(value);
    if (plan.workspace !== workspace || plan.profile !== profile || Boolean(plan.allow_builds) !== builds || (plan.network === 'host-network') !== network) throw new Error('Setup selection changed; review again');
    return plan;
  }

  start(value: SetupPlan, confirmed: boolean, output: (stream: string, value: string) => void, buildConfirmed = false) {
    if (confirmed !== true) throw new Error('Confirm this exact setup plan first');
    const plan = parseSetupPlan(value);
    if (plan.allow_builds && buildConfirmed !== true) throw new Error('Separately confirm build-code execution');
    const id = crypto.randomUUID().replace(/-/g, '');
    const channel = this.channel();
    let ready!: () => void;
    const started = new Promise<void>(resolve => { ready = resolve; });
    let done = false, streamError = false, size = 0;
    const cancel = async () => { await started; return done ? false : this.invoke<boolean>('setup_cancel', { id }); };
    channel.onmessage = value => {
      if (done) return;
      try {
        const event = object(value);
        if (event.event === 'started' && Object.keys(event).length === 1) { ready(); return; }
        if (event.event !== 'output' || Object.keys(event).length !== 3 || !['stdout', 'stderr'].includes(String(event.stream))) throw new Error('Invalid setup event');
        const content = text(event.text, 32768);
        size += content.length;
        if (size > 8_000_000) throw new Error('Setup output exceeded its limit');
        output(event.stream as string, content);
      } catch { streamError = true; ready(); void cancel().catch(() => undefined); }
    };
    const result = this.invoke<unknown>('setup_run', { id, onEvent: channel, request: { version: plan.profile === 'javascript-npm' ? 1 : 2, workspace: plan.workspace,
      sha256: plan.sha256, network: plan.network === 'host-network', registry: plan.registry, confirmed: true,
      ...(plan.profile === 'javascript-npm' ? {} : { profile: plan.profile, allow_builds: plan.allow_builds }) } }).then(value => {
      if (streamError) throw new Error('Setup output could not be verified; inspect saved receipts');
      return parseSetupReceipt(value, plan);
    }).finally(() => { done = true; ready(); });
    return { id, result, cancel };
  }
}
