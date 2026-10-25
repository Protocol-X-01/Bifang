import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  resolve: { dedupe: ['react', 'react-dom'] },
  server: { host: process.env.TAURI_DEV_HOST || '127.0.0.1', port: 1435, strictPort: true },
  build: { outDir: 'dist', emptyOutDir: true },
});
