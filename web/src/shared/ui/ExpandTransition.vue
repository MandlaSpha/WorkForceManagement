<script setup lang="ts">
/** Opens and closes a block by animating its height. Works with `v-show` on the child, so a
 * closed block is still display:none (out of the tab order and the accessibility tree) once the
 * animation ends. Where animation is unavailable or unwanted it simply shows or hides. */
const DURATION_MS = 260
const EASING = 'cubic-bezier(0.2, 0.7, 0.2, 1)'

function reduced(el: Element): boolean {
  return (
    typeof (el as HTMLElement).animate !== 'function' ||
    (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches)
  )
}

function run(el: Element, from: string, to: string, done: () => void): void {
  const node = el as HTMLElement
  const previous = node.style.overflow
  node.style.overflow = 'hidden'
  const animation = node.animate(
    [
      { height: from, opacity: from === '0px' ? 0 : 1 },
      { height: to, opacity: to === '0px' ? 0 : 1 },
    ],
    { duration: DURATION_MS, easing: EASING },
  )
  const finish = (): void => {
    node.style.overflow = previous
    done()
  }
  animation.addEventListener('finish', finish, { once: true })
  animation.addEventListener('cancel', finish, { once: true })
}

function onEnter(el: Element, done: () => void): void {
  if (reduced(el)) return done()
  run(el, '0px', `${(el as HTMLElement).scrollHeight}px`, done)
}
function onLeave(el: Element, done: () => void): void {
  if (reduced(el)) return done()
  run(el, `${(el as HTMLElement).offsetHeight}px`, '0px', done)
}
</script>

<template>
  <!-- `persisted`: the slot holds a v-show the compiler cannot see from here. -->
  <Transition :css="false" persisted @enter="onEnter" @leave="onLeave"><slot /></Transition>
</template>
