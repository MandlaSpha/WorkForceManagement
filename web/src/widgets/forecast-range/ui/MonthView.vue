<script setup lang="ts">
import { computed } from 'vue'

import { monthOf, type ForecastRange, type RangeDay } from '@/entities/forecast'
import { formatDayLabel } from '@/shared/lib/datetime'

const props = defineProps<{ range: ForecastRange; anchor: string }>()
const emit = defineEmits<{ open: [day: string] }>()

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const month = computed(() => monthOf(props.anchor).month)
const cells = computed(() =>
  props.range.days.map((d) => ({
    d,
    inMonth: d.day.startsWith(month.value),
    events: props.range.events.filter((e) => e.dateFrom <= d.day && d.day <= e.dateTo),
  })),
)

function describe(d: RangeDay, events: string[]): string {
  const when = formatDayLabel(d.day)
  const extra = events.length > 0 ? `. Events: ${events.join(', ')}` : ''
  if (!d.hasForecast) return `${when}: no forecast${extra}`
  const people =
    d.peakRequired === null ? 'most people at once not known' : `${d.peakRequired} people at peak`
  return `${when}: ${(d.calls ?? 0).toFixed(0)} calls, ${people}${extra}`
}
const mark = (day: string): string | null =>
  day === props.range.busiestDay ? 'Busiest' : day === props.range.quietestDay ? 'Quietest' : null
</script>

<template>
  <div class="space-y-2">
    <div class="overflow-x-auto">
      <div class="grid min-w-[40rem] grid-cols-7 gap-1" data-testid="month-grid">
        <div
          v-for="w in WEEKDAYS"
          :key="w"
          class="px-1 text-xs font-medium text-ink-muted"
          aria-hidden="true"
        >
          {{ w }}
        </div>
        <button
          v-for="{ d, inMonth, events } in cells"
          :key="d.day"
          type="button"
          class="min-h-24 rounded-lg border p-2 text-left text-xs transition-colors hover:bg-surface-muted"
          :class="[
            inMonth ? 'border-line bg-surface' : 'border-line/50 bg-surface-muted/40',
            mark(d.day) === 'Busiest' ? 'ring-2 ring-danger' : '',
            mark(d.day) === 'Quietest' ? 'ring-2 ring-brand' : '',
          ]"
          :aria-label="
            describe(
              d,
              events.map((e) => e.name),
            )
          "
          :data-day="d.day"
          @click="emit('open', d.day)"
        >
          <span class="flex items-center justify-between">
            <span class="font-semibold text-ink">{{ Number(d.day.slice(8)) }}</span>
            <span
              v-if="mark(d.day)"
              class="rounded-full bg-surface-muted px-1.5 text-[10px] font-semibold"
              :class="mark(d.day) === 'Busiest' ? 'text-danger' : 'text-brand-ink'"
              >{{ mark(d.day) }}</span
            >
          </span>
          <template v-if="d.hasForecast">
            <span class="mt-1 block tabular-nums text-ink"
              >{{ (d.calls ?? 0).toFixed(0) }} calls</span
            >
            <span class="block tabular-nums text-ink-muted">
              <template v-if="d.peakRequired !== null"
                >{{ d.peakRequired }} people at peak</template
              >
              <template v-else>people: not known</template>
            </span>
          </template>
          <span v-else class="mt-1 block text-ink-muted">No forecast</span>
          <span
            v-for="e in events"
            :key="e.name"
            class="mt-1 block truncate rounded bg-warn-soft px-1 text-[10px] text-warn"
            >{{ e.name }}</span
          >
        </button>
      </div>
    </div>
    <p class="text-xs text-ink-muted" data-testid="holiday-note">
      Events from the Events tab are shown on the days they cover. Public holidays are not recorded
      in the system yet, so they are not marked.
    </p>
  </div>
</template>
