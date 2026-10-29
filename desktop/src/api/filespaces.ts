export interface Filespace { path: string; name: string; lastOpened: number }

export function rememberFilespace(existing: unknown, path: string, now = Date.now()): Filespace[] {
  const valid: Filespace[] = Array.isArray(existing) ? existing.filter(item => item && typeof item.path === 'string' && typeof item.name === 'string' && Number.isFinite(item.lastOpened)) : [];
  return [{ path, name: path.split(/[\\/]/).filter(Boolean).pop() || path, lastOpened: now }, ...valid.filter(item => item.path !== path)].slice(0, 20);
}
