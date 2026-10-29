import { invoke, isTauri } from '@tauri-apps/api/core';

interface ServerConnection {
  version: number;
  origin: string;
  api_key: string;
}

export async function localFetch(path: string, options: RequestInit = {}): Promise<Response> {
  if (!path.startsWith('/') || path.startsWith('//') || /[\\\r\n]/.test(path)) {
    throw new Error('Invalid local API path');
  }
  options.signal?.throwIfAborted();
  let origin = 'http://127.0.0.1:8000';
  const headers = new Headers(options.headers);
  if (isTauri()) {
    const connection = await invoke<ServerConnection>('get_server_connection');
    const match = /^http:\/\/127\.0\.0\.1:([1-9][0-9]{0,4})$/.exec(connection.origin);
    if (connection.version !== 1 || !match || Number(match[1]) > 65535 || !/^[a-f0-9]{64}$/.test(connection.api_key)) {
      throw new Error('Invalid local server connection');
    }
    origin = connection.origin;
    headers.set('X-API-Key', connection.api_key);
  }
  options.signal?.throwIfAborted();
  return fetch(origin + path, { ...options, headers, redirect: 'error' });
}
