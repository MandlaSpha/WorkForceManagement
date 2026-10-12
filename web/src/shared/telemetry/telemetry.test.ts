import { InMemorySpanExporter } from '@opentelemetry/sdk-trace-base'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'

import { api } from '@/shared/api'
import { server } from '@/test/server'
import {
  everythingRecorded,
  exporter,
  fetchSpans,
  settle,
  spanNamed,
  startTelemetry,
  waitForFetchSpans,
} from '@/test/spans'

import { stripQuery } from './sanitize'
import { initTelemetry, recordRouteChange, setTelemetryRole, shutdownTelemetry } from './telemetry'

const TRACEPARENT = /^00-([0-9a-f]{32})-[0-9a-f]{16}-([0-9a-f]{2})$/

afterEach(async () => {
  await shutdownTelemetry()
})

describe('stripQuery', () => {
  it.each([
    [
      'https://wfm.example/api/v1/leave?employee=42&name=Pat#top',
      'https://wfm.example/api/v1/leave',
    ],
    ['/api/v1/auth/me?x=1', '/api/v1/auth/me'],
    ['/login?redirect=/roster', '/login'],
    ['/plain', '/plain'],
  ])('%s -> %s', (input, expected) => {
    expect(stripQuery(input)).toBe(expected)
  })
})

describe('trace continuity with the API', () => {
  it('sends a W3C traceparent that matches the exported fetch span', async () => {
    startTelemetry()
    let header: string | null = null
    server.use(
      http.get('*/api/v1/auth/me', ({ request }) => {
        header = request.headers.get('traceparent')
        return HttpResponse.json({ username: 'u', displayName: 'U', role: 'planner' })
      }),
    )

    await api.GET('/api/v1/auth/me')
    await waitForFetchSpans(1, 'GET')

    const match = TRACEPARENT.exec(header ?? '')
    expect(match, `traceparent was ${header}`).not.toBeNull()
    const [fetchSpan] = fetchSpans('GET')
    expect(fetchSpan?.spanContext().traceId).toBe(match![1])
    expect(match![2]).toBe('01') // sampled
  })

  it("does not trace or propagate telemetry's own export requests", async () => {
    startTelemetry()
    let header: string | null = 'unset'
    server.use(
      http.post('*/otlp/v1/traces', ({ request }) => {
        header = request.headers.get('traceparent')
        return new HttpResponse(null, { status: 200 })
      }),
    )

    await fetch(`${window.location.origin}/otlp/v1/traces`, { method: 'POST', body: '{}' })
    await settle()

    expect(header).toBeNull()
    expect(fetchSpans('POST')).toHaveLength(0)
  })

  it('respects a 0 sampling ratio: nothing is exported and the header says "not sampled"', async () => {
    startTelemetry({ sampleRatio: 0 })
    let header: string | null = null
    server.use(
      http.get('*/api/v1/auth/me', ({ request }) => {
        header = request.headers.get('traceparent')
        return HttpResponse.json({ username: 'u', displayName: 'U', role: 'planner' })
      }),
    )

    await api.GET('/api/v1/auth/me')
    await settle()

    expect(exporter.getFinishedSpans()).toHaveLength(0)
    expect(TRACEPARENT.exec(header ?? '')?.[2]).toBe('00')
  })
})

describe('what spans may carry', () => {
  it('labels spans with the role, and "anonymous" when signed out', async () => {
    startTelemetry()
    await api.GET('/api/v1/auth/me')
    setTelemetryRole('planner')
    await api.GET('/api/v1/auth/me')
    await waitForFetchSpans(2, 'GET')

    const roles = fetchSpans('GET').map((s) => s.attributes['wfm.role'])
    expect(roles).toEqual(['anonymous', 'planner'])
  })

  it('removes query strings, even when fetch is called with a plain string', async () => {
    startTelemetry()

    await fetch(`${window.location.origin}/api/v1/auth/me?name=Pat&secret=hunter2#frag`)
    await waitForFetchSpans(1, 'GET')

    const [span] = fetchSpans('GET')
    expect(span).toBeDefined()
    expect(everythingRecorded()).not.toContain('hunter2')
    expect(everythingRecorded()).not.toContain('name=Pat')
    expect(String(span!.attributes['url.full'])).toMatch(/\/api\/v1\/auth\/me$/)
  })

  it('records a screen change by route name only', () => {
    startTelemetry()
    recordRouteChange('roster')

    const [span] = spanNamed('route.change')
    expect(span?.attributes['wfm.route']).toBe('roster')
    expect(everythingRecorded()).not.toContain('redirect')
  })

  it('records an unhandled error by type, never by message', () => {
    startTelemetry()

    window.dispatchEvent(
      new ErrorEvent('error', {
        error: new TypeError('failed for pat.private with password hunter2'),
        message: 'failed for pat.private with password hunter2',
      }),
    )

    const [span] = spanNamed('js.error')
    expect(span?.attributes['error.type']).toBe('TypeError')
    expect(everythingRecorded()).not.toContain('hunter2')
    expect(everythingRecorded()).not.toContain('pat.private')
  })
})

describe('lifecycle', () => {
  it('starting twice does not double-record', async () => {
    startTelemetry()
    initTelemetry({ exporter: new InMemorySpanExporter(), synchronous: true })

    await api.GET('/api/v1/auth/me')
    await waitForFetchSpans(1, 'GET')
    await settle()

    expect(fetchSpans('GET')).toHaveLength(1)
  })

  it('stops tracing after shutdown', async () => {
    startTelemetry()
    await shutdownTelemetry()
    exporter.reset()

    await api.GET('/api/v1/auth/me')
    await settle()

    expect(exporter.getFinishedSpans()).toHaveLength(0)
  })
})
