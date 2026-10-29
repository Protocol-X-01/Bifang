import assert from 'node:assert/strict';
import test from 'node:test';
import { loadApi } from './helpers/local-api.mjs';

test('terminal resize follows the latest message without stealing history scroll position', async context => {
  let resize;
  let scroll;
  let disconnected = false;
  const original = globalThis.ResizeObserver;
  globalThis.ResizeObserver = class {
    constructor(callback) { resize = callback; }
    observe() {}
    disconnect() { disconnected = true; }
  };
  context.after(() => {
    if (original) globalThis.ResizeObserver = original;
    else delete globalThis.ResizeObserver;
  });
  const viewport = {
    clientHeight: 600, scrollHeight: 1200, scrollTop: 600,
    addEventListener(event, callback) { assert.equal(event, 'scroll'); scroll = callback; },
    removeEventListener(event, callback) { assert.equal(event, 'scroll'); assert.equal(callback, scroll); },
  };
  const { followViewportResize } = await loadApi('chatViewport');
  const stop = followViewportResize(viewport);
  viewport.clientHeight = 350;
  scroll();
  resize();
  assert.equal(viewport.scrollTop, 1200);
  viewport.scrollTop = 200;
  scroll();
  viewport.clientHeight = 600;
  resize();
  assert.equal(viewport.scrollTop, 200);
  viewport.scrollTop = 600;
  scroll();
  viewport.clientHeight = 0;
  resize();
  assert.equal(viewport.scrollTop, 600);
  viewport.clientHeight = 350;
  resize();
  assert.equal(viewport.scrollTop, 1200);
  stop();
  assert.equal(disconnected, true);
});
