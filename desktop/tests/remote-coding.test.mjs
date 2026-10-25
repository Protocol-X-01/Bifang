import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { spawnSync } from 'node:child_process';
import ts from 'typescript';

const source = await readFile(new URL('../src/api/remoteCoding.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext } }).outputText;
const contract = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const hash = 'a'.repeat(64);
const job = { id: 'b'.repeat(32), project_id: 'c'.repeat(32), base_revision: 'd'.repeat(64), status: 'awaiting_write_approval', candidate_sha256: hash,
  requested_model: 'exact-model', writable: ['source.py'], check_command: ['python', '-m', 'unittest'], check_timeout: 30,
  proposal: { 'source.py': 'return 1' }, receipt: null };
const receipt = { candidate_sha256: hash, passed: true, exit_code: 0, timed_out: false, command: job.check_command };

test('remote decisions progress only through an explicit candidate-bound state', () => {
  assert.deepEqual(contract.parseRemoteJob(job), job);
  for (const [status, action] of Object.entries({ awaiting_write_approval: 'writes', awaiting_check_approval: 'check', verified: 'review', reviewed: 'stage', staged: 'apply' })) {
    assert.equal(contract.nextRemoteAction({ ...job, status, receipt }), action);
  }
  for (const status of ['queued', 'generating', 'checking', 'applied', 'rejected', 'interrupted']) assert.equal(contract.nextRemoteAction({ ...job, status, receipt }), null);
  for (const invalid of [null, { ...receipt, passed: false }, { ...receipt, exit_code: 1 }, { ...receipt, timed_out: true },
    { ...receipt, candidate_sha256: 'd'.repeat(64) }, { ...receipt, command: ['true'] }]) {
    assert.equal(contract.nextRemoteAction({ ...job, status: 'staged', receipt: invalid }), null);
  }
});

test('patches must belong to displayed candidate and remain untrusted text', () => {
  const patch = { candidate_sha256: hash, patch: '<script>not instructions</script>', content_trust: 'untrusted_source' };
  assert.equal(contract.parseRemotePatch(patch, job), patch.patch);
  for (const invalid of [{ ...patch, candidate_sha256: 'd'.repeat(64) }, { ...patch, content_trust: 'trusted' }, { ...patch, patch: {} }]) assert.throws(() => contract.parseRemotePatch(invalid, job));
});

test('invalid job contracts cannot unlock approval controls', () => {
  for (const invalid of [null, {}, { ...job, status: 'auto_approved' }, { ...job, check_timeout: 1000 }, { ...job, candidate_sha256: 'bad' },
    { ...job, check_command: 'sh -c true' }, { ...job, receipt: { ...receipt, passed: 'true' } }, { ...job, proposal: { 'source.py': 123 } }]) {
    assert.throws(() => contract.parseRemoteJob(invalid));
  }
});

test('source selection excludes credentials, traversal, duplicates of normalized paths and oversized files', () => {
  assert.deepEqual(contract.selectedCodingFiles('{"source.py":"return 1"}'), { 'source.py': 'return 1' });
  for (const path of ['.env', 'nested/.env.local', '/etc/passwd', '../secret', './a.py', 'a//b.py', 'a/../b.py', '.git/config', 'a.key', 'C:\\file']) {
    assert.throws(() => contract.selectedCodingFiles(JSON.stringify({ [path]: 'content' })));
  }
  for (const invalid of [{}, [], { 'a.py': 123 }, { 'a.py': 'a'.repeat(64001) }]) assert.throws(() => contract.selectedCodingFiles(JSON.stringify(invalid)));
});

test('native transport is fixed-route, session-only and does not weaken browser policy', async () => {
  const native = await readFile(new URL('../src-tauri/src/remote.rs', import.meta.url), 'utf8');
  assert.match(native, /https_only\(true\)/);
  assert.match(native, /Policy::none\(\)/);
  assert.match(native, /set_sensitive\(true\)/);
  assert.match(native, /no_proxy\(\)/);
  assert.doesNotMatch(native, /danger_accept_invalid|std::fs|println!|eprintln!/);
  const view = await readFile(new URL('../src/components/RemoteWorkspace.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(view, /localStorage|sessionStorage|dangerouslySetInnerHTML|console\./);
  assert.match(view, /candidate_sha256: job.candidate_sha256/);
  assert.match(view, /pending.current.key/);
});

test('candidate SHA-256 matches independent Python vectors including Unicode codepoint ordering', async () => {
  const vectors = JSON.parse(await readFile(new URL('./coding-digest-vectors.json', import.meta.url), 'utf8'));
  for (const vector of vectors) assert.equal(await contract.codingSnapshotDigest(vector.files), vector.sha256);
  await assert.rejects(contract.codingSnapshotDigest({ 'a.py': '\ud800' }));
  await assert.rejects(contract.codingSnapshotDigest({ '\udfff.py': 'source' }));
});

async function candidateFixture(before, writes, status = 'awaiting_write_approval') {
  const after = { ...before, ...writes };
  const baseline = await contract.codingSnapshotDigest(before);
  const candidate = await contract.codingSnapshotDigest(after);
  return { job: { ...job, base_revision: baseline, candidate_sha256: candidate, proposal: writes, writable: Object.keys(writes), status },
    project: { id: job.project_id, revision: baseline, files: before }, after };
}

test('reconstruction rejects tampering, changed baseline and writes outside approved paths', async () => {
  const fixture = await candidateFixture({ 'a.py': 'before\n', 'test.py': 'immutable\n' }, { 'a.py': 'after\n' });
  const verified = await contract.verifyRemoteCandidate(fixture.job, fixture.project);
  assert.deepEqual(verified.files, fixture.after);
  assert.match(verified.patch, /\+after/);
  for (const project of [{ ...fixture.project, id: 'e'.repeat(32) }, { ...fixture.project, revision: hash },
    { ...fixture.project, files: { ...fixture.project.files, 'test.py': 'tampered' } }]) {
    await assert.rejects(contract.verifyRemoteCandidate(fixture.job, project));
  }
  for (const invalid of [{ ...fixture.job, base_revision: hash }, { ...fixture.job, candidate_sha256: hash },
    { ...fixture.job, writable: ['test.py'] }, { ...fixture.job, proposal: { 'a.py': 'altered' } }]) {
    await assert.rejects(contract.verifyRemoteCandidate(invalid, fixture.project));
  }
  const applied = { ...fixture.job, status: 'applied' };
  assert.equal((await contract.verifyRemoteCandidate(applied, { ...fixture.project, files: fixture.after, revision: fixture.job.candidate_sha256 })).patch, null);
});

test('locally generated replacement patches actually apply byte-exactly with git', async () => {
  for (const [before, writes] of [
    [{ 'source.py': 'first\nsecond\n', 'tests.py': 'unchanged' }, { 'source.py': 'first\nfixed\n' }],
    [{ 'source.py': 'no final newline' }, { 'source.py': 'changed no newline' }],
    [{ 'source.py': 'first\r\nsecond\r\n' }, { 'source.py': 'new\r\n' }],
    [{ 'source.py': 'remove contents\n' }, { 'source.py': '' }],
    [{ 'source.py': 'stable' }, { 'new file.py': 'new source\n' }],
    [{ 'source.py': 'stable' }, { 'empty.py': '' }],
    [{ 'Ω.py': '\ufeffCafé\u2028source' }, { 'Ω.py': '🍂\nnew\n' }],
  ]) {
    const fixture = await candidateFixture(before, writes);
    const verified = await contract.verifyRemoteCandidate(fixture.job, fixture.project);
    const directory = await mkdtemp(join(tmpdir(), 'bifang-client-patch-'));
    try {
      assert.equal(spawnSync('git', ['init', '-q'], { cwd: directory }).status, 0);
      for (const [path, content] of Object.entries(before)) { await mkdir(dirname(join(directory, path)), { recursive: true }); await writeFile(join(directory, path), content); }
      for (const arguments_ of [['apply', '--check', '-'], ['apply', '-']]) {
        const result = spawnSync('git', arguments_, { cwd: directory, input: verified.patch, encoding: 'utf8' });
        assert.equal(result.status, 0, result.stderr);
      }
      for (const [path, content] of Object.entries(fixture.after)) assert.equal(await readFile(join(directory, path), 'utf8'), content);
    } finally { await rm(directory, { recursive: true, force: true }); }
  }
});

test('selected-file import preserves UTF-8/BOM bytes and rejects binary, secret paths, duplicates and growth', async () => {
  const file = (name, content) => {
    const bytes = new TextEncoder().encode(content);
    return { name, size: bytes.byteLength, arrayBuffer: async () => bytes.buffer };
  };
  assert.deepEqual(await contract.importCodingFiles([file('source.py', '\ufeffCafé\r\n')], {}), { 'source.py': '\ufeffCafé\r\n' });
  for (const name of ['.env', '.aws/credentials', '.ssh/id_rsa', '.bifang/history.json', '../source.py', 'source.key']) {
    let reads = 0;
    await assert.rejects(contract.importCodingFiles([{ name, size: 0, arrayBuffer: async () => { reads++; return new ArrayBuffer(0); } }], {}));
    assert.equal(reads, 0);
  }
  for (const selected of [[file('source.py', 'binary\0data')], [file('source.py', 'a'), file('source.py', 'b')],
    [{ name: 'source.py', size: 1, arrayBuffer: async () => new Uint8Array([0xff]).buffer }],
    [{ ...file('source.py', 'a'), size: 0 }]]) await assert.rejects(contract.importCodingFiles(selected, {}));
  await assert.rejects(contract.importCodingFiles([file('source.py', 'new')], { 'source.py': 'old' }));
});
