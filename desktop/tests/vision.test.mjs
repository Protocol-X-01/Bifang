import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/api/vision.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020,
  module: ts.ModuleKind.ESNext } }).outputText;
const vision = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const image = { sha256: 'a'.repeat(64), bytes: 128, width: 16, height: 8,
  mime_type: 'image/png', metadata_removed: true };
const receipt = { request_id: 'b'.repeat(32), provider: 'nebius', requested_model: 'actual-vision', reported_model: null,
  usage: { total_tokens: 12 }, capability_source: 'operator-declared', observed_at: 1,
  tools_enabled: false, image_storage: 'ephemeral' };
const result = { analysis: 'Observed a panel; check the source.', verification: 'unverified_visual_analysis', images: [image], receipt };

test('vision capabilities require explicit model and evidence, not a model-name heuristic', () => {
  const value = { provider: 'nebius', providers: ['nebius'], models: [{ provider: 'nebius', model: 'vision',
    capability_source: 'operator-declared', availability: 'listed_in_live_catalog' }] };
  assert.deepEqual(vision.parseVisualCatalog(value), value);
  for (const invalid of [null, {}, { ...value, models: [{ ...value.models[0], capability_source: 'name contains vision' }] },
    { ...value, models: [{ ...value.models[0], provider: 'nvidia' }] }]) assert.throws(() => vision.parseVisualCatalog(invalid));
});

test('prepared image and analysis parsers reject missing metadata, raw URLs and enabled tools', () => {
  const prepared = { ...image, data_url: 'data:image/png;base64,AA==' };
  assert.deepEqual(vision.parsePreparedImages({ images: [prepared] }), [prepared]);
  for (const invalid of [{ images: [] }, { images: [{ ...prepared, metadata_removed: false }] },
    { images: [{ ...prepared, width: 4_000_001 }] }, { images: [{ ...prepared, data_url: 'https://remote.invalid/image' }] }]) {
    assert.throws(() => vision.parsePreparedImages(invalid));
  }
  assert.deepEqual(vision.parseVisualResult(result), result);
  for (const invalid of [{ ...result, verification: 'tests_passed' },
    { ...result, receipt: { ...receipt, request_id: '' } }, { ...result, receipt: { ...receipt, tools_enabled: true } },
    { ...result, receipt: { ...receipt, reported_model: undefined } },
    { ...result, receipt: { ...receipt, usage: { total_tokens: -1 } } }]) assert.throws(() => vision.parseVisualResult(invalid));
});

test('upload limits cover count, MIME and bytes before local preparation', () => {
  assert.equal(vision.visualUploadError([{ type: 'image/png', size: 100 }]), null);
  for (const files of [[], Array(3).fill({ type: 'image/png', size: 10 }),
    [{ type: 'image/svg+xml', size: 10 }], [{ type: 'image/jpeg', size: 2_000_001 }]]) assert.ok(vision.visualUploadError(files));
});

test('visual handoff is explicitly untrusted text without image bytes or invented server identity', () => {
  const text = vision.visualObservations(vision.parseVisualResult({ ...result, arbitrary_secret: 'should-be-dropped' }));
  assert.ok(text.includes('untrusted evidence'));
  assert.ok(text.includes('"reported_model": null'));
  assert.ok(!text.includes('data:image') && !text.includes('should-be-dropped'));
  assert.ok(vision.visualObservations({ ...result, analysis: 'x'.repeat(9000) }).includes('"analysis_truncated": true'));
});
