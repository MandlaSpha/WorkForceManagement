<script setup lang="ts">
import { computed } from 'vue'

export interface ChartPoint {
  label: string // x-axis label, "10:00"
  bars: number // the shaded bar: for example expected calls
  line: number | null // the line on the right axis: for example agents required; null = no value
}

const props = defineProps<{
  points: ReadonlyArray<ChartPoint>
  /** Names the chart for people who cannot see it. */
  summary: string
  barLabel: string
  lineLabel: string
}>()

const W = 960
const H = 280
const LEFT = 44
const RIGHT = 44
const TOP = 12
const BOTTOM = 28
const innerW = W - LEFT - RIGHT
const innerH = H - TOP - BOTTOM

const ceil = (v: number) => Math.max(1, Math.ceil(v))
const maxBar = computed(() => ceil(Math.max(0, ...props.points.map((p) => p.bars))))
const maxLine = computed(() => ceil(Math.max(0, ...props.points.map((p) => p.line ?? 0))))
const step = computed(() => innerW / Math.max(1, props.points.length))

const bars = computed(() =>
  props.points.map((p, i) => {
    const height = (p.bars / maxBar.value) * innerH
    return {
      key: p.label,
      x: LEFT + i * step.value + step.value * 0.15,
      y: TOP + innerH - height,
      width: step.value * 0.7,
      height,
    }
  }),
)

/** The line is broken where there is no value, so a gap never reads as zero. */
const linePath = computed(() => {
  let path = ''
  let drawing = false
  props.points.forEach((p, i) => {
    if (p.line === null) {
      drawing = false
      return
    }
    const x = LEFT + i * step.value + step.value / 2
    const y = TOP + innerH - (p.line / maxLine.value) * innerH
    path += `${drawing ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)} `
    drawing = true
  })
  return path.trim()
})

const xLabels = computed(() =>
  props.points
    .map((p, i) => ({ label: p.label, x: LEFT + i * step.value + step.value / 2, i }))
    .filter((p) => p.i % 4 === 0),
)
</script>

<template>
  <figure class="space-y-2">
    <svg
      :viewBox="`0 0 ${W} ${H}`"
      class="w-full"
      role="img"
      :aria-label="summary"
      data-testid="interval-chart"
    >
      <line :x1="LEFT" :x2="W - RIGHT" :y1="TOP + innerH" :y2="TOP + innerH" class="stroke-line" />
      <rect
        v-for="bar in bars"
        :key="bar.key"
        :x="bar.x"
        :y="bar.y"
        :width="bar.width"
        :height="bar.height"
        class="fill-brand/40"
        data-testid="chart-bar"
      />
      <path
        v-if="linePath"
        :d="linePath"
        fill="none"
        stroke-width="2"
        class="stroke-danger"
        data-testid="chart-line"
      />
      <text :x="LEFT - 6" :y="TOP + 8" text-anchor="end" class="fill-ink-muted text-[10px]">
        {{ maxBar }}
      </text>
      <text :x="W - RIGHT + 6" :y="TOP + 8" class="fill-danger text-[10px]">{{ maxLine }}</text>
      <text
        v-for="tick in xLabels"
        :key="tick.i"
        :x="tick.x"
        :y="H - 8"
        text-anchor="middle"
        class="fill-ink-muted text-[10px]"
      >
        {{ tick.label }}
      </text>
    </svg>

    <figcaption class="flex flex-wrap gap-4 text-xs text-ink-muted">
      <span class="inline-flex items-center gap-1.5">
        <span class="inline-block size-3 rounded-sm bg-brand/40" aria-hidden="true"></span>
        {{ barLabel }} (left axis)
      </span>
      <span class="inline-flex items-center gap-1.5">
        <span class="inline-block h-0.5 w-4 bg-danger" aria-hidden="true"></span>
        {{ lineLabel }} (right axis)
      </span>
    </figcaption>

    <details class="text-sm">
      <summary class="cursor-pointer text-brand-ink">Show the numbers</summary>
      <div class="mt-2 max-h-72 overflow-auto rounded-xl border border-line">
        <table class="w-full text-left text-sm">
          <thead class="sticky top-0 bg-surface-muted text-xs text-ink-muted">
            <tr>
              <th scope="col" class="px-3 py-1.5 font-medium">Time</th>
              <th scope="col" class="px-3 py-1.5 text-right font-medium">{{ barLabel }}</th>
              <th scope="col" class="px-3 py-1.5 text-right font-medium">{{ lineLabel }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in points" :key="p.label" class="border-t border-line">
              <th scope="row" class="px-3 py-1 font-normal tabular-nums">{{ p.label }}</th>
              <td class="px-3 py-1 text-right tabular-nums">{{ p.bars.toFixed(1) }}</td>
              <td class="px-3 py-1 text-right tabular-nums">{{ p.line ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
  </figure>
</template>
