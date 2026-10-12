import { InMemorySpanExporter, type ReadableSpan } from '@opentelemetry/sdk-trace-base'
import { expect, vi } from 'vitest'

import { initTelemetry } from '@/shared/telemetry'

/** Helpers for tests that look at the spans the app produced. */
export let exporter: InMemorySpanExporter

export function startTelemetry(options: { sampleRatio?: number } = {}): void {
  exporter = new InMemorySpanExporter()
  initTelemetry({ exporter, synchronous: true, ...options })
}

/** Every span's name, attributes and events as one string, to search for leaked values. */
export function everythingRecorded(): string {
  return exporter
    .getFinishedSpans()
    .map((s: ReadableSpan) =>
      JSON.stringify({
        name: s.name,
        attributes: s.attributes,
        events: s.events.map((e) => ({ name: e.name, attributes: e.attributes })),
      }),
    )
    .join('\n')
}

export const spanNamed = (prefix: string) =>
  exporter.getFinishedSpans().filter((s: ReadableSpan) => s.name.startsWith(prefix))

/** Fetch spans are recognised by their HTTP method attribute, not by name: the name format
 * differs between instrumentation versions ("GET" now, "HTTP GET" before). */
export const fetchSpans = (method?: string) =>
  exporter
    .getFinishedSpans()
    .filter(
      (s: ReadableSpan) =>
        'http.request.method' in s.attributes &&
        (!method || s.attributes['http.request.method'] === method),
    )

/** The fetch instrumentation keeps a span open for ~300 ms after the response while it looks for
 * browser resource-timing entries, so tests must wait for spans rather than assert at once. */
export const waitForFetchSpans = (count = 1, method?: string) =>
  vi.waitFor(() => expect(fetchSpans(method).length).toBeGreaterThanOrEqual(count), {
    timeout: 3000,
  })

/** For "nothing was recorded" assertions: wait longer than the instrumentation's hold-open time. */
export const settle = () => new Promise((resolve) => setTimeout(resolve, 600))
