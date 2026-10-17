import { afterEach, describe, expect, it, vi } from 'vitest'

import { uploadStates } from './attendance'

afterEach(() => {
  vi.restoreAllMocks()
  document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
})

describe('uploadStates', () => {
  it('posts the file as multipart form data with the CSRF token', async () => {
    // Failure caught: a JSON body (the server cannot read the file) or a missing CSRF token.
    document.cookie = 'csrftoken=token-from-sign-in'
    const seen: Request[] = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      seen.push((input as Request).clone())
      return new Response(JSON.stringify({ id: 1, fileName: 'states.csv' }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      })
    })

    await uploadStates(new File(['login,state,from,to'], 'states.csv'))

    const request = seen[0]
    expect(request?.method).toBe('POST')
    expect(new URL(request?.url ?? '').pathname).toBe('/api/v1/attendance/imports')
    expect(request?.headers.get('Content-Type')).toMatch(/^multipart\/form-data; boundary=/)
    expect(request?.headers.get('X-CSRFToken')).toBe('token-from-sign-in')
    expect(await request?.text()).toContain('name="file"')
  })
})
