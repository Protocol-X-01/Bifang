import assert from 'node:assert/strict';
import test from 'node:test';
import { loadApi } from './helpers/local-api.mjs';

test('native requests use the current authenticated instance and forbid redirects', async context => {
  let port = 49231;
  const api = await loadApi('localApi', { isTauri: () => true, invoke: async command => {
    assert.equal(command, 'get_server_connection');
    return { version: 1, origin: `http://127.0.0.1:${port}`, api_key: 'a'.repeat(64) };
  } });
  context.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, `http://127.0.0.1:${port}/sessions`);
    assert.equal(options.headers.get('X-API-Key'), 'a'.repeat(64));
    assert.equal(options.redirect, 'error');
    assert.equal(options.method, 'POST');
    return new Response('{}');
  });
  await api.localFetch('/sessions', { method: 'POST' });
  port += 1;
  await api.localFetch('/sessions', { method: 'POST' });
});

test('failed native bootstrap never falls back to another service', async context => {
  const fetch = context.mock.method(globalThis, 'fetch', () => { throw new Error('unexpected network'); });
  const api = await loadApi('localApi', { isTauri: () => true, invoke: async () => { throw new Error('stopped'); } });
  await assert.rejects(api.localFetch('/models'), /stopped/);
  assert.equal(fetch.mock.callCount(), 0);
});

test('invalid origins, paths and aborted requests never send credentials', async context => {
  const fetch = context.mock.method(globalThis, 'fetch', () => { throw new Error('unexpected network'); });
  for (const origin of ['http://evil.test:123', 'http://127.0.0.1:0', 'http://127.0.0.1:99999', 'http://127.0.0.1:123/path']) {
    const api = await loadApi('localApi', { isTauri: () => true, invoke: async () => ({ version: 1, origin, api_key: 'a'.repeat(64) }) });
    await assert.rejects(api.localFetch('/models'), /Invalid local server/);
  }
  const api = await loadApi('localApi');
  for (const path of ['https://evil.test', '//evil.test', '/\\evil.test', '/models\n']) {
    await assert.rejects(api.localFetch(path), /Invalid local API path/);
  }
  await assert.rejects(api.localFetch('/models', { signal: AbortSignal.abort() }), { name: 'AbortError' });
  assert.equal(fetch.mock.callCount(), 0);
});
