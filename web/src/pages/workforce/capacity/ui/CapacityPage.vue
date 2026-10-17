<script setup lang="ts">
import { computed, ref } from 'vue'

import { dayStatus, figure, useCapacity, type CapacityDay } from '@/entities/workforce/capacity'
import { useContextStore } from '@/features/context-filters'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { formatDayLabel } from '@/shared/lib/datetime'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import SelectField from '@/shared/ui/SelectField.vue'

const context = useContextStore()
const screen = NAV_ITEMS.find((item) => item.key === 'capacity')

const horizon = ref('4')
const HORIZONS = [
  { value: '4', label: '4 weeks' },
  { value: '8', label: '8 weeks' },
  { value: '12', label: '12 weeks' },
]
const capacity = useCapacity(
  computed(() => context.weekStart),
  computed(() => Number(horizon.value)),
)

const STATUS_LABEL = {
  unknown: 'No forecast',
  permanent: 'Permanent staff cover it',
  seasonal: 'Needs seasonal agents',
  overflow: 'Beyond everyone',
} as const
const STATUS_CLASS = {
  unknown: 'text-ink-muted',
  permanent: 'text-ink',
  seasonal: 'text-brand-ink',
  overflow: 'font-semibold text-danger',
} as const

const limits = computed(() => capacity.data.value?.limits)
const total = computed(() =>
  limits.value ? limits.value.permanentLimit + limits.value.seasonalLimit : 0,
)
const weeks = computed(() => capacity.data.value?.weeks ?? [])
const anyForecast = computed(() => weeks.value.some((w) => w.daysForecast > 0))
const overflowDays = computed(() => weeks.value.reduce((sum, w) => sum + w.overflowDays, 0))
const seasonalPeak = computed(() => {
  const peaks = weeks.value.map((w) => w.seasonalPeak).filter((p): p is number => p !== null)
  return peaks.length > 0 ? Math.max(...peaks) : null
})
const peak = computed(() => {
  const peaks = weeks.value.map((w) => w.peak).filter((p): p is number => p !== null)
  return peaks.length > 0 ? Math.max(...peaks) : null
})
const incompleteDays = computed(() => weeks.value.reduce((sum, w) => sum + w.daysIncomplete, 0))

/** Width of each part of a day's bar as a share of the whole workforce, so days compare. */
function share(part: number | null): string {
  if (part === null || total.value === 0) return '0%'
  return `${Math.min(100, (part / total.value) * 100)}%`
}

function note(day: CapacityDay): string {
  if (day.queuesCovered === 0) return ''
  return day.complete
    ? ''
    : `At least this many: ${day.queuesCovered} of ${day.queuesTotal} queues have a forecast.`
}
</script>

