# ADR 0004: Grafana operations dashboards (optional, development)

Status: Proposed, 31 October 2026. Legal confirmation of the AGPL-3.0 position is still open (system design section 7: "free for internal use, to be confirmed with legal"). Until it is given, Grafana is a **development-only, opt-in** resource and nothing in production depends on it.

## Context
Requirement OBS-11 asks for operations dashboards in Grafana: traces, logs and metrics from the existing OpenTelemetry data, as an optional resource beside the Aspire dashboard, under the same POPIA rules as OBS-04 to OBS-10 (nothing personal in telemetry). It also says an ADR records the licence position before Grafana is added.

The coding standards allow MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0, PostgreSQL and LGPL without a record. **Grafana is AGPL-3.0**, so it needs this record. Tempo and Loki (the stores OBS-11 names) are AGPL-3.0 as well.

What exists today: the API and worker export **traces only** (`wfm/core/telemetry.py`); there is no metrics or log export yet. The Aspire dashboard is the only place to look, and it is for development.

## Decision
1. **Grafana OSS runs as a separate, unmodified container**, started only by `just dev-grafana` (`WFM_GRAFANA=1`). It is never linked into, imported by or shipped with the application, which is the usual reading under which AGPL's network clause does not reach our code. It is anonymous and bound to this machine in development, like the Aspire dashboard.
2. **Keep the AGPL footprint to Grafana alone.** Traces go to **Jaeger** (Apache-2.0), not Tempo; metrics to **Prometheus** (Apache-2.0); the pipeline is the **OpenTelemetry Collector** (Apache-2.0). Tempo and Loki can replace Jaeger and add logs later, each with a line added here.
3. **Metrics come from the spans**, through the collector's `spanmetrics` connector: request rate, errors and latency by route template, method, status and the role of the signed-in person. No new instrumentation, so no new way for a person to enter telemetry.
4. **The API and worker send a second copy of their spans** to the collector (`WFM_OTEL_MIRROR_ENDPOINT`), beside the Aspire dashboard. It is a second processor on the same tracer provider, so it carries exactly the scrubbed spans the first does, and it never switches telemetry on by itself. (The collector cannot sit in front of the dashboard: the dashboard only listens on localhost.)
5. **A second scrub in the collector** (`attributes/scrub`) deletes identity-looking attributes and any query string before storage. The application's own scrubbing, with its tests that search spans for leaked values, stays the primary control.

## Licence and data position
- Grafana OSS: AGPL-3.0. Run unmodified as a separate service; if it is ever modified, the changes must be offered under the AGPL, so we do not modify it. Provisioning (data sources, dashboards) is configuration, not a modification.
- Prometheus, Jaeger and the OpenTelemetry Collector: Apache-2.0.
- Telemetry stays in our own infrastructure (OBS-09). Grafana's own analytics and update checks are switched off.
- Retention follows OBS-08 (traces 14 to 30 days). The development stack keeps nothing beyond its containers' lifetime.

## Consequences
- Legal confirmation is needed before any hosted environment runs Grafana. If it is refused, the alternatives are Jaeger's own UI and Prometheus's, or a re-export (OTLP) to the customer's tool, which OBS-11 already requires; the dashboards' queries are plain PromQL and carry over.
- Logs are not in this step: the application does not export them yet, and Loki is AGPL. A later step adds a scrubbed log exporter and records Loki here.
- The browser's spans still go only to the Aspire dashboard; sending them to the collector too is a follow-up.
- The customer's own tools (for example SolarWinds or Splunk) are reached by standard OTLP export from the collector, not built in.
