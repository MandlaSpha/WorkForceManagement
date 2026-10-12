import { context, trace } from '@opentelemetry/api'
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http'
import { registerInstrumentations } from '@opentelemetry/instrumentation'
import { DocumentLoadInstrumentation } from '@opentelemetry/instrumentation-document-load'
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch'
import { resourceFromAttributes } from '@opentelemetry/resources'
import {
  BatchSpanProcessor,
  ParentBasedSampler,
  SimpleSpanProcessor,
  TraceIdRatioBasedSampler,
  type ReadableSpan,
  type Span,
  type SpanExporter,
  type SpanProcessor,
} from '@opentelemetry/sdk-trace-base'
import { WebTracerProvider } from '@opentelemetry/sdk-trace-web'

import { stripQuery } from './sanitize'

/**
 * Browser tracing: one trace per user action that continues into the API, the background worker
 * and the database (OBS-01, OBS-02). Spans carry timings, the route *name*, the HTTP status and
 * the user's *role*; never names, usernames, form values, request bodies or query strings.
 *
 * Spans go to the same origin (`/otlp/v1/traces`), where the reverse proxy forwards them to our
 * own collector. Nothing is sent to a third party.
 */

export interface TelemetryOptions {
  serviceName?: string
  /** Same-origin OTLP/HTTP traces endpoint. */
  endpoint?: string
  /** Tests inject an in-memory exporter instead of the OTLP one. */
  exporter?: SpanExporter
  /** 0..1 share of new traces to record; an incoming sampling decision is always respected. */
  sampleRatio?: number
  /** Export each span immediately (tests) instead of in batches. */
  synchronous?: boolean
}

let currentRole = 'anonymous'
let currentRoute = ''
let teardown: (() => Promise<void>) | null = null

/** The signed-in user's role, or null when signed out. Roles are not personal data. */
export function setTelemetryRole(role: string | null): void {
  currentRole = role ?? 'anonymous'
}

/** Attributes that can carry a URL, and so a query string that may hold identifiers. */
const URL_ATTRIBUTES = ['http.url', 'url.full', 'http.target']
/** Attributes dropped outright: a query string on its own, or the browser's user agent. */
const DROPPED_ATTRIBUTES = ['url.query', 'http.user_agent', 'user_agent.original']

/**
 * Labels every span with the role and screen as it starts, and scrubs URLs as it ends. Scrubbing
 * at the end, whatever created the span, is deliberate: an instrumentation hook never sees the
 * URL when the caller passes a plain string to fetch, but every span passes through here. It must
 * be registered before the exporting processor so the exporter only ever sees clean spans.
 */
class WfmSpanProcessor implements SpanProcessor {
  onStart(span: Span): void {
    span.setAttribute('wfm.role', currentRole)
    if (currentRoute) span.setAttribute('wfm.route', currentRoute)
  }
  onEnd(span: ReadableSpan): void {
    // The span has ended, so setAttribute() is refused; the attribute map itself is still ours
    // to clean before any exporter reads it.
    const attributes = span.attributes as Record<string, unknown>
    for (const name of URL_ATTRIBUTES) {
      const value = attributes[name]
      if (typeof value === 'string') attributes[name] = stripQuery(value)
    }
    for (const name of DROPPED_ATTRIBUTES) {
      if (name in attributes) attributes[name] = ''
    }
  }
  forceFlush(): Promise<void> {
    return Promise.resolve()
  }
  shutdown(): Promise<void> {
    return Promise.resolve()
  }
}

function clampRatio(value: number | undefined): number {
  if (value === undefined || Number.isNaN(value)) return 1
  return Math.min(1, Math.max(0, value))
}

export function initTelemetry(options: TelemetryOptions = {}): boolean {
  if (teardown) return true // already running

  const exporter =
    options.exporter ?? new OTLPTraceExporter({ url: options.endpoint ?? '/otlp/v1/traces' })

  const provider = new WebTracerProvider({
    resource: resourceFromAttributes({
      'service.name': options.serviceName ?? 'wfm-web',
      'service.version': '0.1.0',
    }),
    sampler: new ParentBasedSampler({
      root: new TraceIdRatioBasedSampler(clampRatio(options.sampleRatio)),
    }),
    spanProcessors: [
      new WfmSpanProcessor(),
      options.synchronous
        ? new SimpleSpanProcessor(exporter)
        : new BatchSpanProcessor(exporter, { scheduledDelayMillis: 1000 }),
    ],
  })
  provider.register()

  const unregister = registerInstrumentations({
    instrumentations: [
      new FetchInstrumentation({
        // Telemetry's own traffic must not be traced (it would trace itself forever).
        ignoreUrls: [/\/otlp\//],
        // Same-origin requests get the W3C `traceparent` header automatically, which is how the
        // API continues this trace. Cross-origin requests never do.
      }),
      new DocumentLoadInstrumentation(),
    ],
  })

  const onHidden = () => {
    if (document.visibilityState === 'hidden') void provider.forceFlush()
  }
  document.addEventListener('visibilitychange', onHidden)
  const stopErrors = captureErrors()

  teardown = async () => {
    document.removeEventListener('visibilitychange', onHidden)
    stopErrors()
    unregister()
    await provider.shutdown()
    trace.disable()
    context.disable()
    teardown = null
    currentRole = 'anonymous'
    currentRoute = ''
  }
  return true
}

export async function shutdownTelemetry(): Promise<void> {
  await teardown?.()
}

/** Marks a screen change so fetch spans can be told apart by screen. Only the route *name*. */
export function recordRouteChange(routeName: string): void {
  currentRoute = routeName
  const span = trace.getTracer('wfm-web').startSpan('route.change', {
    attributes: { 'wfm.route': routeName },
  })
  span.end()
}

/** Unhandled errors become spans carrying the error *type* only: messages can contain data. */
function captureErrors(): () => void {
  const report = (type: string) => {
    const span = trace.getTracer('wfm-web').startSpan('js.error', {
      attributes: { 'error.type': type },
    })
    span.end()
  }
  const onError = (event: ErrorEvent) => report(event.error?.name ?? 'Error')
  const onRejection = (event: PromiseRejectionEvent) =>
    report((event.reason as { name?: string } | undefined)?.name ?? 'UnhandledRejection')
  window.addEventListener('error', onError)
  window.addEventListener('unhandledrejection', onRejection)
  return () => {
    window.removeEventListener('error', onError)
    window.removeEventListener('unhandledrejection', onRejection)
  }
}
