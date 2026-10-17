<script setup lang="ts">
import { computed, toRef } from 'vue'

import {
  changeLabel,
  dayPoints,
  forecastDays,
  historyAgeDays,
  summarise,
  useIntervals,
  type ForecastVersion,
  type ForecastView,
} from '@/entities/forecast'
import { problemMessage } from '@/shared/api'
import { formatDayLabel } from '@/shared/lib/datetime'
import { ForecastRangeView } from '@/widgets/forecast-range'
import IntervalChart from '@/shared/ui/IntervalChart.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'

const props = defineProps<{ version: ForecastVersion; view: ForecastView; anchor: string }>()
// One event for both: the page keeps the view and the day together in the address.
const emit = defineEmits<{ change: [view: ForecastView, anchor: string] }>()

const VIEWS: Array<{ key: ForecastView; label: string }> = [
  { key: 'day', label: 'Day' },
  { key: 'week', label: 'Week' },
  { key: 'month', label: 'Month' },
]

// A forecast built on data this much older than its first day is a rough guide, not a plan.
const STALE_AFTER_DAYS = 28

// The half-hours are only needed for the day view; the week and month ask for their own totals.
const intervals = useIntervals(computed(() => (props.view === 'day' ? props.version.id : null)))
const days = computed(() => forecastDays(props.version))
const dayOptions = computed(() => days.value.map((d) => ({ value: d, label: formatDayLabel(d) })))

const day = computed(() =>
  days.value.includes(props.anchor) ? props.anchor : (days.value[0] ?? ''),
)
const selectedDay = computed({
  get: () => day.value,
  set: (value: string) => emit('change', 'day', value),
})
// The week and month may be looked at for any date, also outside the days this version covers.
const rangeAnchor = computed(() => props.anchor || day.value || props.version.dateFrom)
const setView = (view: ForecastView): void =>
  emit('change', view, view === 'day' ? day.value : rangeAnchor.value)

const points = computed(() => dayPoints(intervals.data.value ?? [], day.value))
const summary = computed(() => summarise(points.value))
const chartPoints = computed(() =>
  points.value.map((p) => ({ label: p.label, bars: p.volume, line: p.required })),
)

const number = (key: string): number => Number(props.version.params[key])
const age = computed(() => historyAgeDays(props.version))
const stale = computed(() => age.value !== null && age.value >= STALE_AFTER_DAYS)
const evidence = computed(() => points.value[0]?.daysUsed ?? 0)
const missingDays = toRef(() => props.version.daysWithoutHistory)

// Which model made this forecast, and when Prophet was asked for but not used, why (ADR 0002).
// Events that adjusted the chosen day, recorded on the version when it was run.
const appliedEvents = computed(() => {
  const all = (props.version.params.events ?? []) as Array<{
    name: string
    upliftPct: number
    days: string[]
  }>
  return all.filter((e) => e.days.includes(day.value))
})
const usedProphet = computed(() => props.version.method.startsWith('prophet'))
const fallbackMessage = computed(() => {
  const message = props.version.fallback?.message
  return typeof message === 'string' ? message : null
})
const backtest = computed(() => {
  const b = props.version.params.backtest as Record<string, unknown> | undefined
  return b && typeof b.prophetDailyPct === 'number' && typeof b.baselineDailyPct === 'number'
    ? { prophet: b.prophetDailyPct, baseline: b.baselineDailyPct, days: Number(b.daysScored) }
    : null
})

const chartSummary = computed(
  () =>
    `Expected calls per half-hour and agents to roster, ${formatDayLabel(day.value)}. ` +
    (summary.value.peak
      ? `Busiest half-hour ${summary.value.peak.label} with ${summary.value.peak.volume.toFixed(1)} calls.`
      : 'No calls expected.'),
)
</script>

