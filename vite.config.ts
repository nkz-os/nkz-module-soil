import { defineConfig } from 'vite';
import { nkzModulePreset } from '@nekazari/module-builder';

export default defineConfig(
  nkzModulePreset({
    viteConfig: {
      // The preset pins NODE_ENV to production, which disables React's act() under vitest.
      define: process.env.VITEST ? { 'process.env.NODE_ENV': JSON.stringify('test') } : {},
      server: {
        port: 5004,
        proxy: {
          '/api': {
            target: process.env.VITE_PROXY_TARGET || 'http://localhost:8000',
            changeOrigin: true,
            secure: process.env.VITE_PROXY_TARGET?.startsWith('https') ?? false,
          },
        },
      },
    },
  }),
);
