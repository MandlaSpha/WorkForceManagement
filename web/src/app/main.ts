import { VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import { initTelemetry } from '@/shared/telemetry'

import './styles/index.css'
import App from './App.vue'
import { queryClientConfig } from './query'
import { createAppRouter } from './router'

// Start tracing before anything calls the API, so the very first request is part of a trace.
if (import.meta.env.VITE_OTEL_ENABLED === '1') {
  initTelemetry({ sampleRatio: Number(import.meta.env.VITE_OTEL_SAMPLE_RATIO ?? 1) })
}

const app = createApp(App)
app.use(createPinia())
app.use(VueQueryPlugin, { queryClientConfig: queryClientConfig() })
app.use(createAppRouter())
app.mount('#app')
