<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

export interface ChartPoint {
  label: string // x-axis label, "10:00"
  bars: number | null // the shaded bar: for example expected calls; null = no value, no bar
  line: number | null // the line on the right axis: for example agents required; null = no value
}

const props = withDefaults(
  defineProps<{
    points: ReadonlyArray<ChartPoint>
    /** Names the chart for people who cannot see it. */
    summary: string
    barLabel: string
    lineLabel: string
    /** Label every n-th point on the x axis (every 4th half-hour by default). */
    labelEvery?: number
    /** Heading of the first column of the numbers table. */
    categoryLabel?: string
  }>(),
  { labelEvery: 4, categoryLabel: 'Time' },
)

const W = 960
const H = 280
const LEFT = 48
const RIGHT = 48
const TOP = 12
const BOTTOM = 28
const innerW = W - LEFT - RIGHT
const innerH = H - TOP - BOTTOM

const ceil = (v: number) => Math.max(1, Math.ceil(v))
const maxBar = computed(() => ceil(Math.max(0, ...props.points.map((p) => p.bars ?? 0))))
const maxLine = computed(() => ceil(Math.max(0, ...props.points.map((p) => p.line ?? 0))))
const step = computed(() => innerW / Math.max(1, props.points.length))

const hover = ref<number | null>(null)

// The drawing scales with the width of the page, so its text would too. Axis text is set in
// drawing units that come out as TICK_PX on screen, the same size as the text around the chart.
const TICK_PX = 12
const svg = ref<SVGSVGElement | null>(null)
const shownWidth = ref(W)
let watcher: ResizeObserver | null = null
onMounted(() => {
  if (!svg.value || typeof ResizeObserver === 'undefined') return
  watcher = new ResizeObserver(([entry]) => {
    if (entry && entry.contentRect.width > 0) shownWidth.value = entry.contentRect.width
  })
  watcher.observe(svg.value)
})
onBeforeUnmount(() => watcher?.disconnect())
// Whole numbers only, and a number once: with a top of 1 the quarters would all read 0 or 1.
function ticksFor(top: number): Array<{ f: number; v: number }> {
  const seen = new Set<number>()
  return [0, 0.25, 0.5, 0.75, 1].flatMap((f) => {
    const v = Math.round(top * f)
    if (seen.has(v)) return []
    seen.add(v)
    return { f: v / top, v }
  })
}
const leftTicks = computed(() => ticksFor(maxBar.value))
const rightTicks = computed(() => ticksFor(maxLine.value))
const tickSize = computed(() => `${(TICK_PX * W) / shownWidth.value}px`)

function onMove(e: PointerEvent): void {
  const el = e.currentTarget as SVGGraphicsElement
  const box = el.getBoundingClientRect()
  if (box.width === 0) return
  const i = Math.floor(((e.clientX - box.left) / box.width) * props.points.length)
  hover.value = Math.min(props.points.length - 1, Math.max(0, i))
}

const tip = computed(() => {
  const p = hover.value === null ? null : props.points[hover.value]
  if (!p || hover.value === null) return null
  const bar = p.bars === null ? 'no value' : p.bars.toFixed(1)
  const line = p.line === null ? 'no value' : String(p.line)
  return {
    left: ((LEFT + hover.value * step.value + step.value / 2) / W) * 100,
    text: `${p.label}: ${props.barLabel} ${bar}, ${props.lineLabel} ${line}`,
  }
})

const bars = computed(() =>
  props.points.flatMap((p, i) => {
    if (p.bars === null) return [] // no value is no bar, never a bar of zero height
    const height = (p.bars / maxBar.value) * innerH
    return {
      index: i,
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
    .filter((p) => p.i % props.labelEvery === 0),
)
</script>

<template>
  <figure class="relative space-y-2">
    <div
      v-if="tip"
      class="pointer-events-none absolute z-10 -translate-x-1/2 whitespace-nowrap rounded-lg bg-ink px-2 py-1 text-xs text-canvas shadow-pop"
      :style="{ left: `${tip.left}%`, top: '0' }"
      role="status"
      data-testid="chart-tooltip"
    >
      {{ tip.text }}
    </div>
    <svg
      ref="svg"
      :viewBox="`0 0 ${W} ${H}`"
      class="w-full"
      role="img"
      :aria-label="summary"
      data-testid="interval-chart"
    >
      <line
        v-for="g in [0.25, 0.5, 0.75]"
        :key="g"
        :x1="LEFT"
        :x2="W - RIGHT"
        :y1="TOP + innerH * g"
        :y2="TOP + innerH * g"
        class="stroke-chart-grid"
        stroke-dasharray="3 5"
      />
      <line :x1="LEFT" :x2="W - RIGHT" :y1="TOP + innerH" :y2="TOP + innerH" class="stroke-line" />
      <rect
        v-for="bar in bars"
        :key="bar.key"
        :x="bar.x"
        :y="bar.y"
        :width="bar.width"
        :height="bar.height"
        rx="4"
        class="bar-grow fill-brand/40"
        :style="{ animationDelay: `${Math.min(bar.index * 22, 700)}ms` }"
        :class="hover === bar.index ? 'fill-brand/70' : ''"
        data-testid="chart-bar"
      />
      <line
        v-if="hover !== null"
        :x1="LEFT + hover * step + step / 2"
        :x2="LEFT + hover * step + step / 2"
        :y1="TOP"
        :y2="TOP + innerH"
        class="stroke-ink-muted"
        stroke-dasharray="2 3"
        data-testid="chart-crosshair"
      />
      <rect
        :x="LEFT"
        :y="TOP"
        :width="innerW"
        :height="innerH"
        fill="transparent"
        @pointermove="onMove"
        @pointerleave="hover = null"
      />
      <path
        v-if="linePath"
        :d="linePath"
        fill="none"
        stroke-width="2"
        pathLength="1"
        class="spark-line stroke-danger"
        data-testid="chart-line"
      />
      <text
        v-for="t in leftTicks"
        :key="`l${t.f}`"
        :x="LEFT - 8"
        :y="TOP + innerH * (1 - t.f) + 4"
        text-anchor="end"
        class="fill-ink-muted"
        :style="{ fontSize: tickSize }"
      >
        {{ t.v }}
      </text>
      <text
        v-for="t in rightTicks"
        :key="`r${t.f}`"
        :x="W - RIGHT + 8"
        :y="TOP + innerH * (1 - t.f) + 4"
        class="fill-danger"
        :style="{ fontSize: tickSize }"
      >
        {{ t.v }}
      </text>
      <text
        v-for="tick in xLabels"
        :key="tick.i"
        :x="tick.x"
        :y="H - 8"
        text-anchor="middle"
        class="fill-ink-muted"
        :style="{ fontSize: tickSize }"
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
              <th scope="col" class="px-3 py-1.5 font-medium">{{ categoryLabel }}</th>
              <th scope="col" class="px-3 py-1.5 text-right font-medium">{{ barLabel }}</th>
              <th scope="col" class="px-3 py-1.5 text-right font-medium">{{ lineLabel }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in points" :key="p.label" class="border-t border-line">
              <th scope="row" class="px-3 py-1 font-normal tabular-nums">{{ p.label }}</th>
              <td class="px-3 py-1 text-right tabular-nums">
                {{ p.bars === null ? '—' : p.bars.toFixed(1) }}
              </td>
              <td class="px-3 py-1 text-right tabular-nums">{{ p.line ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
  </figure>
</template>
