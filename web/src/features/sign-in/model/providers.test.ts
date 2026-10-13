import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { server } from '@/test/server'

import { fetchProviders, LOCAL_ONLY } from './providers'

describe('fetchProviders', () => {
  it('maps what the API offers', async () => {
    server.use(
      http.get('*/api/v1/auth/providers', () =>
        HttpResponse.json([
          {
            id: 'entra',
            kind: 'oidc',
            label: 'Microsoft',
            flow: 'redirect',
            startUrl: '/api/v1/auth/sso/entra/start',
            restricted: false,
          },
          { id: 'corp', kind: 'ldap', label: 'Company directory', flow: 'credentials' },
        ]),
      ),
    )

    const providers = await fetchProviders()

    expect(providers).toEqual([
      {
        id: 'entra',
        kind: 'oidc',
        label: 'Microsoft',
        flow: 'redirect',
        startUrl: '/api/v1/auth/sso/entra/start',
        restricted: false,
      },
      {
        id: 'corp',
        kind: 'ldap',
        label: 'Company directory',
        flow: 'credentials',
        startUrl: null,
        restricted: false,
      },
    ])
  })

  it('treats an unknown flow as a credentials form rather than guessing a redirect', async () => {
    server.use(
      http.get('*/api/v1/auth/providers', () =>
        HttpResponse.json([{ id: 'x', kind: 'future', label: 'X', flow: 'telepathy' }]),
      ),
    )
    expect((await fetchProviders())[0]?.flow).toBe('credentials')
  })

  it.each([
    ['the API is unreachable', () => HttpResponse.error()],
    ['the API errors', () => new HttpResponse(null, { status: 500 })],
    ['the API offers nothing', () => HttpResponse.json([])],
  ])('falls back to local sign-in when %s', async (_name, respond) => {
    server.use(http.get('*/api/v1/auth/providers', respond))
    expect(await fetchProviders()).toEqual(LOCAL_ONLY)
  })
})
