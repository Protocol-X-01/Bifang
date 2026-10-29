import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/api/systemMetrics.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext } }).outputText;
const { parseSystemMetrics, formatBytes, MetricsPoller } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const absent = { available: false, reason: 'Not configured' };
const fixture = { schema: 1, sampled_at: '2026-10-25T16:00:00+00:00', collection_ms: 102, scope: 'Local only',
  cpu: { available: true, percent: 12.5, sample_ms: 100 },
  memory: { available: true, total_bytes: 1000, used_bytes: 400, available_bytes: 600, percent: 40 },
  disk: { available: true, total_bytes: 1000, used_bytes: 500, free_bytes: 400, percent: 55.5 }, gpu: absent };
const tick = () => new Promise(resolve => setImmediate(resolve));

test('valid local readings and explicit unavailability stay distinct from zero', () => {
  assert.equal(parseSystemMetrics(fixture).memory.used_bytes, 400);
  assert.deepEqual(parseSystemMetrics({ ...fixture, cpu: absent }).cpu, absent);
  assert.equal(formatBytes(0), '0 B');
  assert.equal(formatBytes(1024 ** 3), '1.0 GiB');
  assert.equal(formatBytes(-1), 'Unavailable');
});

test('malformed readings, fabricated GPU values and invalid percentages are rejected', () => {
  for (const change of [{ schema: 2 }, { sampled_at: 'never' }, { cpu: { ...fixture.cpu, percent: NaN } },
    { cpu: { ...fixture.cpu, percent: 101 } }, { cpu: { ...fixture.cpu, available: 'yes' } },
    { memory: { ...fixture.memory, used_bytes: 999 } }, { disk: { ...fixture.disk, free_bytes: 1001 } },
    { gpu: { available: true, percent: 10 } }, { collection_ms: Infinity }]) assert.throws(() => parseSystemMetrics({ ...fixture, ...change }));
});

test('polling waits for each reading and schedules only one next sample', async () => {
  let release, calls = 0; const scheduled = [], samples = [];
  const pending = new Promise(resolve => { release = resolve; });
  const poller = new MetricsPoller(() => { calls += 1; return pending; }, sample => samples.push(sample), () => assert.fail(), callback => { scheduled.push(callback); return 1; }, () => {});
  poller.start(); poller.start();
  assert.equal(calls, 1); assert.equal(scheduled.length, 0);
  release(fixture); await tick();
  assert.equal(samples.length, 1); assert.equal(scheduled.length, 1);
  poller.stop();
});

test('closing during a sample discards late readings and never schedules more work', async () => {
  let release, scheduled = 0;
  const poller = new MetricsPoller(() => new Promise(resolve => { release = resolve; }), () => assert.fail(), () => assert.fail(), () => { scheduled += 1; return 1; }, () => {});
  poller.start(); poller.stop(); release(fixture); await tick();
  assert.equal(scheduled, 0);
});

test('closing cancels the timer; collection errors stop until explicit retry', async () => {
  let cancelled = 0, failed = 0, schedules = 0;
  const healthy = new MetricsPoller(async () => fixture, () => {}, () => assert.fail(), () => 42, identity => { assert.equal(identity, 42); cancelled += 1; });
  healthy.start(); await tick(); healthy.stop();
  assert.equal(cancelled, 1);
  const broken = new MetricsPoller(async () => { throw new Error('private diagnostic'); }, () => assert.fail(), () => { failed += 1; }, () => { schedules += 1; return 1; }, () => {});
  broken.start(); await tick();
  assert.equal(failed, 1); assert.equal(schedules, 0);
});

test('an already dispatched timer callback cannot read after stop', async () => {
  let callback, calls = 0;
  const poller = new MetricsPoller(async () => { calls += 1; return fixture; }, () => {}, () => assert.fail(), next => { callback = next; return 1; }, () => {});
  poller.start(); await tick(); poller.stop(); callback(); await tick();
  assert.equal(calls, 1);
});
