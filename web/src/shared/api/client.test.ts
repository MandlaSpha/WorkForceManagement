import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { server } from '@/test/server'

import { api, readCsrfToken, setUnauthorisedHandler } from './client'
import { toProblem } from './problem'

afterEach(() => setUnauthorisedHandler(null))

describe('readCsrfToken', () => {
  it('finds the token among other cookies', () => {
    expect(readCsrfToken('a=1; csrftoken=abc123; b=2')).toBe('abc123')
  })
  it('returns null when absent', () => {
    expect(readCsrfToken('a=1')).toBeNull()
  })
})

describe('CSRF header', () => {
  it('is added to unsafe methods from the cookie', async () => {
    document.cookie = 'csrftoken=tok-xyz'
    let sent: string | null = null
    server.use(
      http.post('*/api/v1/auth/logout', ({ request }) => {
        sent = request.headers.get('X-CSRFToken')
        return HttpResponse.json({ ok: true })
      }),
    )

    await api.POST('/api/v1/auth/logout')

    expect(sent).toBe('tok-xyz')
  })

  it('is not added to safe methods', async () => {
    document.cookie = 'csrftoken=tok-xyz'
    let sent: string | null = 'unset'
    server.use(
      http.get('*/api/v1/auth/me', ({ request }) => {
        sent = request.headers.get('X-CSRFToken')
        return HttpResponse.json({ username: 'u', displayName: 'U', role: 'planner' })
      }),
    )

    await api.GET('/api/v1/auth/me')

    expect(sent).toBeNull()
  })
})

describe('401 handling', () => {
  it('ends the session when a normal call comes back 401', async () => {
    const onUnauthorised = vi.fn()
    setUnauthorisedHandler(onUnauthorised)
    server.use(http.post('*/api/v1/auth/logout', () => new HttpResponse(null, { status: 401 })))

    await api.POST('/api/v1/auth/logout')

    expect(onUnauthorised).toHaveBeenCalledOnce()
  })

  it('does not treat a 401 from the sign-in probes as an expired session', async () => {
    const onUnauthorised = vi.fn()
    setUnauthorisedHandler(onUnauthorised)

    // fake backend answers /me with 401 when nobody is signed in
    await api.GET('/api/v1/auth/me')

    expect(onUnauthorised).not.toHaveBeenCalled()
  })
})

describe('toProblem', () => {
  it('maps an RFC 9457 body', () => {
    const response = new Response(null, { status: 422 })
    const problem = toProblem(
      { code: 'rule.rest_11h', title: 'Rest rule', detail: 'Needs 11h', violations: [{ a: 'b' }] },
      response,
    )
    expect(problem).toMatchObject({
      status: 422,
      code: 'rule.rest_11h',
      message: 'Rest rule',
      detail: 'Needs 11h',
      violations: [{ a: 'b' }],
    })
  })

  it('falls back to the HTTP status when the body is not a problem', () => {
    const problem = toProblem(undefined, new Response(null, { status: 500, statusText: 'Boom' }))
    expect(problem.code).toBe('http.500')
    expect(problem.message).toBe('Boom')
    expect(problem.violations).toEqual([])
  })
})