<template>
  <PageHeader eyebrow="Operate" :title="screen?.label ?? 'Capacity'" :subtitle="screen?.subtitle">
    <template #actions>
      <div class="w-36">
        <SelectField v-model="horizon" label="Show" :options="HORIZONS" />
      </div>
    </template>
  </PageHeader>

  <section class="space-y-4" aria-live="polite">
    <p v-if="capacity.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="capacity.isError.value" tone="danger">
      Could not load capacity. {{ problemMessage(capacity.error.value) }}
    </NoticeBox>

    <template v-else-if="limits">
      <NoticeBox v-if="!limits.confirmed" tone="warn" data-testid="limits-notice">
        The pools below ({{ limits.permanentLimit }} permanent, {{ limits.seasonalLimit }} seasonal)
        are the tender's figures and nobody has confirmed them. An admin confirms them in Configure.
      </NoticeBox>
      <NoticeBox v-if="!anyForecast" data-testid="no-forecast">
        No queue has a published forecast for these weeks, so there is nothing to plan capacity
        from. Run and publish forecasts on the Forecast screen.
      </NoticeBox>
      <NoticeBox v-else-if="incompleteDays > 0" data-testid="incomplete-notice">
        {{ incompleteDays }} {{ incompleteDays === 1 ? 'day has' : 'days have' }} a forecast for
        only some queues, so the figure for {{ incompleteDays === 1 ? 'it is' : 'them is' }} a
        minimum.
      </NoticeBox>

      <ul class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Summary">
        <li class="rounded-xl border border-line bg-surface p-4" data-testid="kpi-peak">
          <p class="text-xs font-medium text-ink-muted">Most agents needed at once</p>
          <p class="mt-1 text-xl font-semibold tabular-nums text-ink">{{ figure(peak) }}</p>
          <p class="text-xs text-ink-muted">of {{ total }} in the workforce</p>
        </li>
        <li class="rounded-xl border border-line bg-surface p-4" data-testid="kpi-seasonal">
          <p class="text-xs font-medium text-ink-muted">Most seasonal agents needed</p>
          <p class="mt-1 text-xl font-semibold tabular-nums text-ink">{{ figure(seasonalPeak) }}</p>
          <p class="text-xs text-ink-muted">of {{ limits.seasonalLimit }} available</p>
        </li>
        <li class="rounded-xl border border-line bg-surface p-4" data-testid="kpi-overflow">
          <p class="text-xs font-medium text-ink-muted">Days beyond the workforce</p>
          <p class="mt-1 text-xl font-semibold tabular-nums text-ink">
            {{ anyForecast ? overflowDays : '\u2014' }}
          </p>
        </li>
        <li class="rounded-xl border border-line bg-surface p-4" data-testid="kpi-permanent">
          <p class="text-xs font-medium text-ink-muted">Permanent staff</p>
          <p class="mt-1 text-xl font-semibold tabular-nums text-ink">
            {{ limits.permanentLimit }}
          </p>
        </li>
      </ul>

      <div
        v-for="week in weeks"
        :key="week.weekStart"
        class="overflow-x-auto rounded-xl border border-line bg-surface"
      >
        <table
          class="w-full min-w-[46rem] text-left text-sm"
          :data-testid="`week-${week.weekStart}`"
        >
          <caption class="px-4 py-3 text-left text-sm font-semibold text-ink">
            Week of
            {{
              formatDayLabel(week.weekStart)
            }}
          </caption>
          <thead class="border-y border-line bg-surface-muted text-xs text-ink-muted">
            <tr>
              <th scope="col" class="px-4 py-2 font-medium">Day</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Needed at once</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Permanent</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Seasonal</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Overflow</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Seasonal engaged</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Still to find</th>
              <th scope="col" class="px-4 py-2 font-medium">Against the workforce</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="day in week.days"
              :key="day.day"
              class="border-b border-line"
              :class="STATUS_CLASS[dayStatus(day)]"
              :data-testid="`day-${day.day}`"
            >
              <th scope="row" class="px-4 py-2 font-medium">
                {{ formatDayLabel(day.day) }}
                <span v-if="note(day)" class="block text-xs font-normal text-ink-muted">{{
                  note(day)
                }}</span>
              </th>
              <td class="px-3 py-2 text-right tabular-nums" data-col="peak">
                {{ figure(day.peak) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="permanent">
                {{ figure(day.permanent) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="seasonal">
                {{ figure(day.seasonal) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="overflow">
                {{ figure(day.overflow) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="engaged">
                {{ day.seasonalOnBooks }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="hire">
                {{ figure(day.seasonalToHire) }}
              </td>
              <td class="px-4 py-2">
                <span class="sr-only">{{ STATUS_LABEL[dayStatus(day)] }}</span>
                <div
                  class="flex h-3 w-40 overflow-hidden rounded bg-surface-muted"
                  aria-hidden="true"
                >
                  <div class="bg-ink-muted" :style="{ width: share(day.permanent) }" />
                  <div class="bg-brand" :style="{ width: share(day.seasonal) }" />
                  <div class="bg-danger" :style="{ width: share(day.overflow) }" />
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-muted">
        <span class="inline-flex items-center gap-1"
          ><span class="inline-block h-2 w-3 rounded bg-ink-muted" />Permanent</span
        >
        <span class="inline-flex items-center gap-1"
          ><span class="inline-block h-2 w-3 rounded bg-brand" />Seasonal</span
        >
        <span class="inline-flex items-center gap-1"
          ><span class="inline-block h-2 w-3 rounded bg-danger" />Overflow</span
        >
        <span>
          Agents needed at once come from the published forecasts, shrinkage included. The bar is
          against all {{ total }} in the workforce.
        </span>
      </p>
    </template>
  </section>
</template>