<template>
  <section class="space-y-4" aria-labelledby="detail-title">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <h2 id="detail-title" class="text-base font-semibold text-ink">
        {{ version.queue }}: {{ version.label || 'forecast' }}
      </h2>
      <div class="flex flex-wrap items-end gap-3">
        <div role="group" aria-label="Show" class="inline-flex rounded-lg border border-line">
          <button
            v-for="v in VIEWS"
            :key="v.key"
            type="button"
            class="min-h-10 px-3 text-sm font-medium first:rounded-l-lg last:rounded-r-lg"
            :class="
              view === v.key
                ? 'bg-brand text-brand-contrast'
                : 'bg-surface text-ink hover:bg-surface-muted'
            "
            :aria-pressed="view === v.key"
            @click="setView(v.key)"
          >
            {{ v.label }}
          </button>
        </div>
        <div v-if="view === 'day' && days.length > 0" class="w-44">
          <SelectField v-model="selectedDay" label="Day" :options="dayOptions" />
        </div>
      </div>
    </div>

    <NoticeBox v-if="!version.assumptionsConfirmed" tone="warn" data-testid="assumptions-notice">
      The staffing assumptions for {{ version.queue }} are defaults that nobody has confirmed:
      {{ number('slTargetPct') }}% of calls answered within {{ number('slThresholdS') }} s, an
      occupancy ceiling of {{ number('occupancyCeilingPct') }}% and {{ number('shrinkagePct') }}%
      shrinkage. The agents-required figures rest on them.
    </NoticeBox>

    <NoticeBox v-if="fallbackMessage" data-testid="fallback-notice">
      This forecast uses the baseline, not Prophet. {{ fallbackMessage }}
    </NoticeBox>

    <NoticeBox v-if="appliedEvents.length > 0" data-testid="events-notice">
      Adjusted for:
      {{ appliedEvents.map((e) => `${e.name} (${changeLabel(e.upliftPct)})`).join(', ') }}.
    </NoticeBox>

    <NoticeBox v-if="stale" tone="warn" data-testid="stale-notice">
      The newest call data is from {{ version.historyThrough }}, {{ age }} days before the first day
      of this forecast. Treat it as a rough guide, and import newer data to improve it.
    </NoticeBox>

    <NoticeBox v-if="missingDays.length > 0" data-testid="missing-days-notice">
      {{ missingDays.length }} {{ missingDays.length === 1 ? 'day was' : 'days were' }} left out: no
      earlier day with the same weekday has call data to forecast from ({{
        missingDays.map(formatDayLabel).join(', ')
      }}).
    </NoticeBox>

    <ForecastRangeView
      v-if="view !== 'day'"
      :version="version"
      :view="view"
      :anchor="rangeAnchor"
      @update:anchor="emit('change', view, $event)"
      @open="emit('change', 'day', $event)"
    />
    <p v-else-if="intervals.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="intervals.isError.value" tone="danger">
      Could not load this forecast. {{ problemMessage(intervals.error.value) }}
    </NoticeBox>

    <template v-else-if="days.length > 0">
      <dl class="grid gap-3 sm:grid-cols-3">
        <div class="rounded-xl border border-line bg-surface p-3">
          <dt class="text-xs text-ink-muted">Expected calls</dt>
          <dd class="text-xl font-semibold tabular-nums text-ink" data-testid="total-calls">
            {{ summary.totalVolume.toFixed(1) }}
          </dd>
          <dd
            v-if="summary.totalLower !== null && summary.totalUpper !== null"
            class="text-xs tabular-nums text-ink-muted"
            data-testid="total-range"
          >
            80% range {{ summary.totalLower.toFixed(0) }} to {{ summary.totalUpper.toFixed(0) }}
          </dd>
        </div>
        <div class="rounded-xl border border-line bg-surface p-3">
          <dt class="text-xs text-ink-muted">Busiest half-hour</dt>
          <dd class="text-xl font-semibold tabular-nums text-ink" data-testid="peak">
            <template v-if="summary.peak">
              {{ summary.peak.label }} · {{ summary.peak.volume.toFixed(1) }} calls
            </template>
            <template v-else>None</template>
          </dd>
        </div>
        <div class="rounded-xl border border-line bg-surface p-3">
          <dt class="text-xs text-ink-muted">Most agents to roster</dt>
          <dd class="text-xl font-semibold tabular-nums text-ink" data-testid="max-required">
            {{ summary.maxRequired ?? '—' }}
          </dd>
        </div>
      </dl>

      <IntervalChart
        :points="chartPoints"
        :summary="chartSummary"
        bar-label="Expected calls"
        line-label="Agents to roster"
      />
      <p v-if="usedProphet && backtest" class="text-xs text-ink-muted" data-testid="model">
        Model: Prophet. On {{ backtest.days }} past days it predicted the day's total
        {{ backtest.prophet.toFixed(1) }}% right, against {{ backtest.baseline.toFixed(1) }}% for
        the baseline, which is why it was used. It forecasts each day's total; the total is then
        spread over the half-hours in the shape of recent days.
      </p>
      <p class="text-xs text-ink-muted" data-testid="evidence">
        Daily shape from the {{ evidence }} most recent earlier
        {{ evidence === 1 ? 'day' : 'days' }} with the same weekday that have call data. Agents to
        roster include {{ number('shrinkagePct') }}% shrinkage.
      </p>
    </template>
  </section>
</template>
