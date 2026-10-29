import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/api/workbench.ts', import.meta.url), 'utf8');
const metricsSource = await readFile(new URL('../src/api/systemMetrics.ts', import.meta.url), 'utf8');
const metricsCompiled = ts.transpileModule(metricsSource, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext } }).outputText;
const metricsUrl = `data:text/javascript;base64,${Buffer.from(metricsCompiled).toString('base64')}`;
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext } }).outputText.replace("'./systemMetrics'", JSON.stringify(metricsUrl));
const { WorkbenchClient, parsePlugins, parseToolchains } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const info = { id: 'a'.repeat(24), sha256: 'b'.repeat(64), name: 'fixture', version: '1', description: 'Fixture',
  capabilities: ['filesystem'], source_path: '/fixture/plugin.py', manifest_path: '/fixture/plugin.plugin.json', execution: 'Full host access' };
const listing = { plugins: [{ ...info, trusted: false, state: 'disabled' }], errors: [], execution: 'Full host access' };

test('plugin reviews and enablement use one fixed native route and bind the reviewed fingerprint', async () => {
  const calls = [];
  const client = new WorkbenchClient(async (command, args) => {
    calls.push([command, args]);
    return args.request.action === 'plugins.review' ? { ...info, source: 'fixture code' } : { ...info, enabled: true };
  });
  const reviewed = await client.review('/fixture', info.id);
  await assert.rejects(client.trust('/fixture', reviewed, false));
  assert.equal(calls.length, 1);
  await client.trust('/fixture', reviewed, true);
  assert.deepEqual(calls[1], ['workbench_request', { request: { version: 1, workspace: '/fixture', action: 'plugins.trust', id: info.id, sha256: info.sha256, confirmed: true } }]);
});

test('wrong selection or mismatched trust receipt fails closed', async () => {
  const wrong = new WorkbenchClient(async () => ({ ...info, id: 'c'.repeat(24), source: 'code', enabled: true }));
  await assert.rejects(wrong.review('/fixture', info.id));
  await assert.rejects(wrong.trust('/fixture', { ...info, source: 'code' }, true));
});

test('concurrent refreshes are serialized and a rejected request does not poison the queue', async () => {
  let release, active = 0, highest = 0, count = 0;
  const first = new Promise(resolve => { release = resolve; });
  const client = new WorkbenchClient(async () => {
    active += 1; highest = Math.max(active, highest); count += 1;
    if (count === 1) { await first; active -= 1; throw new Error('fixture failure'); }
    active -= 1; return listing;
  });
  const opening = assert.rejects(client.list('/fixture'));
  const next = client.list('/fixture');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(count, 1); release();
  await opening; assert.equal((await next).plugins.length, 1);
  assert.equal(highest, 1);
});

test('listing rejects invalid metadata and inconsistent trust states', () => {
  assert.equal(parsePlugins(listing).plugins[0].name, 'fixture');
  for (const value of [null, {}, { ...listing, plugins: [null] },
    { ...listing, plugins: [{ ...listing.plugins[0], trusted: true }] },
    { ...listing, plugins: [{ ...listing.plugins[0], name: {} }] },
    { ...listing, plugins: [{ ...listing.plugins[0], sha256: 'stale' }] },
    { ...listing, errors: [{ path: {}, error: 'bad' }] }]) assert.throws(() => parsePlugins(value));
});

test('language previews reject automatic installation and invalid argv', () => {
  const profile = { id: 'npm', label: 'JavaScript', manager: 'npm', available: true, manifests: ['package.json'], bootstrap_argv: ['npm', 'ci', '--ignore-scripts'], may_execute_dependency_code: false };
  assert.deepEqual(parseToolchains({ automatic_install: false, profiles: [profile] })[0].bootstrap_argv, profile.bootstrap_argv);
  for (const value of [{ automatic_install: true, profiles: [profile] },
    { automatic_install: false, profiles: [{ ...profile, bootstrap_argv: [{}] }] },
    { automatic_install: false, profiles: [{ ...profile, available: 'yes' }] }]) assert.throws(() => parseToolchains(value));
});

test('disable checks its receipt and empty workspaces never invoke native code', async () => {
  let calls = 0;
  const client = new WorkbenchClient(async () => { calls += 1; return { id: info.id, enabled: false }; });
  await assert.rejects(client.list(''));
  assert.equal(calls, 0);
  await client.disable('/fixture', info.id);
  await assert.rejects(new WorkbenchClient(async () => ({ id: info.id, enabled: true })).disable('/fixture', info.id));
});

test('review renderer uses literal source, explicit host trust and no HTML injection or shell launch', async () => {
  const panel = await readFile(new URL('../src/components/WorkbenchPanel.tsx', import.meta.url), 'utf8');
  assert.match(panel, /aria-label="Plugin source code"/);
  assert.match(panel, /trust its code and dependencies with full host access/);
  assert.match(panel, /disabled=\{!confirmed \|\| pending \|\| agentBusy\}/);
  assert.doesNotMatch(panel, /dangerouslySetInnerHTML|terminal_write|fetch\(/);
});
