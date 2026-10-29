import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const compile = source => ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const source = compile(await readFile(new URL('../src/DeviceTerminal.tsx', import.meta.url), 'utf8'));
const distroCatalog = JSON.parse(await readFile(new URL('../src/distroCatalog.json', import.meta.url), 'utf8'));
const transport = {};
new Function('exports', compile(await readFile(new URL('../../desktop/src/api/localTerminal.ts', import.meta.url), 'utf8')))(transport);
const settle = () => new Promise(resolve => setImmediate(resolve));

function harness(invoke, { selection = '', onAskAgent, surface = null, scroll = () => {}, bufferType = 'normal', output = [{ text: 'SyntaxError at line 3', wrapped: false }] } = {}) {
  const slots = [];
  const cleanups = [];
  let cursor = 0;
  class Emulator {
    rows = 24;
    cols = 80;
    parser = { registerOscHandler: () => ({ dispose() {} }) };
    buffer = { active: { type: bufferType, length: output.length, getLine(index) {
      return output[index] && { isWrapped: output[index].wrapped, translateToString: () => output[index].text };
    } } };
    loadAddon() {}
    open() {}
    reset() {}
    focus() {}
    scrollLines(lines) { scroll(lines); }
    getSelection() { return selection; }
    dispose() {}
    writeln() {}
    write(bytes, done) { done?.(); }
    onData() { return { dispose() {} }; }
    onResize() { return { dispose() {} }; }
  }
  const exports = {};
  const modules = {
    './distroCatalog.json': { default: distroCatalog },
    react: {
      useRef(initial) { const position = cursor++; if (!(position in slots)) slots[position] = { current: position === 0 ? surface : initial }; return slots[position]; },
      useState(initial) { const position = cursor++; if (!(position in slots)) slots[position] = initial; return [slots[position], value => { slots[position] = typeof value === 'function' ? value(slots[position]) : value; }]; },
      useEffect(effect) { const position = cursor++; if (!(position in slots)) { slots[position] = true; cleanups.push(effect()); } },
    },
    '@tauri-apps/api/core': { invoke },
    '@xterm/xterm': { Terminal: Emulator },
    '@xterm/addon-fit': { FitAddon: class { fit() {} } },
    '@xterm/xterm/css/xterm.css': {},
    '../../desktop/src/api/localTerminal': transport,
    'react/jsx-runtime': { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
  };
  class Observer { observe() {} disconnect() {} }
  new Function('require', 'exports', 'ResizeObserver', source)(name => { assert.ok(name in modules); return modules[name]; }, exports, Observer);
  function elements() {
    cursor = 0;
    const found = [];
    const visit = node => { if (!node || typeof node !== 'object') return; found.push(node); for (const child of [node.props?.children].flat(Infinity)) visit(child); };
    visit(exports.DeviceTerminal({ visible: true, onAskAgent }));
    return found;
  }
  return { elements, unmount: () => cleanups.forEach(cleanup => cleanup?.()), button: label => elements().find(node => node.type === 'button' && node.props.children === label) };
}

test('touch scrolling moves history by rows and removes handlers on unmount', () => {
  const handlers = new Map();
  const moved = [];
  let prevented = 0;
  const surface = { clientHeight: 480,
    addEventListener(name, callback) { handlers.set(name, callback); },
    removeEventListener(name) { handlers.delete(name); },
  };
  const view = harness(async () => {}, { surface, scroll: lines => moved.push(lines) });
  view.elements();
  handlers.get('touchstart')({ touches: [{ clientY: 100 }] });
  const move = clientY => handlers.get('touchmove')({ touches: [{ clientY }], preventDefault() { prevented++; }, stopPropagation() {} });
  move(150);
  move(160);
  assert.deepEqual(moved, [-2, -1]);
  assert.equal(prevented, 2);
  handlers.get('touchend')();
  move(200);
  assert.deepEqual(moved, [-2, -1]);
  view.unmount();
  assert.equal(handlers.size, 0);
});

test('device shell starts only on explicit input and uses its native project directory', async () => {
  const calls = [];
  const view = harness(async (command, args) => {
    calls.push({ command, args });
    if (command === 'device_terminal_directory') return '/private/synthetic-project';
    if (command === 'terminal_open') return { id: 1, directory: args.path, program: '/system/bin/sh' };
    if (command === 'terminal_read') return new Promise(() => {});
    return null;
  });
  view.elements();
  assert.deepEqual(calls, []);
  view.button('Start device shell').props.onClick();
  await settle();
  assert.equal(calls[1].args.path, '/private/synthetic-project');
  assert.equal(calls[1].args.confirmed, true);
  view.button('Expand terminal').props.onClick();
  assert.equal(view.elements().find(node => node.props?.['aria-label'] === 'Device terminal').props['data-expanded'], 'true');
  view.button('Restore layout').props.onClick();
  assert.equal(view.elements().find(node => node.props?.['aria-label'] === 'Device terminal').props['data-expanded'], 'false');
  view.elements().find(node => node.type === 'input').props.onChange({ target: { value: 'printf hello' } });
  view.elements().find(node => node.type === 'form').props.onSubmit({ preventDefault() {} });
  await settle();
  const input = calls.find(call => call.command === 'terminal_write');
  assert.equal(new TextDecoder().decode(Uint8Array.from(input.args.data)), 'printf hello\r');
  view.button('Close shell').props.onClick();
  await settle();
  assert.ok(calls.some(call => call.command === 'terminal_close' && call.args.id === 1));
  assert.equal(calls.some(call => call.command === 'remote_operation'), false);
  view.unmount();
});

test('leaving the app while the directory request is pending never starts a shell', async () => {
  const calls = [];
  let finishDirectory;
  const view = harness(async command => {
    calls.push(command);
    if (command === 'device_terminal_directory') return new Promise(resolve => { finishDirectory = resolve; });
    throw new Error('No shell operation should run');
  });
  view.button('Start device shell').props.onClick();
  view.unmount();
  finishDirectory('/private/synthetic-project');
  await settle();
  assert.deepEqual(calls, ['device_terminal_directory']);
});

test('agent handoff includes only selected output and never submits or executes a job', async () => {
  const calls = [];
  const briefs = [];
  const view = harness(async (command, args) => {
    calls.push(command);
    if (command === 'device_terminal_directory') return '/private/synthetic-project';
    if (command === 'terminal_open') return { id: 1, directory: args.path, program: '/system/bin/sh' };
    if (command === 'terminal_read') return new Promise(() => {});
  }, {
    selection: 'SyntaxError at line 3', onAskAgent: brief => briefs.push(brief),
  });
  view.button('Start device shell').props.onClick();
  await settle();
  calls.length = 0;
  view.button('Select output').props.onClick();
  const field = view.elements().find(node => node.type === 'textarea');
  assert.equal(field.props.readOnly, true);
  field.props.onSelect({ currentTarget: { value: field.props.value, selectionStart: 0, selectionEnd: field.props.value.length } });
  view.button('Ask agent about selection').props.onClick();
  assert.equal(briefs.length, 1);
  assert.match(briefs[0], /SyntaxError at line 3/);
  assert.match(briefs[0], /untrusted source text/);
  assert.deepEqual(calls, []);
  view.unmount();
});

test('mobile output snapshot joins wrapped lines and shares only the chosen native text range', () => {
  const briefs = [];
  const view = harness(async () => {}, { onAskAgent: brief => briefs.push(brief),
    output: [{ text: 'first ', wrapped: false }, { text: 'line', wrapped: true }, { text: 'second line', wrapped: false }] });
  view.button('Select output').props.onClick();
  assert.equal(view.button('Ask agent about selection').props.disabled, true);
  const field = view.elements().find(node => node.type === 'textarea');
  assert.equal(field.props.value, 'first line\nsecond line');
  field.props.onSelect({ currentTarget: { value: field.props.value, selectionStart: 11, selectionEnd: 22 } });
  view.button('Ask agent about selection').props.onClick();
  assert.match(briefs[0], /second line$/);
  assert.doesNotMatch(briefs[0], /first line/);
  view.button('Select output').props.onClick();
  assert.equal(view.button('Ask agent about selection').props.disabled, true);
  view.unmount();
});

test('distribution selection comes before launch and unconnected distributions cannot start the system shell', async () => {
  const calls = [];
  const view = harness(async command => { calls.push(command); });
  const chooser = view.elements().find(node => node.type === 'select');
  assert.equal(chooser.props.value, 'android');
  assert.equal(view.elements().filter(node => node.type === 'option').length, 21);
  for (const environment of ['kali', 'blackarch']) {
    view.elements().find(node => node.type === 'select').props.onChange({ target: { value: environment } });
    assert.equal(view.button('Start device shell'), undefined);
    assert.ok(view.button('Connect runtime'));
    await settle();
    assert.deepEqual(calls, []);
  }
  view.unmount();
});

test('distribution installation opens its own transport after explicit connect and install', async () => {
  const calls = [];
  const view = harness(async (command, args) => {
    calls.push({ command, args });
    assert.equal(command, 'device_runtime_request');
    if (args.request.action === 'connect') return { version: '4.34.2', environments: [{ id: 'kali', name: 'Kali', installed: false, packages: 'apt' }] };
    if (args.request.action === 'terminal_open') return { id: 17, directory: '/root', program: 'Kali setup' };
    if (args.request.action === 'terminal_read') return new Promise(() => {});
    return {};
  });
  view.elements().find(node => node.type === 'select').props.onChange({ target: { value: 'kali' } });
  assert.deepEqual(calls, []);
  view.button('Connect runtime').props.onClick();
  await settle();
  view.button('Install distribution').props.onClick();
  await settle();
  const opened = calls.find(call => call.args.request.action === 'terminal_open');
  assert.equal(opened.args.request.environment, 'kali');
  assert.equal(opened.args.request.operation, 'install');
  assert.equal(opened.args.request.confirmed, true);
  view.unmount();
});

test('terminal layout keeps a shrinkable width, scrollable height and a single-row key strip', async () => {
  const view = harness(async () => {});
  const nodes = view.elements();
  assert.match(nodes.find(node => node.type === 'section').props.className, /min-w-0/);
  assert.ok(nodes.some(node => node.props?.className?.includes('device-terminal-output')));
  assert.doesNotMatch(nodes.find(node => node.props?.['aria-label'] === 'Terminal keys').props.className, /flex-wrap/);
  const styles = await readFile(new URL('../src/style.css', import.meta.url), 'utf8');
  assert.match(styles, /overflow-y: auto/);
  assert.match(styles, /min-height: 12rem/);
  assert.match(styles, /@media \(max-height: 500px\)/);
  assert.match(styles, /textarea:not\(\.xterm-helper-textarea\)/);
  view.unmount();
});

test('a failed terminal write preserves typed input for correction or retry', async () => {
  const view = harness(async (command, args) => {
    if (command === 'device_terminal_directory') return '/private/synthetic-project';
    if (command === 'terminal_open') return { id: 1, directory: args.path, program: '/system/bin/sh' };
    if (command === 'terminal_read') return new Promise(() => {});
    if (command === 'terminal_write') throw new Error('Synthetic terminal write failure');
    return null;
  });
  view.button('Start device shell').props.onClick();
  await settle();
  view.elements().find(node => node.type === 'input').props.onChange({ target: { value: 'printf hello' } });
  view.elements().find(node => node.type === 'form').props.onSubmit({ preventDefault() {} });
  await settle();
  assert.equal(view.elements().find(node => node.type === 'input').props.value, 'printf hello');
  assert.ok(view.elements().some(node => node.props?.role === 'alert' && /Synthetic terminal write failure/.test(node.props.children)));
  view.unmount();
});
