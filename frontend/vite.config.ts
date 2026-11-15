import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const BACKEND = process.env.ATLAS_BACKEND || 'http://127.0.0.1:8765';

// The built UI is served by the Python backend from src/combustion_atlas/app/web at "/".
export default defineConfig({
  base: '/',
  plugins: [react()],
  build: {
    outDir: '../src/combustion_atlas/app/web',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    strictPort: true,
    // The backend only accepts same-origin POSTs, so the proxy presents itself as the backend.
    proxy: {
      '/api': {
        target: BACKEND,
        changeOrigin: true,
        configure: proxy => {
          proxy.on('proxyReq', req => { if (req.getHeader('origin')) req.setHeader('origin', BACKEND); });
        },
      },
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
