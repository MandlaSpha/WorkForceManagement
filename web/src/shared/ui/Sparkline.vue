<script setup lang="ts">
import { computed } from 'vue'

import { scaleY, smoothPath, type Pt } from './chart-math'

const props = withDefaults(
  defineProps<{
    /** One value per step; null = no value (the line breaks, it never drops to zero). */
    values: ReadonlyArray<number | null>
    /** Text alternative, for example "Gap by day this week: 12, 0, 3". */
    label: string
    endDot?: boolean
    /** Colour token; "current" takes the text colour of the parent (for a solid tile). */
    tone?: 'brand' | 'danger' | 'ok' | 'current'
    emptyText?: string
  }>(),
  { endDot: true, tone: 'brand', emptyText: 'No data yet' },
)

const TONE = {
  brand: 'text-brand',
  danger: 'text-danger',
  ok: 'text-ok',
  current: '',
}

const W = 120
const H = 36
const PAD = 4

const known = computed(() => props.values.filter((v): v is number => v !== null))
const y = computed(() => scaleY(known.value.length ? known.value : [0], PAD, H - PAD * 2))
const stepX = computed(() => (W - PAD * 2) / Math.max(1, props.values.length - 1))

/** Runs of consecutive known values; each is its own curve. */
const segments = computed<Pt[][]>(() => {
  const runs: Pt[][] = []
  let run: Pt[] = []
  props.values.forEach((v, i) => {
    if (v === null) {
      if (run.length) runs.push(run)
      run = []
      return
    }
    run.push({ x: props.values.length === 1 ? W / 2 : PAD + i * stepX.value, y: y.value(v) })
  })
  if (run.length) runs.push(run)
  return runs
})

const lines = computed(() => segments.value.filter((s) => s.length > 1).map((s) => smoothPath(s)))
const areas = computed(() =>
  segments.value
    .filter((s) => s.length > 1)
    .map((s) => `${smoothPath(s)} L${s.at(-1)!.x.toFixed(1)} ${H} L${s[0]!.x.toFixed(1)} ${H} Z`),
)
const last = computed(() => segments.value.at(-1)?.at(-1) ?? null)
</script>

<template>
  <p v-if="known.length === 0" class="text-xs text-ink-muted" data-testid="sparkline-empty">
    {{ emptyText }}
  </p>
  <svg
    v-else
    :viewBox="`0 0 ${W} ${H}`"
    class="h-9 w-full overflow-visible"
    :class="TONE[tone]"
    role="img"
    :aria-label="label"
    data-testid="sparkline"
  >
    <path
      v-for="(a, i) in areas"
      :key="`a${i}`"
      :d="a"
      fill="currentColor"
      fill-opacity="0.12"
      class="spark-area"
    />
    <path
      v-for="(l, i) in lines"
      :key="`l${i}`"
      :d="l"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      pathLength="1"
      class="spark-line"
      data-testid="sparkline-line"
    />
    <circle v-if="endDot && last" :cx="last.x" :cy="last.y" r="3" fill="currentColor" />
  </svg>
</template>
