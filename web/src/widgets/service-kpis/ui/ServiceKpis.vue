<script setup lang="ts">
import { computed } from 'vue'

import {
  formatCount,
  formatDuration,
  formatPercent,
  formatSeconds,
  type KpiSummary,
} from '@/entities/call-data'
import { canOpen, useSessionStore } from '@/entities/session'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import StatTile from '@/shared/ui/StatTile.vue'

import AttentionCard from './AttentionCard.vue'
import ServiceTrend from './ServiceTrend.vue'

const props = defineProps<{
  summary: KpiSummary
  periodLabel: string
  /** The month, as 2026-07: the trend reads its days. */
  month: string
  /** The month before, when it has calls: the tiles say how far each figure moved. */
  previous?: KpiSummary | null
  previousLabel?: string
}>()

const session = useSessionStore()
// Cosmetic: the API refuses what a role may not read.
const showTrend = computed(() => (session.user ? canOpen(session.user, 'analytics') : false))
const showAttention = computed(() => (session.user ? canOpen(session.user, 'contracts') : false))

/** Percent change, or null when there is nothing to compare with. */
function pct(now: number | null, before: number | null | undefined): number | null {
  return now === null || before === null || before === undefined || before === 0
    ? null
    : ((now - before) / before) * 100
}
/** Change in percentage points. */
function pts(now: number | null, before: number | null | undefined): number | null {
  return now === null || before === null || before === undefined ? null : now - before
}

const total = computed(() => props.summary.total)
// A queue with no calls this month is not a row of dashes; the month's totals already say so.
const queuesWithCalls = computed(() => props.summary.queues.filter((q) => q.offered > 0))
const coverage = computed(() => total.value.serviceLevelPct.coverage)

const prev = computed(() => props.previous?.total ?? null)
const tiles = computed(
  () =>
    [
      {
        key: 'offered',
        label: 'Offered',
        value: formatCount(total.value.offered),
        raw: total.value.offered,
        fmt: (n: number) => formatCount(Math.round(n)),
        note: 'Inbound calls',
        tint: 'brand',
        delta: pct(total.value.offered, prev.value?.offered),
        unit: '%',
        good: 'up',
      },
      {
        key: 'answered',
        label: 'Answered',
        value: formatCount(total.value.answered),
        raw: total.value.answered,
        fmt: (n: number) => formatCount(Math.round(n)),
        note: 'Reached an agent',
        tint: 'ok',
        delta: pct(total.value.answered, prev.value?.answered),
        unit: '%',
        good: 'up',
      },
      {
        key: 'abandon',
        label: 'Abandon rate',
        value: formatPercent(total.value.abandonPct.value, 2),
        raw: total.value.abandonPct.value,
        fmt: (n: number) => formatPercent(n, 2),
        note: `${formatCount(total.value.abandoned)} abandoned`,
        tint: 'danger',
        delta: pts(total.value.abandonPct.value, prev.value?.abandonPct.value),
        unit: ' pts',
        good: 'down',
      },
      {
        key: 'sl',
        label: `Service level (${props.summary.slThresholdS} s)`,
        value: formatPercent(total.value.serviceLevelPct.value, 1),
        raw: total.value.serviceLevelPct.value,
        fmt: (n: number) => formatPercent(n, 1),
        note: `Answered within ${props.summary.slThresholdS} s ÷ offered`,
        tint: 'brand',
        delta: pts(total.value.serviceLevelPct.value, prev.value?.serviceLevelPct.value),
        unit: ' pts',
        good: 'up',
      },
      {
        key: 'asa',
        label: 'Average speed of answer',
        value: formatSeconds(total.value.asaS.value),
        raw: total.value.asaS.value,
        fmt: (n: number) => formatSeconds(n),
        note: 'Mean wait of answered calls',
        tint: 'warn',
        delta: pct(total.value.asaS.value, prev.value?.asaS.value),
        unit: '%',
        good: 'down',
      },
      {
        key: 'aht',
        label: 'Average handling time',
        value: formatDuration(total.value.ahtS.value),
        raw: total.value.ahtS.value,
        fmt: (n: number) => formatDuration(n),
        note: 'Talk + wrap-up, minutes:seconds',
        tint: 'ok',
        delta: pct(total.value.ahtS.value, prev.value?.ahtS.value),
        unit: '%',
        good: 'down',
      },
    ] as const,
)
</script>

<template>
  <div class="space-y-6">
    <NoticeBox v-if="total.offered === 0">
      No calls were recorded in {{ periodLabel }}, so there are no figures to show.
    </NoticeBox>

    <template v-else>
      <div v-if="showTrend || showAttention" class="grid gap-4 lg:grid-cols-3">
        <div v-if="showTrend" class="lg:col-span-2">
          <ServiceTrend :month="month" :period-label="periodLabel" />
        </div>
        <div v-if="showAttention" :class="showTrend ? '' : 'lg:col-span-3'">
          <AttentionCard :queues="queuesWithCalls" />
        </div>
      </div>

      <ul class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="Service figures">
        <StatTile
          v-for="tile in tiles"
          :key="tile.key"
          :label="tile.label"
          :value="tile.raw ?? tile.value"
          :format="tile.fmt"
          :tint="tile.tint"
          :delta="previous ? tile.delta : undefined"
          :delta-unit="tile.unit"
          :delta-good-when="tile.good"
          :delta-versus="previousLabel ? `vs ${previousLabel}` : undefined"
          :data-testid="`tile-${tile.key}`"
        >
          {{ tile.note }}
          <span class="mt-2 block text-[10px] font-semibold uppercase tracking-wide text-brand-ink">
            Measured
          </span>
        </StatTile>
      </ul>

      <p class="text-xs text-ink-muted" data-testid="coverage">
        Measured from imported calls: {{ formatCount(coverage.intervalsUsed) }} of
        {{ formatCount(coverage.intervalsTotal) }} half-hour intervals in {{ periodLabel }} have
        calls.
      </p>

      <div class="overflow-x-auto rounded-xl border border-line bg-surface">
        <table class="w-full min-w-[40rem] text-left text-sm">
          <caption class="px-4 py-3 text-left text-sm font-semibold text-ink">
            Service by queue,
            {{
              periodLabel
            }}
          </caption>
          <thead class="border-y border-line bg-surface-muted text-xs text-ink-muted">
            <tr>
              <th scope="col" class="px-4 py-2 font-medium">Queue</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Offered</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Answered</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Abandoned</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Abandon</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Service level</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">ASA</th>
              <th scope="col" class="px-4 py-2 text-right font-medium">AHT</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="q in queuesWithCalls"
              :key="q.queueId ?? q.queue"
              class="border-b border-line"
            >
              <th scope="row" class="px-4 py-2 font-medium text-ink">
                {{ q.queue }}
                <span
                  v-if="!q.confirmed"
                  class="ml-2 rounded-full bg-warn-soft px-2 py-0.5 text-[10px] font-semibold text-warn"
                  title="Created from an import; an admin has not confirmed it yet"
                  >Unconfirmed</span
                >
              </th>
              <td class="px-3 py-2 text-right tabular-nums">{{ formatCount(q.offered) }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ formatCount(q.answered) }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ formatCount(q.abandoned) }}</td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ formatPercent(q.abandonPct.value, 2) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ formatPercent(q.serviceLevelPct.value, 1) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums">{{ formatSeconds(q.asaS.value) }}</td>
              <td class="px-4 py-2 text-right tabular-nums">{{ formatDuration(q.ahtS.value) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
