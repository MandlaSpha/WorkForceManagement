import type { QueryClient, QueryKey } from '@tanstack/vue-query'

/**
 * Make everything under `keys` fetch again after a write, even a list that is still on its FIRST
 * fetch.
 *
 * A plain `invalidateQueries` does not start a new fetch for a query that is already fetching and
 * has no data yet: it waits for the one in flight. If that request left before the write was
 * saved, it brings back the old list and the new row never appears. This happens when someone
 * adds a person a moment after opening the page, and more often on a slow connection. Cancelling
 * first drops the old request, so the refetch is a new one that sees the write.
 */
export async function refreshQueries(client: QueryClient, ...keys: QueryKey[]): Promise<void> {
  await Promise.all(
    keys.map(async (queryKey) => {
      await client.cancelQueries({ queryKey })
      await client.invalidateQueries({ queryKey })
    }),
  )
}
