import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('engineering accepts explicit outputs without an existing source and retains confirmation', async () => {
  const source = await readFile(new URL('../src/components/CandidatePanel.tsx', import.meta.url), 'utf8');
  assert.match(source, /\(!files\.trim\(\) && !writable\.trim\(\)\)/);
  assert.match(source, /writable: writable\.trim\(\) \? paths\(writable\) : selected/);
  assert.match(source, /inference_confirmed: true/);
  assert.match(source, /onClick=\{\(\) => setIntent\('start'\)\}/);
  assert.match(source, /optional for a new project/);
});
