import { invoke, isTauri } from '@tauri-apps/api/core';

let session: Promise<{ token: string; root: string }> | null = null;
function connect() {
  if (!session) session = browserRequest('session', {}).then(value => {
    const result = value as { token: string; root: string };
    if (!result || typeof result.token !== 'string' || !/^[a-f0-9]{64}$/.test(result.token) || typeof result.root !== 'string') throw new Error('Invalid local filespace session');
    return result;
  }).catch(error => { session = null; throw error; });
  return session;
}
async function browserRequest(action: string, input: Record<string, unknown>, retry = true): Promise<unknown> {
  const identity = action === 'session' ? null : await connect();
  const response = await fetch(`/__bifang/workspaces/${action}`, { method: 'POST', cache: 'no-store', credentials: 'omit',
    headers: { 'Content-Type': 'application/json', 'X-Bifang-Workspace-Client': 'preview', ...(identity ? { 'X-Bifang-Workspace-Token': identity.token } : {}) }, body: JSON.stringify(input) });
  if (response.status === 401 && retry && action !== 'session') { session = null; return browserRequest(action, input, false); }
  let result;
  try { result = await response.json(); } catch { throw new Error('Local filespace access requires the Bifang development server or desktop app.'); }
  if (!response.ok) throw new Error(typeof result?.error === 'string' ? result.error : 'Workspace operation failed');
  return result;
}
function resolved(value: unknown): string {
  if (!value || typeof (value as { path: unknown }).path !== 'string') throw new Error('Invalid workspace response');
  return (value as { path: string }).path;
}
export const nativeWorkspace = () => isTauri();
export async function resolveWorkspace(path: string): Promise<string> {
  return isTauri() ? invoke<string>('resolve_workspace_path', { path }) : resolved(await browserRequest('resolve', { path }));
}
export async function createWorkspace(parent: string, name: string): Promise<string> {
  return isTauri() ? invoke<string>('create_workspace', { parent, name }) : resolved(await browserRequest('create', { parent, name }));
}
export async function workspaceTree(path: string): Promise<string> {
  return isTauri() ? invoke<string>('get_file_tree', { path }) : JSON.stringify(await browserRequest('tree', { path }));
}
export async function workspaceDirectories(path?: string): Promise<{ root: string; path: string; directories: { name: string; path: string }[] }> {
  const identity = await connect();
  return browserRequest('directories', { path: path || identity.root }) as Promise<{ root: string; path: string; directories: { name: string; path: string }[] }>;
}
