import assert from 'node:assert/strict';
import test from 'node:test';
import { loadApi } from './helpers/local-api.mjs';

const api = await loadApi('conversations');

test('conversation summaries reject malformed server data', () => {
  const valid = { conversation_id: 'one', updated_at: 100, turn_count: 2 };
  assert.deepEqual(api.parseConversations([valid]), [valid]);
  for (const invalid of [null, {}, [null], [{ ...valid, conversation_id: '' }],
    [{ ...valid, updated_at: NaN }], [{ ...valid, updated_at: Infinity }],
    [{ ...valid, updated_at: -1 }], [{ ...valid, updated_at: 8.65e12 }],
    [{ ...valid, turn_count: 0.5 }], [{ ...valid, turn_count: -1 }]]) {
    assert.throws(() => api.parseConversations(invalid), /invalid conversation list/);
  }
});

test('restored turns have stable distinct identities without replaying tools', () => {
  const turns = api.parseHistory([
    { turn_id: 'one', user_message: '<script>untrusted</script>', assistant_response: 'answer',
      timestamp: 1, status: 'completed' },
    { turn_id: 'two', user_message: 'cancelled request', assistant_response: '',
      timestamp: 1, status: 'cancelled' },
  ]);
  const messages = api.historyMessages(turns);
  assert.equal(messages.length, 4);
  assert.equal(new Set(messages.map((message) => message.id)).size, 4);
  assert.equal(messages[0].content, '<script>untrusted</script>');
  assert.equal(messages[0].timestamp, 1000);
  assert.deepEqual(api.historyMessages(turns), messages);
  assert.equal(messages[3].role, 'system');
  assert.match(messages[3].content, /cancelled.*not be replayed/);
  assert.ok(messages.every((message) => !('tool_calls' in message)));
});

test('invalid history cannot replace current conversation', () => {
  const valid = { turn_id: 'one', user_message: 'question', assistant_response: 'answer',
    timestamp: 10, status: 'completed' };
  for (const invalid of [null, [null], [{ ...valid, timestamp: NaN }],
    [{ ...valid, turn_id: '' }], [{ ...valid, assistant_response: null }],
    [{ ...valid, status: false }]]) {
    assert.throws(() => api.parseHistory(invalid), /invalid conversation history/);
  }
});

test('listing encodes workspace, pagination and abort signal', async (context) => {
  const signal = new AbortController().signal;
  context.mock.method(globalThis, 'fetch', async (input, options) => {
    const url = new URL(input);
    assert.equal(url.origin, 'http://127.0.0.1:8000');
    assert.equal(url.searchParams.get('workspace'), '/tmp/project & other/测试');
    assert.equal(url.searchParams.get('limit'), '20');
    assert.equal(url.searchParams.get('offset'), '20');
    assert.equal(options.signal, signal);
    return new Response('[]');
  });
  assert.deepEqual(await api.savedConversations('/tmp/project & other/测试', 20, signal), []);
});

test('history fetch validates status and never displays a raw error body', async (context) => {
  context.mock.method(globalThis, 'fetch', async (input) => {
    assert.ok(input.endsWith('/sessions/id%2Fwith%3Fcharacters/history'));
    return new Response('PRIVATE-SERVER-ERROR', { status: 503 });
  });
  await assert.rejects(api.sessionHistory('id/with?characters'), (error) => {
    assert.match(error.message, /HTTP 503/);
    assert.doesNotMatch(error.message, /PRIVATE/);
    return true;
  });
});
