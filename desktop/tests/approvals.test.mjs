import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/api/approvals.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020,
  module: ts.ModuleKind.ESNext } }).outputText;
const { approvalRequest } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

test('only full tool approval sends explicit confirmation', () => {
  for (const mode of ['manual', 'auto', 'full']) {
    assert.deepEqual(approvalRequest(mode), { approval_mode: mode, full_access_confirmed: mode === 'full' });
  }
});

test('unknown approval modes never become automatic approval', () => {
  for (const mode of ['', 'trusted', 'FULL', undefined, null]) {
    assert.throws(() => approvalRequest(mode), /Invalid approval mode/);
  }
});
