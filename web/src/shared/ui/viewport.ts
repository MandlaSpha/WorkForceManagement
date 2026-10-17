/** Phone width, in step with Tailwind's `sm` breakpoint (640px): below it a page is a phone page. */
export const PHONE_QUERY = '(max-width: 639px)'

/** Is the window phone-sized right now? False where the browser cannot say (tests, old engines),
 * so a page then shows its full layout rather than a stripped-down one. Read once when a page
 * opens, to pick a starting view; the CSS breakpoints do the rest as the window changes. */
export function isPhone(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia(PHONE_QUERY).matches
}
