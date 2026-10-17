<script setup lang="ts">
import { computed } from 'vue'

import type { ForecastRange } from '@/entities/forecast'
import { formatDayLabel } from '@/shared/lib/datetime'
import IntervalChart from '@/shared/ui/IntervalChart.vue'

import HeatGrid from './HeatGrid.vue'

const props = defineProps<{ range: ForecastRange }>()
const emit = defineEmits<{ open: [day: string] }>()

// A day with no forecast has no bar and no line point: a gap, never a zero.
const points = computed(() =>
  props.range.days.map((d) => ({
    label: formatDayLabel(d.day),
    bars: d.calls,
    line: d.peakRequired,
  })),
)
const summary = computed(
  () =>
    `Expected calls per day and the most agents needed at once, ${formatDayLabel(props.range.dateFrom)} to ${formatDayLabel(props.range.dateTo)}.`,
)
const incomplete = computed(() => props.range.days.some((d) => d.hasForecast && !d.complete))

const seconds = (n: number | null): string => (n === null ? '—' : `${Math.round(n)} s`)
const mark = (day: string): 'busiest' | 'quietest' | null =>
  day === props.range.busiestDay ? 'busiest' : day === props.range.quietestDay ? 'quietest' : null
</script>

<template>
  <div class="space-y-4">
    <IntervalChart
      :points="points"
      :summary="summary"
      bar-label="Expected calls"
      line-label="Most agents at once"
      category-label="Day"
      :label-every="1"
    />

    <div class="overflow-x-auto rounded-xl border border-line bg-surface">
      <table class="w-full min-w-[36rem] text-left text-sm" data-testid="week-table">
        <caption class="px-4 py-3 text-left text-sm font-semibold text-ink">
          The week, day by day
        </caption>
        <thead class="border-y border-line bg-surface-muted text-xs text-ink-muted">
          <tr>
            <th scope="col" class="px-4 py-2 font-medium">Day</th>
            <th scope="col" class="px-3 py-2 text-right font-medium">Calls</th>
            <th scope="col" class="px-3 py-2 text-right font-medium">Handling time</th>
            <th scope="col" class="px-3 py-2 text-right font-medium">People at the peak</th>
            <th scope="col" class="px-3 py-2 text-right font-medium">Agent-hours</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in range.days" :key="d.day" class="border-b border-line">
            <th scope="row" class="px-4 py-2 font-normal">
              <button
                type="button"
                class="font-medium text-brand-ink underline"
                :aria-label="`Open ${formatDayLabel(d.day)} in the day view`"
                @click="emit('open', d.day)"
              >
                {{ formatDayLabel(d.day) }}
              </button>
              <span
                v-if="mark(d.day)"
                class="ml-2 rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-semibold text-ink-muted"
                >{{ mark(d.day) === 'busiest' ? 'Busiest' : 'Quietest' }}</span
              >
            </th>
            <template v-if="d.hasForecast">
              <td class="px-3 py-2 text-right tabular-nums">{{ (d.calls ?? 0).toFixed(1) }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ seconds(d.ahtS) }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ d.peakRequired ?? '—' }}</td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ d.hoursRequired === null ? '—' : d.hoursRequired.toFixed(1) }}
              </td>
            </template>
            <td v-else colspan="4" class="px-3 py-2 text-ink-muted">No forecast for this day</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="incomplete" class="text-xs text-ink-muted" data-testid="incomplete-note">
      A dash in the people columns means a half-hour with calls could not be staffed, so no peak or
      total is claimed for that day.
    </p>

    <HeatGrid :days="range.days" @open="emit('open', $event)" />
  </div>
</template>
