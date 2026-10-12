/**
 * Telemetry must never carry personal data (requirements OBS-05, OBS-10). URLs are the usual leak
 * — a query string can hold a name, an id or a redirect target — so every URL that reaches a span
 * goes through here first.
 */

/** The URL without its query string and fragment. Anything that is not a URL becomes "". */
export function stripQuery(url: string): string {
  try {
    const parsed = new URL(url, 'http://placeholder.invalid')
    const base = /^[a-z][a-z0-9+.-]*:/i.test(url)
      ? `${parsed.origin}${parsed.pathname}`
      : parsed.pathname
    return base
  } catch {
    return ''
  }
}
