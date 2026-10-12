import { createPinia, setActivePinia } from 'pinia'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import { api, ApiProblem } from '@/shared/api'
import { backend } from '@/test/fake-backend'
import { server } from '@/test/server'

import { useSessionStore } from './store'

beforeEach(() => setActivePinia(createPinia()))

describe('load', () => {
  it('is anonymous when nobody is signed in', async () => {
    const session = useSessionStore()
    await session.load()
    expect(session.status).toBe('anonymous')
    expect(session.user).toBeNull()
  })

  it('restores an existing session', async () => {
    backend.signedIn = { username: 'planner', displayName: 'Pat Planner', role: 'planner' }
    const session = useSessionStore()
    await session.load()
    expect(session.status).toBe('authenticated')
    expect(session.user?.role).toBe('planner')
  })

  it('treats an unreachable API as signed out instead of crashing the app', async () => {
    server.use(http.get('*/api/v1/auth/me', () => HttpResponse.error()))
    const session = useSessionStore()
    await session.load()
    expect(session.status).toBe('anonymous')
  })
})

describe('signIn', () => {
  it('fetches a CSRF token first and sends it with the login', async () => {
    const session = useSessionStore()
    await session.signIn('planner', 'correct-horse-battery')

    const paths = backend.requests.map((r) => `${r.method} ${r.path}`)
    expect(paths).toEqual(['GET /api/v1/auth/csrf', 'POST /api/v1/auth/login'])
    expect(backend.requests[1]?.csrf).toBe('test-csrf-token')
    expect(session.user).toMatchObject({ username: 'planner', role: 'planner' })
    expect(session.status).toBe('authenticated')
  })

  it('throws the API problem on bad credentials and stays signed out', async () => {
    const session = useSessionStore()
    const attempt = session.signIn('planner', 'wrong')

    await expect(attempt).rejects.toBeInstanceOf(ApiProblem)
    await expect(attempt).rejects.toMatchObject({ code: 'auth.invalid_credentials', status: 401 })
    expect(session.user).toBeNull()
  })

  it('clears the "signed out for inactivity" notice after signing in again', async () => {
    const session = useSessionStore()
    await session.signIn('planner', 'correct-horse-battery')
    backend.signedIn = null // server-side idle timeout
    await api.POST('/api/v1/auth/logout') // any normal call now returns 401
    expect(session.expired).toBe(true)

    await session.signIn('planner', 'correct-horse-battery')

    expect(session.expired).toBe(false)
  })

  it('refuses a role the UI does not know rather than guessing', async () => {
    server.use(
      http.post('*/api/v1/auth/login', () =>
        HttpResponse.json({ username: 'x', displayName: 'X', role: 'superuser' }),
      ),
    )
    const session = useSessionStore()
    await expect(session.signIn('x', 'y')).rejects.toThrow(/Unknown role/)
    expect(session.user).toBeNull()
  })
})

describe('signOut', () => {
  it('ends the session', async () => {
    const session = useSessionStore()
    await session.signIn('planner', 'correct-horse-battery')

    await session.signOut()

    expect(session.status).toBe('anonymous')
    expect(session.user).toBeNull()
    expect(backend.signedIn).toBeNull()
  })

  it('still ends the local session if the server already forgot it (401)', async () => {
    const session = useSessionStore()
    await session.signIn('planner', 'correct-horse-battery')
    backend.signedIn = null // idle timeout on the server

    await session.signOut()

    expect(session.status).toBe('anonymous')
  })
})

describe('idle expiry', () => {
  it('a 401 on a normal call signs the user out and says why', async () => {
    const session = useSessionStore()
    await session.signIn('planner', 'correct-horse-battery')
    backend.signedIn = null

    // any normal call that returns 401 triggers the registered handler
    await api.POST('/api/v1/auth/logout')

    expect(session.status).toBe('anonymous')
    expect(session.expired).toBe(true)
  })
})
