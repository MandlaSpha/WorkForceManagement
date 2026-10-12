/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" starts browser tracing (spans go to the same-origin /otlp/v1/traces). */
  readonly VITE_OTEL_ENABLED?: string
  /** 0..1 share of new traces to record. Defaults to 1. */
  readonly VITE_OTEL_SAMPLE_RATIO?: string
  /** "1" shows the demo-login shortcut panel (development only). */
  readonly VITE_DEMO_LOGINS?: string
  /** Password of the synthetic demo accounts; set in a local .env, never committed. */
  readonly VITE_DEMO_PASSWORD?: string
}
