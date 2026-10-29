import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('Apply freezes the displayed digest when confirmation opens and sends that snapshot', async () => {
  const source = await readFile(new URL('../src/components/DiffViewer.tsx', import.meta.url), 'utf8');
  assert.match(source, /reviewedPatch\.current = \{ sessionId, digest: patchDigest \};\s*applyDialog\.current\?\.showModal\(\)/);
  assert.match(source, /const reviewed = reviewedPatch\.current;/);
  assert.match(source, /reviewed\.sessionId !== sessionId/);
  assert.match(source, /JSON\.stringify\(\{ patch_sha256: reviewed\.digest \}\)/);
  assert.match(source, /reviewedPatch\.current = null;\s*applyDialog\.current\?\.close\(\)/);
  assert.match(source, /disabled=\{applying \|\| !diffText \|\| !patchDigest\}/);
  assert.doesNotMatch(source, /patch_sha256: patchDigest/);
});
