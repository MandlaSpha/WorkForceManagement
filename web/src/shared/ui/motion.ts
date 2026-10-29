/** True when the person asked the system for less motion. Without matchMedia (tests, old
 *  browsers) we treat it as "reduce", so nothing animates unless we know it is welcome. */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return true
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
