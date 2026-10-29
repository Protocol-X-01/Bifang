import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/api/localTerminal.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext } }).outputText;
const { LocalTerminal, parseTerminalFrame } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const opened = { id: 7, directory: '/fixture/project', program: '/bin/bash' };
const defer = () => { let resolve; const promise = new Promise(callback => { resolve = callback; }); return { promise, resolve }; };
const tick = () => new Promise(resolve => setImmediate(resolve));

test('no terminal starts during construction or without explicit consent', async () => {
  const calls = [];
  const link = new LocalTerminal(async command => { calls.push(command); }, async () => {}, () => {}, () => {});
  assert.deepEqual(calls, []);
  await assert.rejects(link.start('/fixture', 24, 80, false));
  assert.deepEqual(calls, []);
});

test('closing during native startup closes only that late session without polling', async () => {
  const start = defer(), calls = [];
  const link = new LocalTerminal(async (command, args) => {
    calls.push([command, args]);
    if (command === 'terminal_open') return start.promise;
  }, async () => {}, () => {}, () => {});
  const opening = link.start('/fixture', 24, 80, true);
  await link.close(); start.resolve(opened);
  assert.equal(await opening, null);
  assert.deepEqual(calls.map(([command]) => command), ['terminal_open', 'terminal_close']);
  assert.deepEqual(calls[1][1], { id: 7 });
});

test('input is UTF-8 exact, serialized and split into bounded native calls', async () => {
  const bytes = [], pendingRead = defer();
  let concurrent = 0, peak = 0;
  const link = new LocalTerminal(async (command, args) => {
    if (command === 'terminal_open') return opened;
    if (command === 'terminal_read') return pendingRead.promise;
    if (command === 'terminal_write') {
      concurrent += 1; peak = Math.max(peak, concurrent);
      assert.ok(args.data.length <= 16384); assert.equal(args.id, 7);
      await tick(); bytes.push(...args.data); concurrent -= 1;
    }
  }, async () => {}, () => {}, error => assert.fail(error));
  await link.start('/fixture', 24, 80, true);
  const first = 'π'.repeat(12000), second = '\x03second\r';
  await Promise.all([link.send(first), link.send(second)]);
  assert.equal(new TextDecoder().decode(Uint8Array.from(bytes)), first + second);
  assert.equal(peak, 1);
  await assert.rejects(link.send('x'.repeat(1_048_577)));
  await link.close();
});

test('output rendering provides backpressure before another native frame is requested', async () => {
  const render = defer(), pendingRead = defer(); let reads = 0;
  const link = new LocalTerminal(async command => {
    if (command === 'terminal_open') return opened;
    if (command === 'terminal_read') {
      reads += 1;
      return reads === 1 ? { data: [27, 91, 51, 49, 109], exited: false, exit_code: null } : pendingRead.promise;
    }
  }, async bytes => { assert.deepEqual([...bytes], [27, 91, 51, 49, 109]); await render.promise; }, () => {}, error => assert.fail(error));
  await link.start('/fixture', 24, 80, true); await tick();
  assert.equal(reads, 1);
  await link.close(); render.resolve(); await tick();
  assert.equal(reads, 1);
});

test('final bytes render before cleanup and exact exit status', async () => {
  const events = [], ended = defer();
  const link = new LocalTerminal(async command => {
    if (command === 'terminal_open') return opened;
    if (command === 'terminal_read') return { data: [195, 169], exited: true, exit_code: 7 };
    if (command === 'terminal_close') events.push('closed');
  }, async bytes => events.push([...bytes]), code => { events.push(code); ended.resolve(); }, error => assert.fail(error));
  await link.start('/fixture', 24, 80, true); await ended.promise;
  assert.deepEqual(events, [[195, 169], 'closed', 7]);
});

test('concurrent close operations share one native shutdown', async () => {
  const closing = defer(), pendingRead = defer(); let closes = 0;
  const link = new LocalTerminal(async command => {
    if (command === 'terminal_open') return opened;
    if (command === 'terminal_read') return pendingRead.promise;
    if (command === 'terminal_close') { closes += 1; return closing.promise; }
  }, async () => {}, () => {}, () => {});
  await link.start('/fixture', 24, 80, true);
  const first = link.close(), second = link.close();
  assert.equal(closes, 1); closing.resolve(); await Promise.all([first, second]);
});

test('terminal frame validation rejects oversized or malformed data', () => {
  for (const value of [null, {}, { data: [-1], exited: false, exit_code: null },
    { data: [256], exited: false, exit_code: null }, { data: [1.5], exited: false, exit_code: null },
    { data: Array(16385).fill(0), exited: false, exit_code: null },
    { data: [], exited: 'yes', exit_code: 0 }, { data: [], exited: true, exit_code: -1 }]) {
    assert.throws(() => parseTerminalFrame(value));
  }
});
