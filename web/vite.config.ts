import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // Same-origin in the browser: the dev server proxies /api so session and CSRF cookies work
  // exactly as they will behind the production reverse proxy.
  const apiTarget = env.API_URL ?? 'http://127.0.0.1:8000'

  return {
    plugins: [vue(), tailwindcss()],
    resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
    server: {
      port: Number(env.PORT ?? 5173),
      strictPort: true,
      proxy: { '/api': { target: apiTarget }, '/healthz': { target: apiTarget } },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.ts'],
      coverage: {
        provider: 'v8',
        include: ['src/**/*.{ts,vue}'],
        exclude: ['src/**/*.test.ts', 'src/test/**', 'src/**/*.d.ts', 'src/app/main.ts'],
        thresholds: { lines: 70, functions: 70, branches: 70, statements: 70 },
      },
    },
  }
})
