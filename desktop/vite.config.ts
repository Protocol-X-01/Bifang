import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { localWorkspaces } from './dev/localWorkspaces';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), localWorkspaces()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 1420,
    strictPort: true,
    hmr: {
      port: 1421,
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
