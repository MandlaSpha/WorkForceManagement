import { vi } from 'vitest'

import { backend } from './fake-backend'

/** Answer the work-item upload by hand and let every other request through to the fake backend.
 * The upload is a multipart body, which the mock server cannot read in this environment, so the
 * request is seen where it is made (the same approach the call-data tests take). That it was multipart
 * with a `file` part, and the CSRF token, are recorded in `backend.writes` like any other write;
 * the file's name and bytes are checked end to end, because the test environment's File carries
 * neither into a multipart body. */
export function interceptWorkImport(): void {
  const real = globalThis.fetch
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const request = new Request(input as RequestInfo, init)
    if (new URL(request.url).pathname !== '/api/v1/service-desk/imports') return real(input, init)

    const csrf = request.headers.get('X-CSRFToken')
    const raw = await request.text()
    backend.writes.push({
      method: 'POST',
      path: '/api/v1/service-desk/imports',
      body: {
        filePart: /name="file"/.test(raw),
        multipart: request.headers.get('Content-Type')?.startsWith('multipart/form-data') ?? false,
      },
      csrf,
    })
    if (csrf !== 'test-csrf-token') {
      return Response.json(
        { code: 'auth.csrf', title: 'CSRF check failed', status: 403 },
        { status: 403 },
      )
    }
    const refusal = backend.nextProblem
    if (refusal) {
      backend.nextProblem = null
      return Response.json(refusal, {
        status: refusal.status,
        headers: { 'Content-Type': 'application/problem+json' },
      })
    }
    return Response.json(backend.workImport ?? {}, { status: 201 })
  })
}
