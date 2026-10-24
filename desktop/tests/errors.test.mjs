import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/api/errors.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: {
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext,
} }).outputText;
const { chatErrorMessage } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

test('chat displays actionable sandbox detail instead of JSON wrapper', async () => {
  const detail = 'Bubblewrap unavailable; refusing unsandboxed execution.';
  const response = new Response(JSON.stringify({ detail }), { status: 503 });
  assert.equal(await chatErrorMessage(response), detail);
});

test('malformed errors use safe status text, not raw server HTML or objects', async () => {
  for (const body of ['<html>private traceback</html>', '{}', '{"detail":[]}', '{"detail":" "}']) {
    assert.equal(await chatErrorMessage(new Response(body, { status: 500 })),
      'Chat request failed (HTTP 500).');
  }
});
