<script setup lang="ts">
import { computed } from 'vue'

import { smoothPath } from './chart-math'

export interface BarItem {
  label: string
  /** null = no value: an empty slot, never a bar of zero height. */
  value: number | null
  /** Optional second series drawn as a line (same scale as the bars unless `lineScale`). */
  line?: number | null
  /** Full name for the tooltip and screen readers when `label` is a short axis label. */
  title?: string
  /** Highlight: a high or low bar takes a second colour. Say what it means in `mark`. */
  tone?: 'high' | 'low'
  /** A short text drawn above the bar (for example "Busiest"). */
  mark?: string
}

const props = withDefaults(
  defineProps<{
    items: ReadonlyArray<BarItem>
    /** What the bars are, e.g. "People-half-hours short". */
    valueLabel: string
    lineLabel?: string
    summary: string
    format?: (n: number) => string
    emptyText?: string
    /** Show every n-th axis label (the others stay available as tooltips). */
    labelEvery?: number
  }>(),
  {
    labelEvery: 1,
    lineLabel: '',
    format: (n: number) => n.toLocaleString('en-ZA'),
    emptyText: 'No data yet',
  },
)

const known = computed(() => props.items.filter((i) => i.value !== null))
const max = computed(() =>
  Math.max(1, ...props.items.flatMap((i) => [i.value ?? 0, i.line ?? 0]).filter(Number.isFinite)),
)
const pct = (v: number) => `${(Math.max(0, v) / max.value) * 100}%`

const hasLine = computed(() => props.items.some((i) => i.line != null))
const linePath = computed(() => {
  const n = props.items.length
  const pts = props.items.flatMap((i, idx) =>
    i.line == null
      ? []
      : { x: ((idx + 0.5) / n) * 100, y: 100 - (Math.max(0, i.line) / max.value) * 100 },
  )
  return pts.length > 1 ? smoothPath(pts) : ''
})
</script>

<template>
  <p v-if="known.length === 0" class="text-sm text-ink-muted" data-testid="bars-empty">
    {{ emptyText }}
  </p>
  <figure v-else class="space-y-2" data-testid="bar-series">
    <div role="img" :aria-label="summary" class="relative">
      <ul
        class="grid h-28 items-end border-b border-line"
        :class="items.length > 24 ? 'gap-px' : 'gap-2'"
        :style="{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }"
      >
        <li
          v-for="(item, i) in items"
          :key="item.title ?? item.label"
          class="group relative flex h-full flex-col justify-end outline-none"
          tabindex="0"
          :aria-label="`${item.title ?? item.label}: ${item.value === null ? 'no value' : format(item.value)}${
            item.line != null ? `, ${lineLabel} ${format(item.line)}` : ''
          }`"
          :data-testid="`bar-${i}`"
        >
          <span
            v-if="item.value !== null"
            class="bar-grow block w-full rounded-t-lg group-hover:opacity-80 group-focus-visible:opacity-80"
            :class="
              item.tone === 'high'
                ? 'bg-chart-3'
                : item.tone === 'low'
                  ? 'bg-chart-2'
                  : 'bg-chart-1'
            "
            :style="{ height: pct(item.value), minHeight: item.value > 0 ? '2px' : '0' }"
          ></span>
          <span
            v-if="item.mark && item.value !== null"
            class="pointer-events-none absolute left-1/2 -translate-x-1/2 whitespace-nowrap text-[10px] font-semibold text-ink"
            :style="{ bottom: `calc(${pct(item.value)} + 2px)` }"
            aria-hidden="true"
            >{{ item.mark }}</span
          >
          <span
            role="tooltip"
            class="pointer-events-none absolute -top-8 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded-lg bg-ink px-2 py-1 text-xs font-medium text-canvas opacity-0 shadow-pop group-hover:opacity-100 group-focus-visible:opacity-100"
          >
            {{ item.title ?? item.label }}:
            {{ item.value === null ? 'no value' : format(item.value) }}
          </span>
        </li>
      </ul>
      <svg
        v-if="hasLine && linePath"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        class="pointer-events-none absolute inset-0 h-28 w-full overflow-visible"
        aria-hidden="true"
      >
        <path
          :d="linePath"
          fill="none"
          stroke="var(--chart-2)"
          stroke-width="2"
          vector-effect="non-scaling-stroke"
          pathLength="1"
          class="spark-line"
          data-testid="bars-line"
        />
      </svg>
    </div>
    <ol
      class="grid gap-2 text-center text-[11px] text-ink-muted"
      :style="{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }"
      aria-hidden="true"
    >
      <li v-for="(item, i) in items" :key="item.title ?? item.label" class="truncate">
        {{ i % labelEvery === 0 ? item.label : '' }}
      </li>
    </ol>
    <figcaption class="flex flex-wrap gap-4 text-xs text-ink-muted">
      <span class="inline-flex items-center gap-1.5">
        <span class="inline-block size-3 rounded-sm bg-chart-1" aria-hidden="true"></span>
        {{ valueLabel }}
      </span>
      <span v-if="hasLine && lineLabel" class="inline-flex items-center gap-1.5">
        <span class="inline-block h-0.5 w-4 bg-chart-2" aria-hidden="true"></span>
        {{ lineLabel }}
      </span>
    </figcaption>
  </figure>
</template>
