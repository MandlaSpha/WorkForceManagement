<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { scorecardCsvUrl, useScorecard, type ScorecardItem } from '@/entities/scorecard'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { formatDayLabel } from '@/shared/lib/datetime'
import IntervalChart from '@/shared/ui/IntervalChart.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import StatTile from '@/shared/ui/StatTile.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'analytics')

const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' })
const dayBefore = (n: number) =>
  new Date(Date.parse(today) - n * 86_400_000).toISOString().slice(0, 10)

const PRESETS = [
  { key: '7', label: 'Last 7 days', back: 6 },
  { key: '28', label: 'Last 28 days', back: 27 },
  { key: '90', label: 'Last 90 days', back: 89 },
] as const
const choice = ref<string>('28')
const from = ref(dayBefore(27))
const to = ref(today)
watch(choice, (key) => {
  const preset = PRESETS.find((p) => p.key === key)
  if (!preset) return
  from.value = dayBefore(preset.back)
  to.value = today
})
const card = useScorecard(from, to)
const csvUrl = computed(() => scorecardCsvUrl(from.value, to.value))

const BASIS: Record<string, { label: string; tone: string }> = {
  measured: { label: 'Measured', tone: 'bg-brand-soft text-brand-ink' },
  modelled: { label: 'Modelled', tone: 'bg-warn-soft text-warn' },
  needs_data: { label: 'Needs data', tone: 'bg-surface-muted text-ink-muted' },
}

/** "-" for a figure with nothing behind it, never 0. */
function shown(item: ScorecardItem): string {
  if (item.value === null) return '-'
  const n = item.unit === 's' || item.unit === 'calls' || item.unit === 'half-hours' ? 0 : 1
  const text = item.value.toLocaleString('en-ZA', {
    minimumFractionDigits: n,
    maximumFractionDigits: n,
  })
  const withUnit = item.unit === '%' ? `${text}%` : item.unit === 'R' ? `R ${text}` : text
  return ['s', 'half-hours', 'calls'].includes(item.unit) ? `${withUnit} ${item.unit}` : withUnit
}

const items = computed(() => card.data.value?.items ?? [])
const known = computed(() => items.value.filter((i) => i.value !== null))
const missing = computed(() => items.value.length - known.value.length)
/** The sentence under the title quotes the first figures that really exist. */
const lead = computed(() => known.value.slice(0, 2))

const days = computed(() => card.data.value?.days ?? [])
const points = computed(() =>
  days.value.map((d) => ({
    label: d.day.slice(5),
    bars: d.offered,
    line: d.serviceLevelPct,
  })),
)
const totalCalls = computed(() => days.value.reduce((sum, d) => sum + d.offered, 0))
</script>

