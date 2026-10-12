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

  // Browser spans go to the same origin too (/otlp/...), and are forwarded to our own OTLP/HTTP
  // collector, so telemetry never leaves our infrastructure and needs no CORS. In development the
  // collector is the Aspire dashboard, which wants its API key as a header.
  const otlpTarget = env.OTLP_HTTP_URL
  const otlpKey = /(?:^|,)x-otlp-api-key=([^,]+)/.exec(env.OTEL_EXPORTER_OTLP_HEADERS ?? '')?.[1]

  return {
    plugins: [vue(), tailwindcss()],
    resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
    server: {
      port: Number(env.PORT ?? 5173),
      strictPort: true,
      proxy: {
        '/api': { target: apiTarget },
        '/healthz': { target: apiTarget },
        ...(otlpTarget
          ? {
              '/otlp': {
                target: otlpTarget,
                rewrite: (path: string) => path.replace(/^\/otlp/, ''),
                headers: otlpKey ? { 'x-otlp-api-key': otlpKey } : {},
              },
            }
          : {}),
      },
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
