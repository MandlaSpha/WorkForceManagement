<script setup lang="ts">
import { computed } from 'vue'

import CountUp from './CountUp.vue'

/** A donut with the headline number in the middle. `value` null means there is no data: the ring
 * is empty and says "No data", it never shows a made-up zero. */
const props = withDefaults(
  defineProps<{
    /** 0 to 100, or null for no data. */
    value: number | null
    /** What the number is, for people who cannot see the ring: "Adherence this week". */
    label: string
    tone?: 'brand' | 'ok' | 'warn' | 'danger'
    size?: number
    unit?: string
    emptyText?: string
  }>(),
  { tone: 'brand', size: 88, unit: '%', emptyText: 'No data' },
)

const TONE = { brand: 'text-brand', ok: 'text-ok', warn: 'text-warn', danger: 'text-danger' }
const filled = computed(() => (props.value === null ? 0 : Math.min(100, Math.max(0, props.value))))
const format = (n: number) => `${Math.round(n)}${props.unit}`
</script>

<template>
  <div
    class="relative inline-grid place-items-center"
    :style="{ width: `${size}px`, height: `${size}px` }"
    role="img"
    :aria-label="value === null ? `${label}: ${emptyText}` : `${label}: ${format(value)}`"
  >
    <svg viewBox="0 0 40 40" class="absolute inset-0 size-full -rotate-90" aria-hidden="true">
      <circle cx="20" cy="20" r="16" fill="none" stroke="var(--surface-muted)" stroke-width="4.5" />
      <circle
        v-if="value !== null && filled > 0"
        cx="20"
        cy="20"
        r="16"
        fill="none"
        stroke="currentColor"
        stroke-width="4.5"
        stroke-linecap="round"
        pathLength="100"
        :stroke-dasharray="`${filled} 100`"
        class="ring-arc"
        :class="TONE[tone]"
      />
    </svg>
    <span
      class="relative text-center font-semibold tabular-nums leading-none text-ink"
      :class="value === null ? 'px-2 text-[11px] text-ink-muted' : 'text-lg'"
      aria-hidden="true"
    >
      <template v-if="value === null">{{ emptyText }}</template>
      <CountUp v-else :value="value" :format="format" />
    </span>
  </div>
</template>

<style scoped>
@keyframes ring-draw {
  from {
    stroke-dasharray: 0 100;
  }
}
@media (prefers-reduced-motion: no-preference) {
  .ring-arc {
    animation: ring-draw 0.7s cubic-bezier(0.2, 0.7, 0.2, 1) both;
  }
}
</style>
