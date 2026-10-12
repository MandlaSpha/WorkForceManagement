import createClient, { type Middleware } from 'openapi-fetch'

import type { paths } from './schema'

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])
/** Endpoints where a 401 is an expected answer, not an expired session. */
const AUTH_PROBES = ['/api/v1/auth/login', '/api/v1/auth/csrf', '/api/v1/auth/me']

export function readCsrfToken(cookie: string = document.cookie): string | null {
  const match = cookie.split('; ').find((c) => c.startsWith('csrftoken='))
  return match ? decodeURIComponent(match.slice('csrftoken='.length)) : null
}

let onUnauthorised: (() => void) | null = null

/** The session store registers here so any 401 on a normal call ends the session. */
export function setUnauthorisedHandler(handler: (() => void) | null): void {
  onUnauthorised = handler
}

const middleware: Middleware = {
  onRequest({ request }) {
    if (!SAFE_METHODS.has(request.method)) {
      const token = readCsrfToken()
      if (token) request.headers.set('X-CSRFToken', token)
    }
    return request
  },
  onResponse({ request, response }) {
    const path = new URL(request.url).pathname
    if (response.status === 401 && !AUTH_PROBES.includes(path)) onUnauthorised?.()
    return response
  },
}

/** Typed client generated from the API's OpenAPI schema (`just api-types`). Same-origin: the dev
 * server proxies /api, production sits behind one reverse proxy. */
export const api = createClient<paths>({
  baseUrl: typeof window === 'undefined' ? '' : window.location.origin,
  credentials: 'same-origin',
  // Resolve fetch per call, not at import time: openapi-fetch otherwise keeps the fetch that
  // existed when the client was created, which also hides any later fetch instrumentation
  // (test mocks now, OpenTelemetry's fetch tracing later).
  fetch: (request: Request) => globalThis.fetch(request),
})
api.use(middleware)
