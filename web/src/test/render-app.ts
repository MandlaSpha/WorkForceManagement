import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { render } from '@testing-library/vue'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'

import App from '@/app/App.vue'
import { queryClientConfig } from '@/app/query'
import { createAppRouter } from '@/app/router'

/** Mount the whole app (real router, guards, stores) at `path`, talking to the fake backend. */
export async function renderApp(path = '/') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createAppRouter(createMemoryHistory())
  // Built here (same defaults as production, but no retries) so tests can look inside the cache.
  const queryClient = new QueryClient(queryClientConfig(false))
  await router.push(path)
  await router.isReady()
  const view = render(App, {
    global: { plugins: [pinia, router, [VueQueryPlugin, { queryClient }]] },
  })
  return { ...view, router, pinia, queryClient }
}
