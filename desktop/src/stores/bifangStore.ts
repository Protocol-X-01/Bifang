import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import type { SessionMessage } from '../api/conversations';
import { rememberFilespace, type Filespace } from '../api/filespaces';

let cacheWarning = false;
export const sessionCacheWarning = () => cacheWarning;
const warnCache = () => {
  cacheWarning = true;
  window.dispatchEvent(new Event('bifang-cache-warning'));
};
const sessionStorage = createJSONStorage(() => ({
  getItem: (key: string) => {
    try { return localStorage.getItem(key); } catch { warnCache(); return null; }
  },
  setItem: (key: string, value: string) => {
    try { localStorage.setItem(key, value); } catch { warnCache(); }
  },
  removeItem: (key: string) => {
    try { localStorage.removeItem(key); } catch { warnCache(); }
  },
}));

interface WorkspaceState {
  workspacePath: string | null;
  activeWorkspacePath: string | null;
  filespaces: Filespace[];
  forgetWorkspace: (path: string) => void;
  setWorkspace: (path: string) => void;
  setActiveWorkspace: (path: string | null) => void;
  clearWorkspace: () => void;
}

interface SessionState {
  sessionId: string | null;
  messages: SessionMessage[];
  busy: boolean;
  setBusy: (busy: boolean) => void;
  replaceConversation: (sessionId: string, messages: SessionMessage[]) => void;
  setSessionId: (sessionId: string | null) => void;
  addMessage: (message: Omit<SessionMessage, 'timestamp' | 'id'>) => void;
  clearMessages: () => void;
}

interface SettingsState {
  theme: 'light' | 'dark' | 'system';
  autoStartServer: boolean;
  defaultProvider: string;
  setTheme: (theme: 'light' | 'dark' | 'system') => void;
  setAutoStartServer: (value: boolean) => void;
  setDefaultProvider: (provider: string) => void;
}

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      workspacePath: null,
      activeWorkspacePath: null,
      filespaces: [],
      setWorkspace: (path: string) => set(state => ({ workspacePath: path, activeWorkspacePath: path, filespaces: rememberFilespace(state.filespaces, path) })),
      forgetWorkspace: path => set(state => ({ filespaces: state.filespaces.filter(space => space.path !== path) })),
      setActiveWorkspace: (path) => set({ activeWorkspacePath: path }),
      clearWorkspace: () => set({ workspacePath: null, activeWorkspacePath: null }),
    }),
    { name: 'bifang-workspace', storage: sessionStorage }
  )
);

export const useSessionStore = create<SessionState>()(
  persist(
    (set) => ({
      sessionId: null,
      messages: [],
      busy: false,
      setBusy: (busy) => set({ busy }),
      replaceConversation: (sessionId, messages) => set({ sessionId, messages }),
      setSessionId: (sessionId) => set({ sessionId }),
      addMessage: (message) =>
        set((state) => ({
          messages: [...state.messages, { ...message, id: crypto.randomUUID(), timestamp: Date.now() }],
        })),
      clearMessages: () => set({ messages: [] }),
    }),
    { name: 'bifang-session', storage: sessionStorage, partialize: ({ sessionId, messages }) => ({ sessionId, messages }) }
  )
);

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      theme: 'system',
      autoStartServer: true,
      defaultProvider: 'nvidia',
      setTheme: (theme) => set({ theme }),
      setAutoStartServer: (value) => set({ autoStartServer: value }),
      setDefaultProvider: (provider) => set({ defaultProvider: provider }),
    }),
    { name: 'bifang-settings' }
  )
);

// Combined hook for easy access
export const useBifangStore = () => ({
  workspace: useWorkspaceStore(),
  session: useSessionStore(),
  settings: useSettingsStore(),
});
