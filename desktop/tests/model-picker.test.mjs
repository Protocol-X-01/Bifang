import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';
import { loadApi } from './helpers/local-api.mjs';

const source = await readFile(new URL('../src/components/ModelPicker.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const modelApi = await loadApi('models');
const settle = () => new Promise(resolve => setImmediate(resolve));

function findNode(node, predicate) {
  if (Array.isArray(node)) {
    for (const child of node) {
      const match = findNode(child, predicate);
      if (match) return match;
    }
    return null;
  }
  if (!node || typeof node !== 'object') return null;
  if (predicate(node)) return node;
  return findNode(node.props?.children, predicate);
}

function harness() {
  const slots = [];
  const requests = [];
  let cursor = 0;
  const modules = {
    '../api/localApi': {
      localFetch(path, options) {
        return new Promise((resolve, reject) => requests.push({ path, options, resolve, reject }));
      },
    },
    '../api/models': modelApi,
    react: {
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
      useEffect(effect, dependencies) {
        const position = cursor++;
        const previous = slots[position];
        if (!previous || dependencies.some((value, index) => value !== previous.dependencies[index])) {
          previous?.cleanup?.();
          slots[position] = { dependencies, cleanup: effect() };
        }
      },
    },
    'react/jsx-runtime': {
      Fragment: Symbol('Fragment'),
      jsx: (type, props) => ({ type, props }),
      jsxs: (type, props) => ({ type, props }),
    },
    'lucide-react': Object.fromEntries(['ChevronDown', 'RefreshCw', 'Sparkles', 'Zap', 'Shield'].map(name => [name, () => null])),
  };
  const exports = {};
  new Function('require', 'exports', compiled)(name => modules[name], exports);
  return {
    requests,
    render() {
      cursor = 0;
      return exports.ModelPicker({ selection: null, busy: false, onChange: () => {} });
    },
    refresh() {
      const button = findNode(this.render(), node => node.type === 'button');
      button.props.onClick();
    },
  };
}

test('failed catalog refresh preserves the last successful model list', async () => {
  const view = harness();
  view.render();
  assert.equal(view.requests.length, 1);
  view.requests[0].resolve({ ok: true, json: async () => ({
    provider: 'nebius', models: ['nvidia/Nemotron-3-Nano'], configured_model: 'nvidia/Nemotron-3-Nano',
    configured_mode: 'pinned', auto_available: false, roles: {},
  }) });
  await settle();

  view.refresh();
  view.render();
  assert.equal(view.requests.length, 2);
  view.requests[1].reject(new Error('synthetic network failure'));
  await settle();

  const rendered = JSON.stringify(view.render());
  assert.match(rendered, /nvidia\/Nemotron-3-Nano/);
  assert.match(rendered, /last successful model list remains available/);
  assert.doesNotMatch(rendered, /synthetic network failure/);
});
