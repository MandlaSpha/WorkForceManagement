<script setup lang="ts">
import { computed } from 'vue'

import {
  formatCount,
  formatDuration,
  formatPercent,
  formatSeconds,
  type KpiSummary,
} from '@/entities/call-data'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

const props = defineProps<{ summary: KpiSummary; periodLabel: string }>()

const total = computed(() => props.summary.total)
// A queue with no calls this month is not a row of dashes; the month's totals already say so.
const queuesWithCalls = computed(() => props.summary.queues.filter((q) => q.offered > 0))
const coverage = computed(() => total.value.serviceLevelPct.coverage)

const tiles = computed(() => [
  {
    key: 'offered',
    label: 'Offered',
    value: formatCount(total.value.offered),
    note: 'Inbound calls',
  },
  {
    key: 'answered',
    label: 'Answered',
    value: formatCount(total.value.answered),
    note: 'Reached an agent',
  },
  {
    key: 'abandon',
    label: 'Abandon rate',
    value: formatPercent(total.value.abandonPct.value, 2),
    note: `${formatCount(total.value.abandoned)} abandoned`,
  },
  {
    key: 'sl',
    label: `Service level (${props.summary.slThresholdS} s)`,
    value: formatPercent(total.value.serviceLevelPct.value, 1),
    note: `Answered within ${props.summary.slThresholdS} s ÷ offered`,
  },
  {
    key: 'asa',
    label: 'Average speed of answer',
    value: formatSeconds(total.value.asaS.value),
    note: 'Mean wait of answered calls',
  },
  {
    key: 'aht',
    label: 'Average handling time',
    value: formatDuration(total.value.ahtS.value),
    note: 'Talk + wrap-up, minutes:seconds',
  },
])
</script>

<template>
  <div class="space-y-6">
    <NoticeBox v-if="total.offered === 0">
      No calls were recorded in {{ periodLabel }}, so there are no figures to show.
    </NoticeBox>

    <template v-else>
      <ul class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="Service figures">
        <li
          v-for="tile in tiles"
          :key="tile.key"
          class="rounded-xl border border-line bg-surface p-4"
          :data-testid="`tile-${tile.key}`"
        >
          <p class="text-xs font-medium text-ink-muted">{{ tile.label }}</p>
          <p class="mt-1 text-2xl font-semibold tabular-nums text-ink">{{ tile.value }}</p>
          <p class="mt-1 text-xs text-ink-muted">{{ tile.note }}</p>
          <p class="mt-2 text-[10px] font-semibold uppercase tracking-wide text-brand-ink">
            Measured
          </p>
        </li>
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