<template>
  <PageHeader eyebrow="Insight" :title="screen?.label ?? 'Analytics'">
    <template #subtitle>
      <template v-if="card.data.value && known.length > 0">
        {{ formatDayLabel(card.data.value.dateFrom) }} to
        {{ formatDayLabel(card.data.value.dateTo) }}:
        <template v-for="(item, i) in lead" :key="item.key"
          >{{ i > 0 ? ', ' : '' }}{{ item.label.toLowerCase() }}
          <strong class="font-semibold text-ink">{{ shown(item) }}</strong></template
        ><template v-if="missing > 0"
          >; {{ missing }} {{ missing === 1 ? 'figure needs' : 'figures need' }} more
          data.</template
        ><template v-else>.</template>
      </template>
      <template v-else-if="card.data.value">
        Nothing was measured in that range, so no figure is shown.
      </template>
      <template v-else>{{ screen?.subtitle }}</template>
    </template>
  </PageHeader>

  <section class="space-y-6" aria-live="polite">
    <div class="flex flex-wrap items-center gap-3">
      <div
        class="inline-flex flex-wrap gap-1 rounded-xl border border-line bg-surface p-1"
        role="group"
        aria-label="Range"
        data-testid="analytics-range"
      >
        <button
          v-for="p in PRESETS"
          :key="p.key"
          type="button"
          class="press rounded-lg px-3 py-1.5 text-sm"
          :class="
            choice === p.key ? 'bg-brand text-brand-contrast' : 'text-ink hover:bg-surface-muted'
          "
          :aria-pressed="choice === p.key"
          @click="choice = p.key"
        >
          {{ p.label }}
        </button>
        <button
          type="button"
          class="press rounded-lg px-3 py-1.5 text-sm"
          :class="
            choice === 'custom' ? 'bg-brand text-brand-contrast' : 'text-ink hover:bg-surface-muted'
          "
          :aria-pressed="choice === 'custom'"
          @click="choice = 'custom'"
        >
          Custom
        </button>
      </div>
      <template v-if="choice === 'custom'">
        <label class="flex items-center gap-2 text-sm text-ink">
          From
          <input
            v-model="from"
            type="date"
            class="rounded-lg border border-line bg-surface px-2 py-1"
          />
        </label>
        <label class="flex items-center gap-2 text-sm text-ink">
          To
          <input
            v-model="to"
            type="date"
            class="rounded-lg border border-line bg-surface px-2 py-1"
          />
        </label>
      </template>
      <a
        v-if="from <= to"
        :href="csvUrl"
        download
        class="ml-auto text-sm font-medium text-brand-ink underline"
        data-testid="scorecard-csv"
      >
        Download as CSV
      </a>
    </div>

    <NoticeBox v-if="from > to" tone="warn">The start date is after the end date.</NoticeBox>
    <div v-else-if="card.isPending.value" class="space-y-4" data-testid="analytics-loading">
      <span class="sr-only">Loading…</span>
      <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div v-for="n in 4" :key="n" class="skeleton h-28"></div>
      </div>
      <div class="skeleton h-56"></div>
    </div>
    <NoticeBox v-else-if="card.isError.value" tone="danger" data-testid="scorecard-error">
      Could not load the figures. {{ problemMessage(card.error.value) }}
    </NoticeBox>

    <template v-else-if="card.data.value">
      <ul
        class="page-enter grid grid-cols-2 gap-3 lg:grid-cols-4"
        aria-label="Figures"
        data-testid="analytics-tiles"
      >
        <StatTile
          v-for="(item, i) in items"
          :key="item.key"
          :variant="i === 0 && item.value !== null ? 'feature' : 'default'"
          :label="item.label"
          :value="shown(item)"
          :data-testid="`item-${item.key}`"
        >
          <span
            class="inline-block rounded-full px-2 py-0.5 text-[11px] font-semibold"
            :class="BASIS[item.basis]?.tone"
            data-testid="basis"
          >
            {{ BASIS[item.basis]?.label ?? item.basis }}
          </span>
          <span v-if="item.note" class="mt-1 block">{{ item.note }}</span>
        </StatTile>
      </ul>

      <section
        v-if="points.length > 0"
        class="page-enter rounded-2xl border border-line bg-surface p-4 shadow-card"
        aria-labelledby="trend-title"
      >
        <h2 id="trend-title" class="text-sm font-semibold text-ink">
          Calls and service level by day
        </h2>
        <p class="mt-1 text-xs text-ink-muted">
          {{ totalCalls.toLocaleString('en-ZA') }} calls over {{ points.length }}
          {{ points.length === 1 ? 'day' : 'days' }} with calls. A day with no service level has no
          point on the line.
        </p>
        <div class="mt-3">
          <IntervalChart
            :points="points"
            summary="Calls offered each day as bars, and the service level as a line"
            bar-label="Calls offered"
            line-label="Service level (%)"
          />
        </div>
      </section>
      <NoticeBox v-else data-testid="no-trend">No calls were measured in that range.</NoticeBox>

      <section
        v-if="days.length > 0"
        class="page-enter overflow-hidden rounded-2xl border border-line bg-surface shadow-card"
        aria-labelledby="numbers-title"
        data-testid="analytics-numbers"
      >
        <h2 id="numbers-title" class="px-4 pt-4 text-sm font-semibold text-ink">The numbers</h2>
        <div class="mt-2 overflow-x-auto">
          <table class="w-full min-w-[22rem] text-left text-sm">
            <thead class="border-y border-line bg-surface-muted text-xs text-ink-muted">
              <tr>
                <th scope="col" class="px-4 py-2 font-medium">Day</th>
                <th scope="col" class="px-3 py-2 text-right font-medium">Calls offered</th>
                <th scope="col" class="px-4 py-2 text-right font-medium">Service level</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in days" :key="d.day" class="border-b border-line last:border-0">
                <th scope="row" class="px-4 py-2 font-medium">{{ formatDayLabel(d.day) }}</th>
                <td class="px-3 py-2 text-right tabular-nums">
                  {{ d.offered.toLocaleString('en-ZA') }}
                </td>
                <td class="px-4 py-2 text-right tabular-nums">
                  {{ d.serviceLevelPct === null ? '-' : `${d.serviceLevelPct.toFixed(1)}%` }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </section>
</template>
