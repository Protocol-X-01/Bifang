export type RemoteAction = 'writes' | 'check' | 'review' | 'stage' | 'apply';
export interface RemoteJob {
  id: string;
  project_id: string;
  base_revision: string;
  status: string;
  candidate_sha256: string | null;
  requested_model: string;
  check_command: string[];
  check_timeout: number;
  writable: string[];
  proposal: Record<string, string> | null;
  receipt: { candidate_sha256: string; passed: boolean; exit_code: number; timed_out: boolean; command: string[] } | null;
}

const statuses = new Set(['queued', 'generating', 'awaiting_write_approval', 'awaiting_check_approval', 'queued_check', 'checking', 'verified', 'reviewed', 'staged', 'applied', 'rejected', 'check_denied', 'check_failed', 'cancelled', 'failed', 'interrupted', 'deleted']);
const digest = /^[a-f0-9]{64}$/;
const resource = /^[a-f0-9]{32}$/;
const object = (value: unknown): value is Record<string, any> => Boolean(value) && typeof value === 'object' && !Array.isArray(value);
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.length > 0 && value.every(item => typeof item === 'string');

export function parseRemoteJob(value: unknown): RemoteJob {
  if (!object(value) || !resource.test(value.id) || !resource.test(value.project_id) || !digest.test(value.base_revision) || !statuses.has(value.status)
    || !(value.candidate_sha256 === null || typeof value.candidate_sha256 === 'string' && digest.test(value.candidate_sha256))
    || typeof value.requested_model !== 'string' || !strings(value.check_command) || value.check_command.length > 32
    || !strings(value.writable) || value.writable.length > 8 || !Number.isInteger(value.check_timeout) || value.check_timeout < 1 || value.check_timeout > 60
    || !(value.proposal === null || object(value.proposal) && Object.values(value.proposal).every(content => typeof content === 'string'))
    || !(value.receipt === null || object(value.receipt) && digest.test(value.receipt.candidate_sha256)
      && typeof value.receipt.passed === 'boolean' && Number.isInteger(value.receipt.exit_code) && typeof value.receipt.timed_out === 'boolean'
      && strings(value.receipt.command))) throw new Error('Invalid remote job contract; no decision is available.');
  return value as RemoteJob;
}

export function nextRemoteAction(job: RemoteJob): RemoteAction | null {
  const actions: Record<string, RemoteAction> = { awaiting_write_approval: 'writes', awaiting_check_approval: 'check', verified: 'review', reviewed: 'stage', staged: 'apply' };
  const action = actions[job.status];
  if (!action || !job.candidate_sha256) return null;
  if (['review', 'stage', 'apply'].includes(action) && (!job.receipt?.passed || job.receipt.exit_code !== 0 || job.receipt.timed_out
    || job.receipt.candidate_sha256 !== job.candidate_sha256 || JSON.stringify(job.receipt.command) !== JSON.stringify(job.check_command))) return null;
  return action;
}

export function parseRemotePatch(value: unknown, job: RemoteJob): string {
  if (!object(value) || value.candidate_sha256 !== job.candidate_sha256 || !job.candidate_sha256
    || value.content_trust !== 'untrusted_source' || typeof value.patch !== 'string' || value.patch.length > 1000000) {
    throw new Error('Patch does not match this candidate. Refresh before deciding.');
  }
  return value.patch;
}

export function selectedCodingFiles(text: string, allowEmpty = false): Record<string, string> {
  const value: unknown = JSON.parse(text);
  if (!object(value) || (!allowEmpty && !Object.keys(value).length) || Object.keys(value).length > 8
    || !Object.entries(value).every(([path, content]) => path.length > 0 && path.length <= 200
      && !path.startsWith('/') && !/[\\:\x00-\x1f\x7f]/.test(path)
      && path.split('/').every(part => part && !['.', '..', '.git', '.bifang', '.arca', '.venv', '.ssh', '.aws', '.vercel', 'node_modules', '__pycache__'].includes(part) && !part.startsWith('.env'))
      && !['id_rsa', 'id_ed25519', 'credentials'].includes(path.split('/').pop() || '')
      && !/\.(pem|key|p12|pfx)$/i.test(path) && typeof content === 'string' && validUnicode(path) && validUnicode(content) && new TextEncoder().encode(content).length <= 64000)
    || new TextEncoder().encode(text).length > 128000) throw new Error('Select up to eight ordinary source files as a JSON path-to-content object.');
  return value;
}

function validUnicode(text: string): boolean {
  return Array.from(text).every(character => character.length !== 1 || character.charCodeAt(0) < 0xd800 || character.charCodeAt(0) > 0xdfff);
}

