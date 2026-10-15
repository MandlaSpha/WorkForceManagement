import { vi } from 'vitest'

import { backend } from './fake-backend'

/** Answer the employee-file upload by hand and let every other request through to the fake backend.
 * The upload is a multipart body, which the mock server cannot read in this environment, so the
 * request is seen where it is made (the same approach the work-item tests take). Whether it was
 * a check (`dry_run=true`) or the real import is recorded in `backend.employeeImports`, with the
 * CSRF token; the file's name and bytes are not carried into a multipart body by the test
 * environment, so they are covered end to end instead. */
export function interceptEmployeeImport(): void {
  const real = globalThis.fetch
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const request = new Request(input as RequestInfo, init)
    const url = new URL(request.url)
    if (url.pathname !== '/api/v1/scheduling/employees/import') return real(input, init)

    const csrf = request.headers.get('X-CSRFToken')
    const raw = await request.text()
    const dryRun = url.searchParams.get('dry_run') !== 'false'
    backend.employeeImports.push({
      dryRun,
      multipart: request.headers.get('Content-Type')?.startsWith('multipart/form-data') ?? false,
      filePart: /name="file"/.test(raw),
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
    return Response.json({ ...(backend.employeeImport ?? {}), dryRun })
  })
}
