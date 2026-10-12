import { http, HttpResponse } from 'msw'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { api } from '@/shared/api'
import { shutdownTelemetry } from '@/shared/telemetry'
import { server } from '@/test/server'
import { everythingRecorded, fetchSpans, startTelemetry, waitForFetchSpans } from '@/test/spans'

import { useSessionStore } from './store'

beforeEach(() => setActivePinia(createPinia()))
afterEach(async () => {
  await shutdownTelemetry()
})

describe('session and tracing', () => {
  it('never records credentials, names or the CSRF token from a real sign-in', async () => {
    startTelemetry()
    server.use(
      http.post('*/api/v1/auth/login', () =>
        HttpResponse.json({ username: 'pat.private', displayName: 'Pat Secret', role: 'planner' }),
      ),
    )

    await useSessionStore().signIn('pat.private', 'correct-horse-battery')
    await waitForFetchSpans(2) // the CSRF fetch and the login

    const recorded = everythingRecorded()
    for (const secret of [
      'pat.private',
      'Pat Secret',
      'correct-horse-battery',
      'test-csrf-token',
    ]) {
      expect(recorded).not.toContain(secret)
    }
    expect(fetchSpans().at(-1)?.attributes['wfm.role']).toBeDefined()
  })

  it('labels later spans with the role of whoever signed in, and clears it on sign-out', async () => {
    startTelemetry()
    server.use(
      http.post('*/api/v1/auth/login', () =>
        HttpResponse.json({ username: 'x', displayName: 'X', role: 'lead' }),
      ),
    )
    const session = useSessionStore()
    await session.signIn('x', 'y')

    await api.GET('/api/v1/auth/me')
    await waitForFetchSpans(3)
    expect(fetchSpans('GET').at(-1)?.attributes['wfm.role']).toBe('lead')

    await session.signOut()
    await api.GET('/api/v1/auth/me')
    await waitForFetchSpans(5)
    expect(fetchSpans('GET').at(-1)?.attributes['wfm.role']).toBe('anonymous')
  })
})
