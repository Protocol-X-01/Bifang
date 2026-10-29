import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/api/filespaces.ts', import.meta.url), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext } }).outputText;
const { rememberFilespace } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);

test('filespace history is bounded, deduplicated and records no file contents or credentials', () => {
  let spaces;
  for (let count = 0; count < 30; count += 1) spaces = rememberFilespace(spaces, `/projects/project-${count}`, count);
  assert.equal(spaces.length, 20);
  spaces = rememberFilespace(spaces, '/projects/project-20', 40);
  assert.equal(spaces.length, 20);
  assert.equal(spaces[0].name, 'project-20');
  assert.equal(spaces[0].lastOpened, 40);
  assert.equal(spaces.filter(space => space.path === '/projects/project-20').length, 1);
  assert.deepEqual(Object.keys(spaces[0]).sort(), ['lastOpened', 'name', 'path']);
  assert.equal(rememberFilespace([null, {}], 'C:\\Projects\\Fixture', 1)[0].name, 'Fixture');
});

test('workspace store persists filespaces, restores them and forgets history without closing the project', async () => {
  const cache = new Map();
  globalThis.localStorage = { getItem: key => cache.get(key) ?? null, setItem: (key, value) => cache.set(key, value), removeItem: key => cache.delete(key) };
  const storeSource = await readFile(new URL('../src/stores/bifangStore.ts', import.meta.url), 'utf8');
  const filespaceModule = `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`;
  const storeCode = ts.transpileModule(storeSource, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
    .replace("'zustand'", JSON.stringify(import.meta.resolve('zustand')))
    .replace("'zustand/middleware'", JSON.stringify(import.meta.resolve('zustand/middleware')))
    .replace("'../api/filespaces'", JSON.stringify(filespaceModule));
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(storeCode).toString('base64')}`;
  try {
    const { useWorkspaceStore } = await import(moduleUrl);
    useWorkspaceStore.getState().setWorkspace('/projects/First');
    useWorkspaceStore.getState().setWorkspace('/projects/Second');
    useWorkspaceStore.getState().clearWorkspace();
    assert.equal(useWorkspaceStore.getState().activeWorkspacePath, null);
    assert.equal(useWorkspaceStore.getState().filespaces.length, 2);
    const restored = (await import(`${moduleUrl}#restored`)).useWorkspaceStore;
    assert.equal(restored.getState().filespaces[0].path, '/projects/Second');
    restored.getState().setWorkspace('/projects/First');
    restored.getState().forgetWorkspace('/projects/First');
    assert.equal(restored.getState().workspacePath, '/projects/First');
    assert.equal(restored.getState().filespaces.length, 1);
    assert.equal(JSON.parse(cache.get('bifang-workspace')).state.filespaces[0].path, '/projects/Second');
  } finally {
    delete globalThis.localStorage;
  }
});
