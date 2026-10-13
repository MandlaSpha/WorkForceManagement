import type { QueryClientConfig } from '@tanstack/vue-query'

/** One place for how server data is cached. Tests pass `retry: false` so failures show at once. */
export function queryClientConfig(retry: number | false = 1): QueryClientConfig {
  return { defaultOptions: { queries: { retry, refetchOnWindowFocus: false } } }
}
