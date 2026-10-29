import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/components/RemoteWorkspace.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const settle = () => new Promise(resolve => setImmediate(resolve));

function harness(invoke) {
  const slots = [];
  let cursor = 0;
  const exports = {};
  const pairing = () => null;
  const modules = {
    react: {
      useState(initial) {
        const position = cursor++;
        if (!(position in slots)) slots[position] = initial;
        return [slots[position], value => { slots[position] = value; }];
      },
      useRef(initial) {
        const position = cursor++;
        if (!(position in slots)) slots[position] = { current: initial };
        return slots[position];
      },
      useEffect() {},
    },
    '@tauri-apps/api/core': { invoke },
    'react/jsx-runtime': { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }), Fragment: 'fragment' },
    'lucide-react': { CheckCircle: () => null, X: () => null, CheckCircle: () => null, X: () => null, CheckCircleIcon: () => null, XIcon: () => null, Link2: () => null, RefreshCw: () => null, Eye: () => null },
    '../components/DevicePairing': { DevicePairing: pairing, PairedDevices: () => null },
    './DevicePairing': { DevicePairing: pairing, PairedDevices: () => null },
    './RemoteSourcePicker': { RemoteSourcePicker: () => null },
    './RemoteModelPicker': { RemoteModelPicker: () => null },
    '../api/remoteCoding': {},
  };
  new Function('require', 'exports', compiled)(name => {
    assert.ok(name in modules, `Unexpected module ${name}`);
    return modules[name];
  }, exports);
  function elements() {
    cursor = 0;
    const found = [];
    const visit = node => {
      if (!node || typeof node !== 'object') return;
      found.push(node);
      for (const child of [node.props?.children].flat(Infinity)) visit(child);
    };
    visit(exports.RemoteWorkspace());
    return found;
  }
  const input = label => elements().find(node => node.type === 'input' && node.props['aria-label'] === label);
  return { elements, input, slots, pairing };
}

test('confirmed desktop sign-in removes token field and clears text before job refresh finishes', async () => {
  let confirm;
  let finishList;
  const view = harness(async command => {
    if (command === 'remote_connect') return new Promise(resolve => { confirm = resolve; });
    if (command === 'remote_operation') return new Promise(resolve => { finishList = resolve; });
    throw new Error('Unexpected command');
  });
  view.input('HTTPS service origin').props.onChange({ target: { value: 'https://fixture.test' } });
  view.input('Client access token').props.onChange({ target: { value: 'synthetic-owner-token' } });
  const form = view.elements().find(node => node.type === 'form');
  form.props.onSubmit({ preventDefault() {} });
  assert.ok(view.input('Client access token'));
  confirm({});
  await settle();
  assert.equal(view.input('Client access token'), undefined);
  assert.equal(view.slots.includes('synthetic-owner-token'), false);
  assert.ok(view.elements().some(node => node.type === 'button' && Array.isArray(node.props.children) ? node.props.children.some(c => typeof c === 'string' && c.includes('Disconnect')) : typeof node.props.children === 'string' && node.props.children.includes('Disconnect')));
  finishList({ jobs: [] });
  await settle();
  assert.equal(view.input('Client access token'), undefined);
});

test('failed desktop sign-in clears token without claiming connection', async () => {
  const view = harness(async () => { throw new Error('Sign-in refused'); });
  view.input('HTTPS service origin').props.onChange({ target: { value: 'https://fixture.test' } });
  view.input('Client access token').props.onChange({ target: { value: 'synthetic-owner-token' } });
  view.elements().find(node => node.type === 'form').props.onSubmit({ preventDefault() {} });
  await settle();
  assert.equal(view.input('Client access token').props.value, '');
  assert.ok(view.elements().some(node => node.props?.role === 'alert' && node.props.children === 'Sign-in refused'));
  assert.equal(view.elements().some(node => node.type === 'button' && node.props.children === 'Disconnect'), false);
});

test('pairing appears before collapsed manual token sign-in', () => {
  const view = harness(async () => {});
  const elements = view.elements();
  const pairingIndex = elements.findIndex(node => node.type === view.pairing);
  const manualIndex = elements.findIndex(node => node.type === 'details');
  assert.ok(pairingIndex >= 0 && manualIndex > pairingIndex);
  assert.notEqual(elements[manualIndex].props.open, true);
});
