/** RFC 9457 problem details as sent by the API (standards section 4). */
export class ApiProblem extends Error {
  readonly status: number
  readonly code: string
  readonly detail: string
  readonly violations: ReadonlyArray<Record<string, string>>

  constructor(init: {
    status: number
    code: string
    title: string
    detail?: string
    violations?: ReadonlyArray<Record<string, string>>
  }) {
    super(init.title)
    this.name = 'ApiProblem'
    this.status = init.status
    this.code = init.code
    this.detail = init.detail ?? ''
    this.violations = init.violations ?? []
  }
}

export function toProblem(error: unknown, response: Response): ApiProblem {
  const body = (typeof error === 'object' && error !== null ? error : {}) as Record<string, unknown>
  const text = (value: unknown) => (typeof value === 'string' ? value : undefined)
  return new ApiProblem({
    status: response.status,
    code: text(body.code) ?? `http.${response.status}`,
    title: text(body.title) ?? response.statusText ?? 'Request failed',
    detail: text(body.detail),
    violations: Array.isArray(body.violations)
      ? (body.violations as Array<Record<string, string>>)
      : [],
  })
}

/** Something a person can read for any failure. API problems carry their own explanation; other
 * errors (a dropped connection, a bug) get a plain fallback that never shows internals. */
export function problemMessage(
  error: unknown,
  fallback = 'Something went wrong. Try again.',
): string {
  if (error instanceof ApiProblem) return error.detail || error.message
  return fallback
}
