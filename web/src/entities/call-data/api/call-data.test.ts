import { afterEach, describe, expect, it, vi } from 'vitest'

import { importReport, kpiSummary } from '@/test/call-data-fixtures'

import { fetchKpis, uploadReport } from './call-data'

/** Answer every call with `body`, remembering the requests so a test can look at them. */
function fakeFetch(body: unknown, status = 200) {
  const seen: Request[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    seen.push((input as Request).clone())
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  return seen
}

afterEach(() => {
  vi.restoreAllMocks()
  document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
})

describe('uploadReport', () => {
  it('posts the file as multipart form data with the CSRF token', async () => {
    document.cookie = 'csrftoken=token-from-sign-in'
    const seen = fakeFetch(importReport(), 201)

    const report = await uploadReport(new File(['bytes'], 'may.xlsx'))

    expect(report.fileName).toBe('may.xlsx')
    const request = seen[0]
    expect(request?.method).toBe('POST')
    expect(new URL(request?.url ?? '').pathname).toBe('/api/v1/telephony/imports')
    // Without the boundary the server cannot read the file; without the token it refuses it.
    expect(request?.headers.get('Content-Type')).toMatch(/^multipart\/form-data; boundary=/)
    expect(request?.headers.get('X-CSRFToken')).toBe('token-from-sign-in')
    expect(await request?.text()).toContain('name="file"')
  })

  it('turns a refusal into an ApiProblem carrying the stable code', async () => {
    fakeFetch(
      { code: 'import.duplicate_file', title: 'File already imported', detail: 'Seen before.' },
      409,
    )

    await expect(uploadReport(new File(['bytes'], 'may.xlsx'))).rejects.toMatchObject({
      status: 409,
      code: 'import.duplicate_file',
      detail: 'Seen before.',
    })
  })
})

describe('fetchKpis', () => {
  it('asks for exactly the days of the month, leap years included', async () => {
    const seen = fakeFetch(kpiSummary())

    await fetchKpis({ from: '2028-02-01', to: '2028-02-29' })

    const url = new URL(seen[0]?.url ?? '')
    expect(url.pathname).toBe('/api/v1/telephony/kpis')
    expect(url.searchParams.get('date_from')).toBe('2028-02-01')
    expect(url.searchParams.get('date_to')).toBe('2028-02-29')
  })
})
