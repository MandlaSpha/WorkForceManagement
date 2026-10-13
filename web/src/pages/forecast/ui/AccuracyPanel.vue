<script setup lang="ts">
import { computed } from 'vue'

import { useAccuracy } from '@/entities/forecast'
import { problemMessage } from '@/shared/api'
import { formatDayLabel } from '@/shared/lib/datetime'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

const props = defineProps<{ queueId: number }>()
const accuracy = useAccuracy(computed(() => props.queueId))
const pct = (value: number | null) => (value === null ? '—' : `${value.toFixed(1)}%`)
</script>

<template>
  <section class="space-y-3" aria-labelledby="accuracy-title">
    <h2 id="accuracy-title" class="text-base font-semibold text-ink">Forecast accuracy</h2>
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
      <p class="text-xs text-ink-muted">
        Measured on real calls: each day is forecast from only the days before it, using the
        {{ accuracy.data.value.weeks }} most recent same-weekday days, then compared with what
        happened. Accuracy is 100% minus the total error as a share of total calls. The half-hour
        figure is always lower, and much lower for a small queue, where a half-hour holds only a
        call or two and chance alone moves it. Judge staffing for the day by the day figure.
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
