<script setup lang="ts">
import { computed, ref, toRef } from 'vue'

import {
  dayPoints,
  forecastDays,
  historyAgeDays,
  summarise,
  useIntervals,
  type ForecastVersion,
} from '@/entities/forecast'
import { problemMessage } from '@/shared/api'
import { formatDayLabel } from '@/shared/lib/datetime'
import IntervalChart from '@/shared/ui/IntervalChart.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'

const props = defineProps<{ version: ForecastVersion }>()

// A forecast built on data this much older than its first day is a rough guide, not a plan.
const STALE_AFTER_DAYS = 28

const intervals = useIntervals(computed(() => props.version.id))
const days = computed(() => forecastDays(props.version))
const dayOptions = computed(() => days.value.map((d) => ({ value: d, label: formatDayLabel(d) })))

const chosen = ref('')
const day = computed(() =>
  days.value.includes(chosen.value) ? chosen.value : (days.value[0] ?? ''),
)
const selectedDay = computed({
  get: () => day.value,
  set: (value: string) => (chosen.value = value),
})

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
      <div v-if="days.length > 0" class="w-44">
        <SelectField v-model="selectedDay" label="Day" :options="dayOptions" />
      </div>
    </div>

    <NoticeBox v-if="!version.assumptionsConfirmed" tone="warn" data-testid="assumptions-notice">
      The staffing assumptions for {{ version.queue }} are defaults that nobody has confirmed:
      {{ number('slTargetPct') }}% of calls answered within {{ number('slThresholdS') }} s, an
      occupancy ceiling of {{ number('occupancyCeilingPct') }}% and {{ number('shrinkagePct') }}%
      shrinkage. The agents-required figures rest on them.
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

    <p v-if="intervals.isPending.value" class="text-sm text-ink-muted">Loading…</p>
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
      <p class="text-xs text-ink-muted" data-testid="evidence">
        Forecast from the {{ evidence }} most recent earlier {{ evidence === 1 ? 'day' : 'days' }}
        with the same weekday that have call data. Agents to roster include
        {{ number('shrinkagePct') }}% shrinkage.
      </p>
    </template>
  </section>
</template>