function codepointOrder(left: string, right: string): number {
  const first = Array.from(left), second = Array.from(right);
  for (let index = 0; index < Math.min(first.length, second.length); index++) {
    const difference = first[index].codePointAt(0)! - second[index].codePointAt(0)!;
    if (difference) return difference;
  }
  return first.length - second.length;
}

function pythonJsonString(value: string): string {
  return JSON.stringify(value).replace(/[\x7f-\uffff]/g, character => `\\u${character.charCodeAt(0).toString(16).padStart(4, '0')}`);
}

async function sha256(value: string): Promise<string> {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, '0')).join('');
}

export async function codingSnapshotDigest(files: Record<string, string>): Promise<string> {
  const entries = await Promise.all(Object.keys(files).sort(codepointOrder).map(async path => {
    if (!validUnicode(path) || !validUnicode(files[path])) throw new Error('Invalid Unicode source.');
    return `${pythonJsonString(path)}: ${pythonJsonString(await sha256(files[path]))}`;
  }));
  return sha256(`{${entries.join(', ')}}`);
}

function replacementPatch(before: Record<string, string>, after: Record<string, string>): string {
  let output = '';
  for (const path of Object.keys(after).sort(codepointOrder)) {
    const exists = Object.prototype.hasOwnProperty.call(before, path);
    if (exists && before[path] === after[path]) continue;
    const oldLines = (exists ? before[path] : '').match(/[^\n]*\n|[^\n]+$/g) || [];
    const newLines = after[path].match(/[^\n]*\n|[^\n]+$/g) || [];
    output += `diff --git a/${path} b/${path}\n${exists ? '' : 'new file mode 100644\n'}--- ${exists ? `a/${path}` : '/dev/null'}\n+++ b/${path}\n`;
    if (!oldLines.length && !newLines.length) continue;
    output += `@@ -${oldLines.length ? 1 : 0},${oldLines.length} +${newLines.length ? 1 : 0},${newLines.length} @@\n`;
    for (const [prefix, lines] of [['-', oldLines], ['+', newLines]] as const) {
      for (const line of lines) output += prefix + line + (line.endsWith('\n') ? '' : '\n\\ No newline at end of file\n');
    }
  }
  return output;
}

export async function verifyRemoteCandidate(job: RemoteJob, project: unknown): Promise<{ files: Record<string, string>; patch: string | null }> {
  if (!object(project) || project.id !== job.project_id || typeof project.revision !== 'string' || !digest.test(project.revision)
    || !object(project.files) || !job.candidate_sha256 || !job.proposal || !Object.keys(job.proposal).length
    || Object.keys(job.proposal).some(path => !job.writable.includes(path))) throw new Error('Candidate verification failed; no approval is available.');
  const baseline = selectedCodingFiles(JSON.stringify(project.files), true);
  if (await codingSnapshotDigest(baseline) !== project.revision) throw new Error('Hosted source does not match its revision digest.');
  const files = selectedCodingFiles(JSON.stringify({ ...baseline, ...job.proposal }));
  if (await codingSnapshotDigest(files) !== job.candidate_sha256) throw new Error('Reconstructed candidate digest differs from the proposed candidate.');
  if (job.status === 'applied' && project.revision === job.candidate_sha256) return { files, patch: null };
  if (project.revision !== job.base_revision) throw new Error('Hosted baseline changed. Refresh before making a decision.');
  const patch = replacementPatch(baseline, files);
  if (!patch) throw new Error('Candidate contains no source change.');
  return { files, patch };
}

export async function importCodingFiles(selected: Array<{ name: string; size: number; arrayBuffer: () => Promise<ArrayBuffer> }>, existing: Record<string, string>): Promise<Record<string, string>> {
  if (!selected.length || selected.length + Object.keys(existing).length > 8) throw new Error('Choose at most eight source files in total.');
  const entries: [string, string][] = [];
  const names = new Set(Object.keys(existing));
  for (const file of selected) {
    if (file.size > 64000 || names.has(file.name)) throw new Error('A selected file is too large or has a duplicate name. Remove or rename it first.');
    selectedCodingFiles(JSON.stringify({ [file.name]: '' }));
    names.add(file.name);
    const bytes = await file.arrayBuffer();
    if (bytes.byteLength > 64000 || bytes.byteLength !== file.size) throw new Error('Selected file changed or exceeds the size limit.');
    let content: string;
    try { content = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes); }
    catch { throw new Error('Select UTF-8 source files, not binary data.'); }
    if (content.includes('\0')) throw new Error('Select text source, not binary data.');
    entries.push([file.name, content]);
  }
  return selectedCodingFiles(JSON.stringify({ ...existing, ...Object.fromEntries(entries) }));
}
