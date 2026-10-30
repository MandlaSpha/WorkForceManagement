import { onBeforeUnmount, ref, watch, type Ref } from 'vue'

import { prefersReducedMotion } from './motion'

/**
 * Animated number. `text` is ALWAYS the final formatted value (for screen readers and tests);
 * `shown` is what to paint while `animating` is true. With reduced motion, animating is never true.
 */
export function useCountUp(
  target: Ref<number> | (() => number),
  format: (n: number) => string,
  durationMs = 1300,
) {
  const read = () => (typeof target === 'function' ? target() : target.value)
  const text = ref(format(read()))
  const shown = ref(text.value)
  const animating = ref(false)
  let frame = 0

  function run(from: number, to: number): void {
    cancelAnimationFrame(frame)
    const start = performance.now()
    animating.value = true
    const tick = (now: number) => {
      const t = Math.min(1, Math.max(0, (now - start) / durationMs))
      const eased = 1 - Math.pow(1 - t, 3)
      shown.value = format(from + (to - from) * eased)
      if (t < 1) frame = requestAnimationFrame(tick)
      else animating.value = false
    }
    frame = requestAnimationFrame(tick)
  }

  watch(
    () => read(),
    (to, from) => {
      text.value = format(to)
      if (!Number.isFinite(to) || prefersReducedMotion()) {
        shown.value = text.value
        animating.value = false
      } else run(Number.isFinite(from) ? from : 0, to)
    },
  )

  // First paint: count up from zero.
  if (Number.isFinite(read()) && !prefersReducedMotion()) run(0, read())

  onBeforeUnmount(() => cancelAnimationFrame(frame))
  return { text, shown, animating }
}
