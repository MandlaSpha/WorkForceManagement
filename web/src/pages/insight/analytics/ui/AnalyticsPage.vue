<script setup lang="ts">
import { computed, ref } from 'vue'

import { useScorecard, type ScorecardItem } from '@/entities/scorecard'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import IntervalChart from '@/shared/ui/IntervalChart.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'analytics')

const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' })
const from = ref(new Date(Date.parse(today) - 27 * 86_400_000).toISOString().slice(0, 10))
const to = ref(today)
const card = useScorecard(from, to)

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
  return item.unit === '%' ? `${text}%` : item.unit === 'R' ? `R ${text}` : text
}

const unit = (item: ScorecardItem) =>
  ['s', 'half-hours', 'calls'].includes(item.unit) ? item.unit : ''

const points = computed(() =>
  (card.data.value?.days ?? []).map((d) => ({
    label: d.day.slice(5),
    bars: d.offered,
    line: d.serviceLevelPct,
  })),
)
</script>

<template>
  <PageHeader
    eyebrow="Insight"
    :title="screen?.label ?? 'Analytics'"
    :subtitle="screen?.subtitle"
  />

  <section class="space-y-4" aria-live="polite">
    <div class="flex flex-wrap gap-4 text-sm text-ink">
      <label class="flex items-center gap-2">
        From
        <input
          v-model="from"
          type="date"
          class="rounded-lg border border-line bg-surface px-2 py-1"
        />
      </label>
      <label class="flex items-center gap-2">
        To
        <input
          v-model="to"
          type="date"
          class="rounded-lg border border-line bg-surface px-2 py-1"
        />
      </label>
    </div>

    <NoticeBox v-if="from > to" tone="warn">The start date is after the end date.</NoticeBox>
    <p v-else-if="card.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="card.isError.value" tone="danger" data-testid="scorecard-error">
      Could not load the figures. {{ problemMessage(card.error.value) }}
    </NoticeBox>

    <template v-else-if="card.data.value">
      <ul class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="Figures">
        <li
          v-for="item in card.data.value.items"
          :key="item.key"
          class="rounded-xl border border-line bg-surface p-4"
          :data-testid="`item-${item.key}`"
        >
          <p class="flex items-center justify-between gap-2 text-xs text-ink-muted">
            {{ item.label }}
            <span
              class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
              :class="BASIS[item.basis]?.tone"
              data-testid="basis"
            >
              {{ BASIS[item.basis]?.label ?? item.basis }}
            </span>
          </p>
          <p class="mt-1 text-xl font-semibold tabular-nums text-ink" data-testid="value">
            {{ shown(item) }}
            <span
              v-if="item.value !== null && unit(item)"
              class="text-xs font-normal text-ink-muted"
            >
              {{ unit(item) }}
            </span>
          </p>
          <p v-if="item.note" class="mt-1 text-xs text-ink-muted">{{ item.note }}</p>
        </li>
      </ul>

      <section v-if="points.length > 0" aria-labelledby="trend-title" class="space-y-2">
        <h2 id="trend-title" class="text-sm font-semibold text-ink">
          Calls and service level by day
        </h2>
        <IntervalChart
          :points="points"
          summary="Calls offered each day as bars, and the service level as a line"
          bar-label="Calls offered"
          line-label="Service level (%)"
        />
      </section>
      <NoticeBox v-else data-testid="no-trend">No calls were measured in that range.</NoticeBox>
    </template>
  </section>
</template>
