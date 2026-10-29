import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/components/DevicePairing.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const settle = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };

function harness(invoke) {
  const slots = [];
  const cleanups = [];
  const timers = new Map();
  let cursor = 0;
  let sequence = 0;
  let connected = 0;
  let busy = false;
  const hooks = {
    useState(initial) {
      const position = cursor++;
      if (!(position in slots)) slots[position] = initial;
      return [slots[position], value => { slots[position] = typeof value === 'function' ? value(slots[position]) : value; }];
    },
    useRef(initial) {
      const position = cursor++;
      if (!(position in slots)) slots[position] = { current: initial };
      return slots[position];
    },
    useEffect(effect) {
      const position = cursor++;
      if (!(position in slots)) { slots[position] = true; cleanups.push(effect()); }
    },
  };
  const exports = {};
  const modules = { react: hooks, '@tauri-apps/api/core': { invoke }, 'react/jsx-runtime': { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }), Fragment: 'fragment' }, 'lucide-react': { Phone: () => null } };
  new Function('require', 'exports', 'setTimeout', 'clearTimeout', compiled)(name => modules[name], exports,
    (callback, delay) => { const identity = ++sequence; timers.set(identity, { callback, delay }); return identity; }, identity => timers.delete(identity));
  function render() {
    cursor = 0;
    return exports.DevicePairing({ endpoint: 'https://fixture.test', disabled: false, onBusy: value => { busy = value; }, onConnected: async () => { connected++; } });
  }
  function button(label) {
    const visit = node => {
      if (!node || typeof node !== 'object') return null;
      const textContent = Array.isArray(node.props?.children) 
        ? node.props.children.filter(c => typeof c === 'string').join('')
        : typeof node.props?.children === 'string' ? node.props.children : '';
      if (node.type === 'button' && textContent.includes(label)) return node;
      for (const child of [node.props?.children].flat(Infinity)) { const found = visit(child); if (found) return found; }
      return null;
    };
    const found = visit(render());
    assert.ok(found, `missing button ${label}`);
    return found;
  }
  return { button, render, slots, tick: (expectedDelay = 5000) => { const [identity, timer] = timers.entries().next().value; assert.equal(timer.delay, expectedDelay); timers.delete(identity); timer.callback(); },
    unmount: () => cleanups.forEach(cleanup => cleanup?.()), get connected() { return connected; }, get busy() { return busy; } };
}

const challenge = { attempt: '1', user_code: 'ABCD-EFGH', expires_in: 300, interval: 5 };

test('phone code polls at native interval and hands off without revoking the connected session', async () => {
  const calls = [];
  const view = harness(async (command, arguments_) => {
    calls.push([command, arguments_]);
    return command === 'remote_pair_begin' ? challenge : { status: 'connected', expires_in: 3600 };
  });
  view.button('Get pairing code').props.onClick();
  await settle();
  assert.equal(view.busy, true);
  assert.match(JSON.stringify(view.render()), /ABCD-EFGH/);
  assert.equal(calls.length, 1);
  view.tick();
  await settle();
  assert.equal(view.connected, 1);
  view.unmount();
  assert.deepEqual(calls.map(entry => entry[0]), ['remote_pair_begin', 'remote_pair_poll']);
  assert.deepEqual(calls[1][1], { attempt: '1' });
  assert.equal(view.busy, false);
});

test('cancelling while begin is in flight cancels its eventual native challenge', async () => {
  const started = deferred();
  const calls = [];
  const view = harness(async command => { calls.push(command); return command === 'remote_pair_begin' ? started.promise : undefined; });
  view.button('Get pairing code').props.onClick();
  view.button('Cancel pairing').props.onClick();
  started.resolve(challenge);
  await settle();
  assert.deepEqual(calls, ['remote_pair_begin', 'remote_pair_cancel']);
  assert.equal(view.connected, 0);
  assert.equal(view.busy, false);
});

test('cancellation racing with token issuance never hands off an unwanted connection', async () => {
  const issued = deferred();
  const calls = [];
  const view = harness(async command => { calls.push(command); return command === 'remote_pair_begin' ? challenge : command === 'remote_pair_poll' ? issued.promise : undefined; });
  view.button('Get pairing code').props.onClick();
  await settle();
  view.tick();
  await settle();
  view.button('Cancel pairing').props.onClick();
  issued.resolve({ status: 'connected' });
  await settle();
  assert.equal(view.connected, 0);
  assert.equal(calls.filter(command => command === 'remote_pair_cancel').length, 2);
});

test('unmount while pairing is starting cancels the late result', async () => {
  const started = deferred();
  const calls = [];
  const view = harness(async command => { calls.push(command); return command === 'remote_pair_begin' ? started.promise : undefined; });
  view.button('Get pairing code').props.onClick();
  view.unmount();
  started.resolve(challenge);
  await settle();
  assert.deepEqual(calls, ['remote_pair_begin', 'remote_pair_cancel']);
  assert.equal(view.connected, 0);
});

test('denied pairing clears pending native state and permits retry', async () => {
  const calls = [];
  const view = harness(async command => {
    calls.push(command);
    if (command === 'remote_pair_begin') return challenge;
    if (command === 'remote_pair_poll') throw new Error('Pairing declined');
  });
  view.button('Get pairing code').props.onClick();
  await settle();
  view.tick();
  await settle();
  assert.match(JSON.stringify(view.render()), /Pairing declined/);
  assert.ok(view.button('Get pairing code'));
  assert.equal(view.connected, 0);
  assert.equal(calls.at(-1), 'remote_pair_cancel');
});

test('phone respects a native slow-down result before polling again', async () => {
  let polls = 0;
  const view = harness(async command => {
    if (command === 'remote_pair_begin') return challenge;
    if (command === 'remote_pair_poll') return ++polls === 1 ? { status: 'pending', retry_after: 15 } : { status: 'connected' };
  });
  view.button('Get pairing code').props.onClick();
  await settle();
  view.tick();
  await settle();
  assert.equal(polls, 1);
  assert.equal(view.connected, 0);
  view.tick(15000);
  await settle();
  assert.equal(view.connected, 1);
});
