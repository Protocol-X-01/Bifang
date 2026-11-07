import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { jsx, jsxs } from 'react/jsx-runtime';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

const source = await readFile(new URL('../src/components/ReviewPanel.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: {
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;
const settle = () => new Promise(resolve => setImmediate(resolve));

function harness(review) {
  const slots = [];
  const cleanups = [];
  const requests = [];
  let cursor = 0;
  const state = { sessionId: 'fixture', busy: false, setBusy(value) { state.busy = value; } };
  const useSessionStore = selector => selector(state);
  useSessionStore.getState = () => state;
  const exports = {};
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
      useEffect(effect) {
        const position = cursor++;
        if (!(position in slots)) { slots[position] = true; cleanups.push(effect()); }
      },
    },
    '../api/localApi': { localFetch: async path => {
      requests.push(path);
      return { ok: true, json: async () => review };
    } },
    '../stores/bifangStore': { useSessionStore },
    'react/jsx-runtime': { jsx, jsxs },
    'lucide-react': Object.fromEntries(
      ['X', 'Loader2', 'AlertTriangle', 'CheckCircle', 'MessageSquare', 'Eye'].map(name => [name, () => null]),
    ),
  };
  new Function('require', 'exports', 'setTimeout', 'clearTimeout', compiled)(name => {
    assert.ok(name in modules, `Unexpected module ${name}`);
    return modules[name];
  }, exports, () => 1, () => {});
  return {
    requests,
    render() { cursor = 0; return exports.ReviewPanel(); },
    unmount() { cleanups.forEach(cleanup => cleanup?.()); },
  };
}

function elements(node) {
  if (!node || typeof node !== 'object') return [];
  return [node, ...[node.props?.children].flat(Infinity).flatMap(elements)];
}

const worker = { role: 'investigator', status: 'completed', analysis: 'Inspected evidence.', routing: [], observations: [] };

for (const failure of [
  { status: 'stopped', stop_reason: 'provider_filter', analysis: 'I cannot complete the review.',
    error: 'The provider stopped the review before a final answer.' },
  { status: 'stopped', stop_reason: 'output_limit', analysis: 'Partial review',
    error: 'The model reached its response limit before finishing the review.' },
  { status: 'stopped', stop_reason: 'empty_analysis', analysis: '',
    error: 'The model returned no final review. Choose another model or a smaller task.' },
  { status: 'failed', provider_http_status: 404, analysis: '',
    error: 'The provider rejected the review request (HTTP 404).' },
]) {
  test(`worker ${failure.stop_reason ?? failure.provider_http_status} shows its error separately from analysis`, async context => {
    const view = harness({ status: 'failed', workers: [{ ...worker, ...failure }, { ...worker, role: 'reviewer' }] });
    context.after(() => view.unmount());
    view.render();
    await settle();
    const articles = elements(view.render()).filter(node => node.type === 'article');
    const failed = elements(articles[0]);
    const alert = failed.find(node => node.props.role === 'alert');
    assert.ok(alert, 'the affected worker must explain why it did not complete');
    assert.equal(alert.type, 'p');
    assert.equal(alert.props.children, failure.error);
    assert.equal(failed.find(node => node.type === 'pre').props.children, failure.analysis);
    assert.equal(elements(articles[1]).some(node => node.props.role === 'alert'), false);
    assert.deepEqual(view.requests, ['/sessions/fixture/review']);
  });
}

for (const status of ['stopped', 'failed']) {
  test(`${status} worker errors render markup as plain React text`, async context => {
    const error = '<img src=x onerror=alert(1)> **retry**';
    const analysis = '<script>alert(2)</script> Partial analysis';
    const view = harness({ status: 'failed', workers: [{ ...worker, status, error, analysis }] });
    context.after(() => view.unmount());
    view.render();
    await settle();
    const tree = view.render();
    const alert = elements(tree).find(node => node.props.role === 'alert');
    assert.ok(alert);
    assert.equal(alert.props.children, error);
    const html = renderToStaticMarkup(tree);
    assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt; **retry**'));
    assert.ok(html.includes('&lt;script&gt;alert(2)&lt;/script&gt; Partial analysis'));
    assert.doesNotMatch(html, /<img|<script|<strong>/);
  });
}

test('workers without optional error metadata retain their analysis without an empty alert', async context => {
  const view = harness({ status: 'completed', workers: [worker] });
  context.after(() => view.unmount());
  view.render();
  await settle();
  const nodes = elements(view.render());
  assert.equal(nodes.some(node => node.props.role === 'alert'), false);
  assert.equal(nodes.find(node => node.type === 'pre').props.children, worker.analysis);
});
