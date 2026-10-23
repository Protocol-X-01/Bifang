import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface WorkspaceState {
  workspacePath: string | null;
  activeWorkspacePath: string | null;
  setWorkspace: (path: string) => void;
  setActiveWorkspace: (path: string | null) => void;
  clearWorkspace: () => void;
}

interface SessionState {
  sessionId: string | null;
  messages: Array<{ role: 'user' | 'assistant' | 'tool' | 'system'; content: string; timestamp: number }>;
  setSessionId: (sessionId: string | null) => void;
  addMessage: (message: { role: 'user' | 'assistant' | 'tool' | 'system'; content: string }) => void;
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
      setWorkspace: (path: string) => set({ workspacePath: path, activeWorkspacePath: path }),
      setActiveWorkspace: (path) => set({ activeWorkspacePath: path }),
      clearWorkspace: () => set({ workspacePath: null }),
    }),
    { name: 'bifang-workspace' }
  )
);

export const useSessionStore = create<SessionState>()(
  persist(
    (set) => ({
      sessionId: null,
      messages: [],
      setSessionId: (sessionId) => set({ sessionId }),
      addMessage: (message) =>
        set((state) => ({
          messages: [...state.messages, { ...message, timestamp: Date.now() }],
        })),
      clearMessages: () => set({ messages: [] }),
    }),
    { name: 'bifang-session' }
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
