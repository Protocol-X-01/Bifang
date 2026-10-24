import type { RoutingReceipt } from './models';

export interface SessionMessage {
  id?: string;
  role: 'user' | 'assistant' | 'tool' | 'system';
  content: string;
  timestamp: number;
  routing?: RoutingReceipt[];
}

export interface SavedConversation {
  conversation_id: string;
  updated_at: number;
  turn_count: number;
}

export interface HistoryTurn {
  turn_id: string;
  user_message: string;
  assistant_response: string;
  timestamp: number;
  status: string;
  routing?: RoutingReceipt[];
}

export function parseRoutingReceipts(value: unknown): RoutingReceipt[] {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.some((item) => !item ||
    ['provider', 'requested_model', 'role', 'task_type'].some((key) => typeof item[key] !== 'string') ||
    !(item.reported_model === null || typeof item.reported_model === 'string') ||
    !item.usage || typeof item.usage !== 'object' || Array.isArray(item.usage) ||
    Object.values(item.usage).some((count) => typeof count !== 'number' || !Number.isSafeInteger(count) || count < 0))) {
    throw new Error('The server returned invalid model receipts.');
  }
  return value;
}

const API = 'http://127.0.0.1:8000';
const finiteTime = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 8.64e12;

export function parseConversations(value: unknown): SavedConversation[] {
  if (!Array.isArray(value) || value.some((item) => !item || typeof item.conversation_id !== 'string' ||
    !item.conversation_id || !finiteTime(item.updated_at) || !Number.isInteger(item.turn_count) || item.turn_count < 0)) {
    throw new Error('The server returned an invalid conversation list.');
  }
  return value;
}

export function parseHistory(value: unknown): HistoryTurn[] {
  if (!Array.isArray(value) || value.some((item) => !item || typeof item.turn_id !== 'string' || !item.turn_id ||
    typeof item.user_message !== 'string' || typeof item.assistant_response !== 'string' ||
    !finiteTime(item.timestamp) || typeof item.status !== 'string')) {
    throw new Error('The server returned invalid conversation history.');
  }
  value.forEach((turn) => parseRoutingReceipts(turn.routing));
  return value;
}

export function historyMessages(turns: HistoryTurn[]): SessionMessage[] {
  return turns.flatMap((turn): SessionMessage[] => [
    { id: `${turn.turn_id}:user`, role: 'user', content: turn.user_message, timestamp: turn.timestamp * 1000 },
    ...(turn.assistant_response ? [{ id: `${turn.turn_id}:assistant`, role: 'assistant' as const,
      content: turn.assistant_response, timestamp: turn.timestamp * 1000, routing: turn.routing || [] }] : []),
    ...(turn.status !== 'completed' ? [{ id: `${turn.turn_id}:status`, role: 'system' as const,
      content: `Earlier turn: ${turn.status}. Its tools will not be replayed.`, timestamp: turn.timestamp * 1000 }] : []),
  ]);
}

export async function savedConversations(workspace: string, offset = 0, signal?: AbortSignal): Promise<SavedConversation[]> {
  const query = new URLSearchParams({ workspace, limit: '20', offset: String(offset) });
  const response = await fetch(`${API}/conversations?${query}`, { signal });
  if (!response.ok) throw new Error(`Could not load saved conversations (HTTP ${response.status}).`);
  return parseConversations(await response.json());
}

export async function sessionHistory(sessionId: string): Promise<SessionMessage[]> {
  const response = await fetch(`${API}/sessions/${encodeURIComponent(sessionId)}/history`);
  if (!response.ok) throw new Error(`Could not restore conversation history (HTTP ${response.status}).`);
  return historyMessages(parseHistory(await response.json()));
}
