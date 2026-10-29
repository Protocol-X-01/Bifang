import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/api/setup.ts', import.meta.url), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const { SetupClient, parseSetupPlan, parseSetupReceipt } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const hash = 'a'.repeat(64);
const plan = { version: 'npm-locked-v1', profile: 'javascript-npm', sha256: hash, workspace: '/fixture',
  argv: ['/usr/bin/npm', 'ci', '--ignore-scripts'], inputs: { 'package.json': hash, 'package-lock.json': hash,
    'npm-shrinkwrap.json': null, '.npmrc': null, 'pnpm-lock.yaml': null, 'yarn.lock': null, 'bun.lock': null, 'bun.lockb': null },
  executable: '/usr/share/nodejs/npm/bin/npm-cli.js', executable_sha256: hash, network: 'offline-v1',
  registry: 'https://registry.npmjs.org', cache_path: '/fixture-state/cache', scripts: 'disabled',
  timeout_seconds: 300, output_limit_bytes: 1_000_000, writes: ['project', 'private cache'], isolation: 'Bubblewrap', warning: 'Review network access' };
const receipt = { plan_sha256: hash, plan, workspace: '/fixture', argv: plan.argv, network: 'offline-v1', scripts: 'disabled',
  status: 'succeeded', returncode: 0, started_at: '2026-10-25T21:00:00+00:00', elapsed_seconds: .5,
  output_bytes: 5, output_sha256: hash, inputs_unchanged: true, rollback: 'not performed', receipt_saved: true, receipt_path: '/fixture-state/receipt.json' };

test('setup review is read-only and binds the exact selected path and network option', async () => {
  const calls = [];
  const client = new SetupClient(async (command, args) => { calls.push([command, args]); return plan; }, () => ({}));
  assert.equal((await client.review('/fixture', false)).sha256, hash);
  assert.deepEqual(calls[0], ['workbench_request', { request: { version: 1, workspace: '/fixture', action: 'setup.plan', network: false } }]);
  await assert.rejects(client.review('/other-project', false));
  await assert.rejects(client.review('/fixture', true));
  await assert.rejects(client.review('', false));
});

test('unconfirmed setup does not create a native job or channel', () => {
  const client = new SetupClient(() => assert.fail('must not invoke'), () => assert.fail('must not create channel'));
  assert.throws(() => client.start(plan, false, () => {}));
  assert.throws(() => client.start(plan, 'yes', () => {}));
});

test('setup streams literal output and cancellation targets only the matching native job', async () => {
  const channel = {}, calls = [], output = [];
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const client = new SetupClient(async (command, args) => {
    calls.push([command, args]);
    if (command === 'setup_cancel') return true;
    channel.onmessage({ event: 'started' });
    channel.onmessage({ event: 'output', stream: 'stdout', text: '<literal>output</literal>' });
    return pending;
  }, () => channel);
  const job = client.start(plan, true, (_stream, text) => output.push(text));
  assert.equal(await job.cancel(), true);
  assert.deepEqual(calls[1], ['setup_cancel', { id: job.id }]);
  assert.deepEqual(calls[0][1].request, { version: 1, workspace: '/fixture', sha256: hash, network: false,
    registry: plan.registry, confirmed: true });
  finish({ ...receipt, status: 'cancelled', returncode: -9 });
  assert.equal((await job.result).status, 'cancelled');
  assert.deepEqual(output, ['<literal>output</literal>']);
  channel.onmessage({ event: 'output', stream: 'stdout', text: 'late output' });
  assert.equal(output.length, 1);
  assert.equal(await job.cancel(), false);
});

test('malformed progress cancels and cannot turn into a verified success', async () => {
  const channel = {}, calls = [];
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const client = new SetupClient(async (command, args) => {
    calls.push(command);
    if (command === 'setup_cancel') return true;
    channel.onmessage({ event: 'started' });
    return pending;
  }, () => channel);
  const job = client.start(plan, true, () => {});
  const rejected = assert.rejects(job.result, /could not be verified/);
  channel.onmessage({ event: 'output', stream: 'stdout', text: { unsafe: true } });
  await new Promise(resolve => setImmediate(resolve));
  assert.ok(calls.includes('setup_cancel'));
  finish(receipt);
  await rejected;
});

test('plan and exit receipts reject unknown versions, stale fingerprints and false success', () => {
  assert.equal(parseSetupReceipt(receipt, parseSetupPlan(plan)).status, 'succeeded');
  for (const value of [null, {}, { ...plan, scripts: 'enabled' }, { ...plan, version: 'unknown' },
    { ...plan, sha256: 'stale' }, { ...plan, inputs: { ...plan.inputs, 'package.json': null } },
    { ...plan, timeout_seconds: Infinity }, { ...plan, argv: ['sh', '-c', 'anything'] }]) assert.throws(() => parseSetupPlan(value));
  for (const value of [{ ...receipt, plan_sha256: 'b'.repeat(64) }, { ...receipt, returncode: 1 },
    { ...receipt, inputs_unchanged: false }, { ...receipt, receipt_saved: true, receipt_path: null },
    { ...receipt, status: 'invented' }, { ...receipt, plan: { ...plan, network: 'host-network' } },
    { ...receipt, argv: ['sh', '-c', 'changed'] }]) assert.throws(() => parseSetupReceipt(value, plan));
});

