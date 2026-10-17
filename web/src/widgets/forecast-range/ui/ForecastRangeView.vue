<script setup lang="ts">
import { computed } from 'vue'

import {
  rangeFor,
  step,
  useRange,
  type ForecastVersion,
  type ForecastView,
} from '@/entities/forecast'
import { problemMessage } from '@/shared/api'
import { formatDayLabel } from '@/shared/lib/datetime'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

import MonthView from './MonthView.vue'
import WeekView from './WeekView.vue'

const props = defineProps<{
  version: ForecastVersion
  view: Exclude<ForecastView, 'day'>
  anchor: string
}>()
const emit = defineEmits<{ 'update:anchor': [day: string]; open: [day: string] }>()

const range = computed(() => rangeFor(props.view, props.anchor))
// The heat-grid needs every half-hour of the week; the month needs only the daily totals.
const query = useRange(
  computed(() => props.version.id),
  computed(() => range.value.from),
  computed(() => range.value.to),
  computed(() => props.view === 'week'),
)
const data = computed(() => query.data.value)

const MONTH = new Intl.DateTimeFormat('en-ZA', { timeZone: 'UTC', month: 'long', year: 'numeric' })
const heading = computed(() =>
  props.view === 'week'
    ? `Week of ${formatDayLabel(range.value.from)}`
    : MONTH.format(new Date(`${props.anchor.slice(0, 7)}-01T12:00:00Z`)),
)

// What the figures rest on, in words (never a number without its source).
const STATUS: Record<string, string> = {
  published: 'the published (live) forecast',
  draft: 'a draft that is not live',
  archived: 'an archived forecast that is no longer live',
}
const basis = computed(() => {
  const label = props.version.label || 'unlabelled'
  return `${props.version.queue}, version "${label}", ${STATUS[data.value?.status ?? props.version.status] ?? ''}`
})

const missing = computed(() => (data.value?.days ?? []).filter((d) => !d.hasForecast))
const outside = computed(() => missing.value.filter((d) => d.reason === 'outside_version').length)
const noHistory = computed(() => missing.value.filter((d) => d.reason === 'no_history').length)
const total = computed(() => data.value?.days.length ?? 0)
const covered = computed(
  () =>
    `${formatDayLabel(props.version.dateFrom)}` +
    (props.version.dateTo === props.version.dateFrom
      ? ''
      : ` to ${formatDayLabel(props.version.dateTo)}`),
)
</script>

<template>
  <section class="space-y-4" :aria-label="`${view === 'week' ? 'Week' : 'Month'} view`">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3 class="text-base font-semibold text-ink" data-testid="range-heading">{{ heading }}</h3>
      <div class="flex gap-2">
        <AppButton
          variant="secondary"
          :aria-label="view === 'week' ? 'Previous week' : 'Previous month'"
          @click="emit('update:anchor', step(view, anchor, -1))"
        >
          Previous
        </AppButton>
        <AppButton
          variant="secondary"
          :aria-label="view === 'week' ? 'Next week' : 'Next month'"
          @click="emit('update:anchor', step(view, anchor, 1))"
        >
          Next
        </AppButton>
      </div>
    </div>

    <p class="text-xs text-ink-muted" data-testid="range-basis">Based on {{ basis }}.</p>

    <p v-if="query.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="query.isError.value" tone="danger">
      Could not load this {{ view }}. {{ problemMessage(query.error.value) }}
    </NoticeBox>

    <template v-else-if="data">
      <NoticeBox v-if="missing.length === total" tone="warn" data-testid="no-forecast-notice">
        This forecast has nothing for any day shown. It covers {{ covered }}; use Previous and Next
        to find those days.
      </NoticeBox>
      <NoticeBox v-else-if="missing.length > 0" data-testid="partial-notice">
        {{ missing.length }} of {{ total }} days have no forecast and show no figures.
        <template v-if="outside > 0">
          {{ outside }} fall outside the days this forecast covers ({{ covered }}).
        </template>
        <template v-if="noHistory > 0">
          {{ noHistory }} could not be forecast: no earlier day with the same weekday has call data.
        </template>
      </NoticeBox>

      <WeekView v-if="view === 'week'" :range="data" @open="emit('open', $event)" />
      <MonthView v-else :range="data" :anchor="anchor" @open="emit('open', $event)" />
    </template>
  </section>
</template>
