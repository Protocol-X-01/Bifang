import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

async function loadApi(name) {
  const source = await readFile(new URL(`../src/api/${name}.ts`, import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.ESNext } }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
}

const models = await loadApi('models');
const conversations = await loadApi('conversations');

test('catalog requires explicit verified metadata and configuration mode', () => {
  const valid = { provider: 'nebius', models: ['vendor/model'], configured_model: 'custom',
    configured_mode: 'auto', auto_available: true, roles: { fast: 'vendor/model' } };
  assert.deepEqual(models.parseModelCatalog(valid), valid);
  for (const invalid of [null, {}, { ...valid, configured_mode: undefined },
    { ...valid, models: [null] }, { ...valid, auto_available: 'yes' },
    { ...valid, roles: [] }, { ...valid, roles: { fast: 1 } }]) {
    assert.throws(() => models.parseModelCatalog(invalid), /invalid model catalog/);
  }
});

test('selection round trips configured, automatic and explicit model identifiers', () => {
  for (const value of ['configured', 'auto', 'model:vendor/model:revision']) {
    assert.equal(models.selectionValue(models.selectionFor(value)), value);
  }
  for (const value of ['', 'model:', 'arbitrary']) {
    assert.throws(() => models.selectionFor(value), /Invalid model selection/);
  }
});

const receipt = { provider: 'nebius', requested_model: 'requested', reported_model: null,
  role: 'balanced', task_type: 'chat', usage: { total_tokens: 3 } };

test('receipts never substitute requested model for absent server identity', () => {
  assert.equal(conversations.parseRoutingReceipts([receipt])[0].reported_model, null);
  assert.deepEqual(conversations.parseRoutingReceipts(undefined), []);
  for (const invalid of [null, {}, [null], [{ ...receipt, reported_model: undefined }],
    [{ ...receipt, usage: { total_tokens: -1 } }], [{ ...receipt, usage: { total_tokens: NaN } }]]) {
    assert.throws(() => conversations.parseRoutingReceipts(invalid), /invalid model receipts/);
  }
});

test('history restoration preserves routing receipts without replaying tools', () => {
  const turns = conversations.parseHistory([{ turn_id: 'turn', user_message: 'question',
    assistant_response: 'answer', timestamp: 1, status: 'completed', routing: [receipt] }]);
  const messages = conversations.historyMessages(turns);
  assert.deepEqual(messages[1].routing, [receipt]);
  assert.ok(messages.every((message) => !('tool_calls' in message)));
});
