import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, readdir, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createServer, request as rawRequest } from 'node:http';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../dev/localWorkspaces.ts', import.meta.url), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const { createWorkspaceMiddleware } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);

test('browser workspace service creates real folders, reopens them and enforces its filesystem/auth boundaries', async () => {
  const fixture = await mkdtemp(path.join(tmpdir(), 'bifang-browser-workspaces-'));
  const root = path.join(fixture, 'home'), outside = path.join(fixture, 'outside');
  await mkdir(root); await mkdir(outside); await symlink(outside, path.join(root, 'escape'));
  const middleware = createWorkspaceMiddleware(root);
  const server = createServer((request, response) => middleware(request, response, () => { response.statusCode = 404; response.end(); }));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = `http://127.0.0.1:${server.address().port}`;
  const headers = { Origin: address, 'Content-Type': 'application/json', 'X-Bifang-Workspace-Client': 'preview' };
  const request = (action, body, extra = {}) => fetch(`${address}/__bifang/workspaces/${action}`, { method: 'POST', headers: { ...headers, ...extra }, body: JSON.stringify(body) });
  try {
    assert.equal((await request('create', { parent: root, name: 'blocked' })).status, 401);
    assert.equal((await request('session', {}, { Origin: 'https://untrusted.example' })).status, 403);
    const rebound = await new Promise((resolve, reject) => {
      const call = rawRequest(`${address}/__bifang/workspaces/session`, { method: 'POST', headers: { ...headers, Host: 'rebind.example' } }, response => { response.resume(); resolve(response.statusCode); });
      call.on('error', reject); call.end('{}');
    });
    assert.equal(rebound, 403);
    assert.equal((await request('session', {}, { 'X-Bifang-Workspace-Client': '' })).status, 403);
    assert.equal((await request('create', { parent: root, name: 'blocked' }, { 'X-Bifang-Workspace-Token': 'é'.repeat(64) })).status, 401);
    const handshake = await request('session', {});
    assert.equal(handshake.headers.get('access-control-allow-origin'), null);
    assert.equal(handshake.headers.get('cache-control'), 'no-store');
    const session = await handshake.json();
    const auth = { 'X-Bifang-Workspace-Token': session.token };
    assert.equal(session.root, root);
    const created = await request('create', { parent: root, name: 'My project' }, auth);
    assert.equal(created.status, 201);
    const workspace = (await created.json()).path;
    assert.equal(workspace, path.join(root, 'My project'));
    assert.deepEqual(await readdir(workspace), []);
    await writeFile(path.join(workspace, 'keep.txt'), 'preserve');
    assert.equal((await request('create', { parent: root, name: 'My project' }, auth)).status, 400);
    assert.equal(await readFile(path.join(workspace, 'keep.txt'), 'utf8'), 'preserve');
    for (const parent of [outside, path.join(root, 'escape')]) {
      assert.equal((await request('create', { parent, name: 'escape' }, auth)).status, 400);
    }
    for (const name of ['../escape', '.git', 'CON', 'bad/name', 'name ', 'bad:name']) {
      assert.equal((await request('create', { parent: root, name }, auth)).status, 400);
    }
    assert.equal((await request('create', { parent: root, name: 'extra', command: 'must not execute' }, auth)).status, 400);
    assert.equal((await request('resolve', { path: workspace }, auth)).status, 200);
    const tree = await (await request('tree', { path: workspace }, auth)).json();
    assert.equal(tree[0].name, 'keep.txt');
    assert.equal(tree[0].type, 'file');
    const directories = await (await request('directories', { path: root }, auth)).json();
    assert.deepEqual(directories.directories.map(entry => entry.name), ['My project']);
    assert.deepEqual(await readdir(outside), []);
    const clientSource = await readFile(new URL('../src/api/workspaces.ts', import.meta.url), 'utf8');
    const shim = `data:text/javascript;base64,${Buffer.from('export const isTauri = () => false; export const invoke = () => { throw new Error("Native bridge must not be used"); };').toString('base64')}`;
    const clientCode = ts.transpileModule(clientSource, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText.replace('@tauri-apps/api/core', shim);
    const client = await import(`data:text/javascript;base64,${Buffer.from(clientCode).toString('base64')}`);
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (resource, options) => originalFetch(new URL(resource, address), { ...options, headers: { ...options.headers, Origin: address } });
    try {
      assert.equal(client.nativeWorkspace(), false);
      const createdPath = await client.createWorkspace(root, 'Client project');
      assert.deepEqual(await readdir(createdPath), []);
      assert.equal(await client.resolveWorkspace(createdPath), createdPath);
      assert.deepEqual(JSON.parse(await client.workspaceTree(createdPath)), []);
      assert.equal((await client.workspaceDirectories()).root, root);
      assert.ok((await client.workspaceDirectories(root)).directories.some(entry => entry.path === createdPath));
      await assert.rejects(client.createWorkspace(root, 'Client project'), /already uses/);
      await assert.rejects(client.resolveWorkspace(outside), /filespace root/);
    } finally {
      globalThis.fetch = originalFetch;
    }
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    await rm(fixture, { recursive: true, force: true });
  }
});
