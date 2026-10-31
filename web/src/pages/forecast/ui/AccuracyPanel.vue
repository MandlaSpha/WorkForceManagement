<script setup lang="ts">
import { computed, ref } from 'vue'

import { biasLabel, useAccuracy, type ForecastMethod } from '@/entities/forecast'
import { problemMessage } from '@/shared/api'
import { formatDayLabel } from '@/shared/lib/datetime'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

const props = defineProps<{ queueId: number }>()
const MODELS: ReadonlyArray<{ value: ForecastMethod; label: string }> = [
  { value: 'baseline', label: 'Baseline' },
  { value: 'smoothed', label: 'Smoothed' },
]
const method = ref<ForecastMethod>('baseline')
const accuracy = useAccuracy(
  computed(() => props.queueId),
  method,
)
const pct = (value: number | null) => (value === null ? '—' : `${value.toFixed(1)}%`)
</script>

<template>
  <section class="space-y-3" aria-labelledby="accuracy-title">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <h2 id="accuracy-title" class="text-base font-semibold text-ink">Forecast accuracy</h2>
      <div role="group" aria-label="Model" class="inline-flex rounded-lg border border-line">
        <button
          v-for="m in MODELS"
          :key="m.value"
          type="button"
          class="min-h-10 px-3 text-sm font-medium first:rounded-l-lg last:rounded-r-lg"
          :class="
            method === m.value
              ? 'bg-brand text-brand-contrast'
              : 'bg-surface text-ink hover:bg-surface-muted'
          "
          :aria-pressed="method === m.value"
          @click="method = m.value"
        >
          {{ m.label }}
        </button>
      </div>
    </div>
    <p v-if="method === 'smoothed'" class="text-sm text-ink-muted" data-testid="smoothed-note">
      Smoothed blends the recent same weekdays with the usual level of weekdays and pools the shape
      of the day, so one odd day moves it less. Compare it with the baseline on the same days.
    </p>
    <p v-if="accuracy.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="accuracy.isError.value" tone="danger">
      Could not load the accuracy. {{ problemMessage(accuracy.error.value) }}
    </NoticeBox>
    <NoticeBox v-else-if="(accuracy.data.value?.days ?? []).length === 0">
      Not enough call data yet to check the forecast against what happened. It needs at least two
      days with the same weekday.
    </NoticeBox>
    <template v-else-if="accuracy.data.value">
      <dl class="grid gap-3 sm:grid-cols-2">
        <div class="rounded-xl border border-line bg-surface p-3">
          <dt class="text-xs text-ink-muted">Each day's total calls</dt>
          <dd class="text-xl font-semibold tabular-nums text-ink" data-testid="accuracy-daily">
            {{ pct(accuracy.data.value.overallDailyAccuracyPct) }}
          </dd>
        </div>
        <div class="rounded-xl border border-line bg-surface p-3">
          <dt class="text-xs text-ink-muted">Each half-hour</dt>
          <dd class="text-xl font-semibold tabular-nums text-ink" data-testid="accuracy-interval">
            {{ pct(accuracy.data.value.overallAccuracyPct) }}
          </dd>
        </div>
      </dl>
      <p class="text-sm text-ink" data-testid="accuracy-days">
        Over {{ accuracy.data.value.days.length }} past
        {{ accuracy.data.value.days.length === 1 ? 'day' : 'days' }}.
      </p>
      <p class="text-sm text-ink" data-testid="accuracy-bias">
        Bias: {{ biasLabel(accuracy.data.value.biasPct) }}. Whether forecasts run high or low is
        tuned on the Calibration screen.
      </p>
      <details class="text-sm">
        <summary class="cursor-pointer text-brand-ink">Show each day</summary>
        <div class="mt-2 max-h-72 overflow-auto rounded-xl border border-line">
          <table class="w-full text-left text-sm">
            <thead class="sticky top-0 bg-surface-muted text-xs text-ink-muted">
              <tr>
                <th scope="col" class="px-3 py-1.5 font-medium">Day</th>
                <th scope="col" class="px-3 py-1.5 text-right font-medium">Day total</th>
                <th scope="col" class="px-3 py-1.5 text-right font-medium">Half-hours</th>
                <th scope="col" class="px-3 py-1.5 text-right font-medium">Days used</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in accuracy.data.value.days" :key="d.date" class="border-t border-line">
                <th scope="row" class="px-3 py-1 font-normal">{{ formatDayLabel(d.date) }}</th>
                <td class="px-3 py-1 text-right tabular-nums">{{ pct(d.dailyAccuracyPct) }}</td>
                <td class="px-3 py-1 text-right tabular-nums">{{ pct(d.accuracyPct) }}</td>
                <td class="px-3 py-1 text-right tabular-nums">{{ d.daysUsed }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </template>
  </section>
</template>
