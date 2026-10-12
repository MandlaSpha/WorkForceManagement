import { expect, test } from '@playwright/test'

import { PASSWORD, signIn } from './helpers'

/**
 * Tracing proof (requirements OBS-01, OBS-05, OBS-10). These need the stack started with
 * telemetry on, which `just dev` does: the web app has VITE_OTEL_ENABLED=1 and Aspire gives the
 * API and the worker an OTLP endpoint.
 */
test.describe('tracing', () => {
  test('one browser action is one trace through the API and into the background worker', async ({
    page,
  }) => {
    await signIn(page, 'admin')

    const requestSent = page.waitForRequest((r) => r.url().endsWith('/api/v1/system/ping-worker'))
    const body = await page.evaluate(async () => {
      const token =
        document.cookie
          .split('; ')
          .find((c) => c.startsWith('csrftoken='))
          ?.split('=')[1] ?? ''
      const response = await fetch('/api/v1/system/ping-worker', {
        method: 'POST',
        headers: { 'X-CSRFToken': token },
      })
      return { status: response.status, json: await response.json() }
    })
    const request = await requestSent

    expect(body.status).toBe(200)
    const traceparent = request.headers()['traceparent'] ?? ''
    const browserTrace = /^00-([0-9a-f]{32})-[0-9a-f]{16}-01$/.exec(traceparent)?.[1]
    expect(browserTrace, `browser sent traceparent "${traceparent}"`).toBeTruthy()

    // The API continued the browser's trace, and so did the Celery worker it called.
    expect(body.json.apiTraceId, 'API trace id').toBe(browserTrace)
    expect(body.json.workerTraceId, 'worker trace id').toBe(browserTrace)
  })

  test('browser spans reach the collector through the same-origin proxy and carry no personal data', async ({
    page,
  }) => {
    const exports: Array<{ status: number; body: string }> = []
    page.on('response', async (response) => {
      if (response.url().includes('/otlp/v1/traces')) {
        exports.push({
          status: response.status(),
          body: response.request().postData() ?? '',
        })
      }
    })

    await signIn(page, 'planner')
    await page.getByRole('link', { name: 'Forecast' }).click()
    await expect(page.getByRole('heading', { name: 'Forecast' })).toBeVisible()
    await page.goto('/login?redirect=/roster&name=Pat') // a URL with a query string
    // Spans are exported in batches and when the page is hidden.
    await expect.poll(() => exports.length, { timeout: 15_000 }).toBeGreaterThan(0)

    for (const e of exports) expect(e.status, 'collector accepted the spans').toBeLessThan(300)
    const everything = exports.map((e) => e.body).join('\n')

    expect(everything).toContain('wfm.role') // labelled by role...
    expect(everything).toContain('route.change') // ...and by screen
    for (const secret of [PASSWORD, 'Pat Planner', 'redirect=', 'name=Pat']) {
      expect(everything, `telemetry leaked "${secret}"`).not.toContain(secret)
    }
  })

  test('the API labels its response with a request id for correlation', async ({ request }) => {
    const response = await request.get('/api/v1/auth/csrf')
    expect(response.headers()['x-request-id']).toBeTruthy()
  })
})
