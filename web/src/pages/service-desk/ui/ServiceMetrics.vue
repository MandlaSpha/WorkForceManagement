<script setup lang="ts">
import { computed, ref } from 'vue'

import { fteLabel, useServiceKpis, type ServiceKpiFigures } from '@/entities/service-desk'
import { rands } from '@/entities/workforce/utilisation'
import { problemMessage } from '@/shared/api'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

const thisMonth = new Date()
  .toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' })
  .slice(0, 7)
const month = ref(thisMonth)
const report = useServiceKpis(computed(() => `${month.value}-01`))

const dash = '—'
const num = (v: number | null, digits = 1): string => (v === null ? dash : v.toFixed(digits))
const pct = (v: number | null): string => (v === null ? dash : `${v.toFixed(1)}%`)
const hours = (v: number | null): string => (v === null ? dash : `${v.toFixed(1)} h`)
const days = (v: number | null): string => (v === null ? dash : `${v.toFixed(1)} d`)
const cost = (f: ServiceKpiFigures, visible: boolean): string =>
  !visible ? dash : f.costPerTicketRands === null ? dash : rands(f.costPerTicketRands)
</script>

<template>
  <section class="space-y-4" aria-live="polite" data-testid="service-metrics">
    <label class="flex items-center gap-2 text-sm text-ink">
      Month
      <input
        v-model="month"
        type="month"
        class="rounded-lg border border-line bg-surface px-2 py-1"
      />
    </label>

    <p v-if="report.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="report.isError.value" tone="danger" data-testid="metrics-error">
      Could not load the service metrics. {{ problemMessage(report.error.value) }}
    </NoticeBox>

    <template v-else-if="report.data.value">
      <NoticeBox data-testid="metrics-how">
        Counted from the imported tickets that were <strong>closed</strong> in the month. A figure
        needs the column in the export (first-contact flag, CSAT, NPS): with no answers it shows a
        dash, never zero. Backlog age is the tickets still open on {{ report.data.value.asOf }}.
        Staffing is the people the pool needs over the next 7 days (modelled, as on the demand tab).
        <template v-if="!report.data.value.costVisible">
          Cost per ticket is shown to planners and admins only.
        </template>
      </NoticeBox>

      <NoticeBox v-if="report.data.value.pools.length === 0" data-testid="metrics-empty">
        There are no tickets yet. A planner or admin brings them in from the ticketing tool.
      </NoticeBox>

      <div v-else class="overflow-x-auto rounded-xl border border-line bg-surface">
        <table class="w-full min-w-[60rem] text-left text-sm" data-testid="metrics-table">
          <caption class="px-4 py-3 text-left text-sm font-semibold text-ink">
            Service metrics by resource pool
            <span class="block text-xs font-normal text-ink-muted">
              Closed tickets in the month, with the backlog and staffing beside them.
            </span>
          </caption>
          <thead class="border-y border-line bg-surface-muted text-xs text-ink-muted">
            <tr>
              <th scope="col" class="px-4 py-2 font-medium">Pool</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Closed</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">MTTR</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">FCR</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">CSAT (1 to 5)</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">NPS</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Cost per ticket</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Backlog</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Oldest</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">People needed</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="p in report.data.value.pools"
              :key="p.poolId"
              class="border-b border-line"
              :data-testid="`kpi-pool-${p.poolId}`"
            >
              <th scope="row" class="px-4 py-2 font-medium text-ink">{{ p.pool }}</th>
              <td class="px-3 py-2 text-right tabular-nums" data-col="closed">{{ p.closed }}</td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="mttr">
                {{ hours(p.mttrH) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="fcr">
                {{ pct(p.fcrPct) }}
                <span class="block text-[11px] text-ink-muted">of {{ p.fcrKnown }} flagged</span>
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="csat">
                {{ num(p.csatAverage, 2) }}
                <span class="block text-[11px] text-ink-muted">{{ p.csatCount }} answers</span>
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="nps">
                {{ num(p.nps, 0) }}
                <span class="block text-[11px] text-ink-muted">{{ p.npsCount }} answers</span>
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="cost">
                {{ cost(p, report.data.value.costVisible) }}
                <span
                  v-if="report.data.value.costVisible && p.costPerTicketRands !== null"
                  class="block text-[11px] text-ink-muted"
                  >over {{ p.ticketsPriced }} with an estimate</span
                >
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="backlog">
                {{ p.backlogCount }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="oldest">
                {{ days(p.backlogOldestAgeDays) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="fte">
                {{ fteLabel(p.requiredFte, p.staffingComplete) }}
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="font-semibold" data-testid="kpi-total">
              <th scope="row" class="px-4 py-2 text-ink">All pools</th>
              <td class="px-3 py-2 text-right tabular-nums" data-col="closed">
                {{ report.data.value.total.closed }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="mttr">
                {{ hours(report.data.value.total.mttrH) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="fcr">
                {{ pct(report.data.value.total.fcrPct) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="csat">
                {{ num(report.data.value.total.csatAverage, 2) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="nps">
                {{ num(report.data.value.total.nps, 0) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="cost">
                {{ cost(report.data.value.total, report.data.value.costVisible) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="backlog">
                {{ report.data.value.total.backlogCount }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="oldest">
                {{ days(report.data.value.total.backlogOldestAgeDays) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="fte">
                {{ fteLabel(report.data.value.total.requiredFte, true) }}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </template>
  </section>
</template>