test('desktop setup requires explicit confirmation, renders plain text and cancels on teardown', async () => {
  const panel = await readFile(new URL('../src/components/PackageSetupPanel.tsx', import.meta.url), 'utf8');
  const native = await readFile(new URL('../src-tauri/src/setup.rs', import.meta.url), 'utf8');
  assert.match(panel, /Install approved plan/);
  assert.match(panel, /I approve this exact plan/);
  assert.match(panel, /disabled=\{!confirmed \|\| Boolean\(plan.allow_builds && !buildConfirmed\) \|\| running \|\| agentBusy \|\| disabled\}/);
  assert.match(panel, /I separately authorize the build code/);
  assert.match(panel, /active.current\?\.cancel\(\)/);
  assert.match(panel, /slice\(-100_000\)/);
  assert.doesNotMatch(panel, /dangerouslySetInnerHTML|terminal_write|fetch\(/);
  assert.equal((native.match(/crate::terminal::local_window\(&window\)\?/g) || []).length, 2);
});

for (const profile of ['python-uv', 'rust-cargo']) {
  test(`${profile} uses a versioned profile request and does not infer build consent`, async () => {
    const inputs = Object.fromEntries((profile === 'python-uv' ? ['pyproject.toml', 'uv.lock', 'uv.toml', '.python-version', 'poetry.lock', 'pdm.lock']
      : ['Cargo.toml', 'Cargo.lock', '.cargo/config', '.cargo/config.toml', 'rust-toolchain', 'rust-toolchain.toml', 'build.rs']).map((key, index) => [key, index < 2 ? hash : null]));
    const extended = { ...plan, version: 'project-setup-v2', profile, inputs, allow_builds: false,
      argv: profile === 'python-uv' ? ['/bifang-tools/uv', 'sync', '--locked', '--no-install-project', '--no-build'] : ['/runtime/bin/cargo', 'fetch', '--locked'],
      runtime_mounts: ['/runtime/lib'], runtime_tools: { '/runtime/bin/tool': hash }, sandbox_env: { HOME: '/tmp' }, execution: 'No build code',
      ...(profile === 'python-uv' ? { environment_path: '/fixture/.bifang/environments/python-0000', environment_generation: 0, python_version: '3.11.15' } : { runtime_aliases: {} }) };
    const calls = [], channel = {};
    const client = new SetupClient(async (command, args) => {
      calls.push([command, args]);
      if (command === 'workbench_request') return extended;
      channel.onmessage({ event: 'started' });
      return { ...receipt, plan: extended, argv: extended.argv };
    }, () => channel);
    const reviewed = await client.review('/fixture', false, profile, false);
    assert.deepEqual(calls[0][1].request, { version: 1, workspace: '/fixture', action: 'setup.profile_plan', network: false, profile, allow_builds: false });
    const job = client.start(reviewed, true, () => {});
    assert.equal((await job.result).plan.profile, profile);
    assert.equal(calls[1][1].request.version, 2);
    assert.equal(calls[1][1].request.profile, profile);
    assert.equal(calls[1][1].request.allow_builds, false);
    assert.throws(() => parseSetupPlan({ ...extended, scripts: 'build-code-enabled' }));
    assert.throws(() => parseSetupReceipt({ ...receipt, plan: { ...extended, allow_builds: true, scripts: 'build-code-enabled' }, scripts: 'build-code-enabled' }, reviewed));
  });
}

test('build-enabled plans require a separate client-side confirmation before native invocation', async () => {
  const inputs = Object.fromEntries(['Cargo.toml', 'Cargo.lock', '.cargo/config', '.cargo/config.toml', 'rust-toolchain', 'rust-toolchain.toml', 'build.rs'].map((name, index) => [name, index < 2 ? hash : null]));
  const build = { ...plan, version: 'project-setup-v2', profile: 'rust-cargo', inputs, allow_builds: true, scripts: 'build-code-enabled',
    argv: ['/runtime/bin/cargo', 'check', '--locked'], runtime_mounts: ['/runtime/lib'], runtime_tools: { '/runtime/bin/rustc': hash },
    sandbox_env: { CARGO_HOME: '/tmp/cargo-home' }, runtime_aliases: {}, execution: 'Build code may execute' };
  const channel = {}, calls = [];
  const client = new SetupClient(async (command, args) => {
    calls.push([command, args]); channel.onmessage({ event: 'started' });
    return { ...receipt, plan: build, argv: build.argv, scripts: 'build-code-enabled' };
  }, () => channel);
  assert.throws(() => client.start(build, true, () => {}), /Separately confirm/);
  assert.equal(calls.length, 0);
  const job = client.start(build, true, () => {}, true);
  assert.equal((await job.result).scripts, 'build-code-enabled');
  assert.equal(calls[0][1].request.allow_builds, true);
});
