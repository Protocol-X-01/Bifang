export interface ModelSelection {
  routing_mode: 'pinned' | 'auto';
  model?: string;
}

export interface RoutingReceipt {
  provider: string;
  requested_model: string;
  reported_model: string | null;
  role: string;
  task_type: string;
  usage: Record<string, number>;
}

export interface ModelCatalog {
  provider: string;
  models: string[];
  configured_model: string | null;
  configured_mode: 'pinned' | 'auto';
  auto_available: boolean;
  roles: Record<string, string>;
}

export function parseModelCatalog(value: unknown): ModelCatalog {
  const catalog = value as ModelCatalog | null;
  if (!catalog || typeof catalog.provider !== 'string' || !Array.isArray(catalog.models) ||
    catalog.models.some((model) => typeof model !== 'string' || !model) ||
    typeof catalog.auto_available !== 'boolean' ||
    !['pinned', 'auto'].includes(catalog.configured_mode) ||
    !(catalog.configured_model === null || typeof catalog.configured_model === 'string') ||
    !catalog.roles || typeof catalog.roles !== 'object' || Array.isArray(catalog.roles) ||
    Object.values(catalog.roles).some((model) => typeof model !== 'string')) {
    throw new Error('The server returned an invalid model catalog.');
  }
  return catalog;
}

export function selectionValue(selection: ModelSelection | null): string {
  return selection?.routing_mode === 'auto' ? 'auto' : selection?.model ? `model:${selection.model}` : 'configured';
}

export function selectionFor(value: string): ModelSelection | null {
  if (value === 'configured') return null;
  if (value === 'auto') return { routing_mode: 'auto' };
  if (value.startsWith('model:') && value.length > 6) return { routing_mode: 'pinned', model: value.slice(6) };
  throw new Error('Invalid model selection.');
}
