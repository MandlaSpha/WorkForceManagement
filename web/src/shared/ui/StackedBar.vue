<script setup lang="ts">
import { computed } from 'vue'

export interface BarSegment {
  key: string
  label: string
  value: number
  /** Token colour; the legend repeats the name and the number, so colour is never alone. */
  tone: 'chart-1' | 'chart-2' | 'chart-3' | 'chart-4' | 'ok' | 'danger'
  /** Diagonal hatching: for "not covered" or "unknown". */
  hatched?: boolean
}

const props = withDefaults(
  defineProps<{
    segments: ReadonlyArray<BarSegment>
    /** One sentence for people who cannot see the bar. */
    summary: string
    /** A labelled tick, `at` from 0 (start) to 1 (end), for example the current day. */
    marker?: { label: string; at: number } | null
    unit?: string
    emptyText?: string
  }>(),
  { marker: null, unit: '', emptyText: 'Nothing to show yet' },
)

const FILL = {
  'chart-1': 'var(--chart-1)',
  'chart-2': 'var(--chart-2)',
  'chart-3': 'var(--chart-3)',
  'chart-4': 'var(--chart-4)',
  ok: 'var(--ok)',
  danger: 'var(--danger)',
}

const total = computed(() => props.segments.reduce((s, x) => s + Math.max(0, x.value), 0))
const share = (v: number) => (total.value > 0 ? (Math.max(0, v) / total.value) * 100 : 0)
const markerAt = computed(() =>
  props.marker ? Math.min(1, Math.max(0, props.marker.at || 0)) * 100 : 0,
)
</script>

<template>
  <p v-if="total === 0" class="text-sm text-ink-muted" data-testid="stacked-empty">
    {{ emptyText }}
  </p>
  <figure v-else class="space-y-2" data-testid="stacked-bar">
    <div class="relative pt-5">
      <div
        v-if="marker"
        class="pointer-events-none absolute inset-y-0 z-10 flex -translate-x-1/2 flex-col items-center"
        :style="{ left: `${markerAt}%` }"
        data-testid="stacked-marker"
      >
        <span class="text-[11px] font-semibold text-ink">{{ marker.label }}</span>
        <span class="w-0.5 flex-1 rounded bg-ink" aria-hidden="true"></span>
      </div>
      <div
        class="flex h-4 w-full overflow-hidden rounded-full bg-surface-muted"
        role="img"
        :aria-label="summary"
      >
        <span
          v-for="s in segments"
          :key="s.key"
          class="stacked-seg block h-full"
          :class="s.hatched ? 'hatched' : ''"
          :style="{ width: `${share(s.value)}%`, '--seg': FILL[s.tone] }"
          :data-testid="`segment-${s.key}`"
        />
      </div>
    </div>
    <figcaption>
      <ul class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-muted">
        <li v-for="s in segments" :key="s.key" class="inline-flex items-center gap-1.5">
          <span
            class="inline-block size-3 rounded-sm"
            :class="s.hatched ? 'hatched' : ''"
            :style="{ '--seg': FILL[s.tone] }"
            aria-hidden="true"
          ></span>
          {{ s.label }}:
          <span class="font-semibold tabular-nums text-ink"
            >{{ s.value.toLocaleString('en-ZA') }}{{ unit ? ` ${unit}` : '' }}</span
          >
        </li>
      </ul>
    </figcaption>
  </figure>
</template>
