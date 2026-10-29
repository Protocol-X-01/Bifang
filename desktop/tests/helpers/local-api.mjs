import { readFile } from 'node:fs/promises';
import ts from 'typescript';

export async function loadApi(name, native = { isTauri: () => false }) {
  const source = await readFile(new URL(`../../src/api/${name}.ts`, import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS,
  } }).outputText;
  const local = name === 'conversations' ? await loadApi('localApi', native) : null;
  const exports = {};
  new Function('require', 'exports', compiled)(name => {
    if (name === '@tauri-apps/api/core') return native;
    if (name === './localApi') return local;
    throw new Error(`Unexpected import: ${name}`);
  }, exports);
  return exports;
}
