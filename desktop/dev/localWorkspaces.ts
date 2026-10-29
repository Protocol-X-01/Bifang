import { randomBytes, timingSafeEqual } from 'node:crypto';
import { mkdir, readdir, realpath } from 'node:fs/promises';
import { homedir } from 'node:os';
import path from 'node:path';
import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Plugin } from 'vite';

const prefix = '/__bifang/workspaces/';
const loopback = (address: string | undefined) => ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(address || '');

export function createWorkspaceMiddleware(root: string) {
  const token = randomBytes(32).toString('hex');
  let rootPath: Promise<string> | undefined;
  const boundaryPath = () => rootPath ||= realpath(root);
  const resolve = async (value: unknown) => {
    if (typeof value !== 'string' || value.length > 4096 || !path.isAbsolute(value)) throw new Error('Enter an existing absolute directory path.');
    const canonical = await realpath(value), boundary = await boundaryPath();
    const relative = path.relative(boundary, canonical);
    if (relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) throw new Error('Choose a directory within the configured filespace root.');
    await readdir(canonical);
    return canonical;
  };
  return (request: IncomingMessage, response: ServerResponse, next: () => void) => {
    if (!request.url?.startsWith(prefix)) { next(); return; }
    response.setHeader('Cache-Control', 'no-store');
    response.setHeader('Cross-Origin-Resource-Policy', 'same-origin');
    response.setHeader('X-Content-Type-Options', 'nosniff');
    response.setHeader('Content-Type', 'application/json');
    const reply = (status: number, value: unknown) => { response.statusCode = status; response.end(JSON.stringify(value)); };
    const port = request.socket.localPort;
    const allowedHosts = [`127.0.0.1:${port}`, `localhost:${port}`, `[::1]:${port}`];
    if (!loopback(request.socket.localAddress) || !loopback(request.socket.remoteAddress) ||
        !allowedHosts.includes(request.headers.host || '') || request.headers.origin !== `http://${request.headers.host}` ||
        request.method !== 'POST' || request.headers['x-bifang-workspace-client'] !== 'preview' ||
        request.headers['content-type'] !== 'application/json') {
      reply(403, { error: 'Local same-origin workspace access required.' }); return;
    }
    const action = request.url.slice(prefix.length);
    if (!['session', 'create', 'resolve', 'tree', 'directories'].includes(action)) { reply(404, { error: 'Unknown workspace operation.' }); return; }
    const supplied = request.headers['x-bifang-workspace-token'];
    if (action !== 'session' && (typeof supplied !== 'string' || !/^[a-f0-9]{64}$/.test(supplied) ||
        !timingSafeEqual(Buffer.from(supplied), Buffer.from(token)))) {
      reply(401, { error: 'Reconnect the local filespace session.' }); return;
    }
    void (async () => {
      let size = 0;
      const chunks: Buffer[] = [];
      for await (const chunk of request) {
        size += chunk.length;
        if (size > 8192) { reply(413, { error: 'Workspace request is too large.' }); return; }
        chunks.push(Buffer.from(chunk));
      }
      const input = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid workspace request.');
      const fields = action === 'create' ? ['parent', 'name'] : action === 'session' ? [] : ['path'];
      if (Object.keys(input).sort().join(',') !== fields.sort().join(',')) throw new Error('Invalid workspace request fields.');
      if (action === 'session') { reply(200, { token, root: await boundaryPath() }); return; }
      if (action === 'create') {
        const name = input.name;
        if (typeof name !== 'string' || !name || Buffer.byteLength(name) > 120 || name.trim() !== name ||
            name.startsWith('.') || name.endsWith('.') || /[\x00-\x1f\x7f/\\:<>"|?*]/.test(name) ||
            /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name)) throw new Error('Choose a valid new folder name without path separators.');
        const parent = await resolve(input.parent), created = path.join(parent, name);
        await mkdir(created, { recursive: false });
        reply(201, { path: created }); return;
      }
      const directory = await resolve(input.path);
      if (action === 'resolve') { reply(200, { path: directory }); return; }
      if (action === 'directories') {
        const entries = await readdir(directory, { withFileTypes: true });
        reply(200, { root: await boundaryPath(), path: directory, directories: entries.filter(entry => entry.isDirectory() && !entry.name.startsWith('.')).slice(0, 500).map(entry => ({ name: entry.name, path: path.join(directory, entry.name) })) });
        return;
      }
      let count = 0;
      const tree = async (current: string, depth: number): Promise<unknown[]> => {
        if (depth > 8) return [];
        const result = [];
        for (const entry of await readdir(current, { withFileTypes: true })) {
          if (entry.isSymbolicLink() || entry.name.startsWith('.') || ['node_modules', 'target', 'dist', '__pycache__'].includes(entry.name)) continue;
          if (++count > 2000) throw new Error('Choose a smaller workspace for the browser file tree.');
          const absolute = path.join(current, entry.name);
          result.push({ name: entry.name, path: path.relative(directory, absolute).split(path.sep).join('/'), type: entry.isDirectory() ? 'directory' : 'file', ...(entry.isDirectory() ? { children: await tree(absolute, depth + 1) } : {}) });
        }
        return result;
      };
      reply(200, await tree(directory, 0));
    })().catch(error => {
      const code = error?.code;
      const message = code === 'EEXIST' ? 'A file or folder already uses that name.' : code === 'ENOENT' ? 'The directory does not exist.' : code === 'EACCES' ? 'This directory is not writable or accessible.' : 'Could not complete this workspace operation. Check its name, path and filespace root.';
      if (!response.writableEnded) reply(400, { error: message });
    });
  };
}

export function localWorkspaces(): Plugin {
  return { name: 'bifang-local-workspaces', apply: 'serve', configureServer(server) {
    server.middlewares.use(createWorkspaceMiddleware(process.env.BIFANG_BROWSER_WORKSPACE_ROOT || homedir()));
  } };
}
