import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/components/RemoteModelPicker.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const settle = () => new Promise(resolve => setImmediate(resolve));

function harness() {
  const slots = [];
  const requests = [];
  let cursor = 0;
  let selected = 'stale-model';
  const onChange = value => { selected = value; };
  const exports = {};
  const modules = {
    react: {
      useState(initial) {
        const position = cursor++;
        if (!(position in slots)) slots[position] = initial;
        return [slots[position], value => { slots[position] = typeof value === 'function' ? value(slots[position]) : value; }];
      },
      useEffect(effect, dependencies) {
        const position = cursor++;
        const previous = slots[position];
        if (!previous || dependencies.some((value, index) => value !== previous.dependencies[index])) {
          previous?.cleanup?.();
          slots[position] = { dependencies, cleanup: effect() };
        }
      },
    },
    '@tauri-apps/api/core': { invoke: (command, args) => new Promise((resolve, reject) => { requests.push({ command, args, resolve, reject }); }) },
    'react/jsx-runtime': { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    'lucide-react': { RefreshCw: () => null },
  };
  new Function('require', 'exports', compiled)(name => modules[name], exports);
  return {
    requests, parse: exports.parseRemoteModels, get selected() { return selected; },
    render(provider = 'nebius') { cursor = 0; return exports.RemoteModelPicker({ provider, value: selected, disabled: false, onChange }); },
  };
}

test('catalog validation rejects stale provider, duplicates and unlisted defaults', () => {
  const { parse } = harness();
  const valid = { provider: 'nebius', models: ['one'], default_model: 'one' };
  assert.deepEqual(parse(valid, 'nebius'), { models: ['one'], default_model: 'one' });
  for (const value of [{ ...valid, provider: 'nvidia' }, { ...valid, models: ['one', 'one'] }, { ...valid, default_model: 'unknown' }, { ...valid, models: ['bad\nmodel'] }]) {
    assert.throws(() => parse(value, 'nebius'));
  }
});

test('switching providers ignores an earlier catalog response and clears old selection', async () => {
  const view = harness();
  view.render();
  assert.equal(view.selected, '');
  view.render('nvidia');
  assert.equal(view.requests.length, 2);
  view.requests[1].resolve({ provider: 'nvidia', models: ['current-model'], default_model: 'current-model' });
  await settle();
  assert.equal(view.selected, 'current-model');
  view.requests[0].resolve({ provider: 'nebius', models: ['stale-model'], default_model: 'stale-model' });
  await settle();
  assert.equal(view.selected, 'current-model');
  assert.equal(view.requests[1].args.operation.provider, 'nvidia');
});

test('failed discovery leaves no guessed selection and exposes retry', async () => {
  const view = harness();
  view.render();
  view.requests[0].reject(new Error('private provider error'));
  await settle();
  const rendered = JSON.stringify(view.render());
  assert.equal(view.selected, '');
  assert.match(rendered, /Could not load the service model list/);
  assert.match(rendered, /Refresh models/);
  assert.doesNotMatch(rendered, /private provider error/);
});
