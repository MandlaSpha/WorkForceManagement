import { QueryClient, QueryObserver } from '@tanstack/vue-query'
import { afterEach, describe, expect, it } from 'vitest'

import { refreshQueries } from './refresh'

const unsubscribe: Array<() => void> = []
afterEach(() => unsubscribe.splice(0).forEach((stop) => stop()))

/** A list on screen (something is watching it) whose first request is still on its way when the
 * write finishes: the first request will come back with the OLD list, any later one the new. */
function listWithSlowFirstRequest() {
  const client = new QueryClient()
  const state = { calls: 0, releaseFirst: (value: string[]): unknown => value }
  const observer = new QueryObserver(client, {
    queryKey: ['people'],
    queryFn: () => {
      state.calls += 1
      if (state.calls > 1) return Promise.resolve(['old', 'new'])
      return new Promise<string[]>((resolve) => (state.releaseFirst = resolve))
    },
  })
  unsubscribe.push(observer.subscribe(() => undefined)) // the page is showing it: fetch starts
  return { client, state }
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 20))

describe('refreshQueries', () => {
  it('shows the write even when the first request left before it was saved', async () => {
    const { client, state } = listWithSlowFirstRequest()

    await refreshQueries(client, ['people']) // the write has just finished
    state.releaseFirst(['old']) // and now the request that left before it comes back
    await settle()

    expect(state.calls).toBe(2) // a new request was made, after the write
    expect(client.getQueryData(['people'])).toEqual(['old', 'new'])
  })

  it('control: a plain invalidate waits for the old request and shows the old list', async () => {
    // This is why `refreshQueries` exists. If the library ever starts a new request here, the
    // helper is no longer needed and this test says so.
    const { client, state } = listWithSlowFirstRequest()

    const invalidated = client.invalidateQueries({ queryKey: ['people'] }) // waits for the old one
    state.releaseFirst(['old'])
    await invalidated
    await settle()

    expect(state.calls).toBe(1)
    expect(client.getQueryData(['people'])).toEqual(['old'])
  })

  it('leaves queries under other keys alone', async () => {
    const client = new QueryClient()
    await client.fetchQuery({ queryKey: ['mine'], queryFn: () => Promise.resolve(1) })
    await client.fetchQuery({ queryKey: ['other'], queryFn: () => Promise.resolve(2) })

    await refreshQueries(client, ['mine'])

    expect(client.getQueryState(['mine'])?.isInvalidated).toBe(true)
    expect(client.getQueryState(['other'])?.isInvalidated).toBe(false)
  })

  it('refreshes every key it is given', async () => {
    const client = new QueryClient()
    for (const key of ['a', 'b']) {
      await client.fetchQuery({ queryKey: [key], queryFn: () => Promise.resolve(key) })
    }

    await refreshQueries(client, ['a'], ['b'])

    expect(client.getQueryState(['a'])?.isInvalidated).toBe(true)
    expect(client.getQueryState(['b'])?.isInvalidated).toBe(true)
  })
})
