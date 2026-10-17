<script setup lang="ts">
import { computed, ref } from 'vue'

import { fteLabel, useDemand } from '@/entities/service-desk'
import { useSessionStore } from '@/entities/session'
import { PoolMinutes } from '@/features/set-pool-minutes'
import { WorkItemImport } from '@/features/import-work-items'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { formatMinutes } from '@/shared/lib/duration'
import { todayInJohannesburg } from '@/shared/lib/week'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TabBar from '@/shared/ui/TabBar.vue'

import ServiceMetrics from './ServiceMetrics.vue'

const session = useSessionStore()
const screen = NAV_ITEMS.find((item) => item.key === 'service-desk')
// Cosmetic: the API refuses bringing work in and setting productive time for any other role.
const canChange = computed(() => ['planner', 'admin'].includes(session.user?.role ?? ''))

const asOf = todayInJohannesburg()
const days = ref('7')
const HORIZONS = [
  { value: '7', label: 'Next 7 days' },
  { value: '14', label: 'Next 14 days' },
  { value: '28', label: 'Next 28 days' },
]
const demand = useDemand(
  asOf,
  computed(() => Number(days.value)),
)
const data = computed(() => demand.data.value)

const tab = ref('demand')
const TABS = computed(() => [
  { key: 'demand', label: 'Demand & capacity' },
  { key: 'metrics', label: 'Service metrics' },
  ...(canChange.value ? [{ key: 'import', label: 'Bring in work' }] : []),
])
</script>

<template>
  <PageHeader
    eyebrow="Operate"
    :title="screen?.label ?? 'Service desk'"
    :subtitle="screen?.subtitle"
  >
    <template v-if="tab === 'demand'" #actions>
      <div class="w-40">
        <SelectField v-model="days" label="Period" :options="HORIZONS" />
      </div>
    </template>
  </PageHeader>

  <div class="space-y-4">
    <NoticeBox data-testid="not-erlang">
      <strong>This is not Erlang.</strong> A caller who is not answered abandons; a ticket that is
      not picked up is still there tomorrow. So the people needed are the effort that must be
      finished by a deadline divided by the productive time one person has before it. Effort is
      engineer time, never the SLA window: a four-hour P1 can hold twenty minutes of work.
    </NoticeBox>

    <TabBar v-model="tab" :tabs="TABS" label="Service desk sections" id-prefix="sd" />

    <div
      v-if="tab === 'demand'"
      id="sd-panel-demand"
      role="tabpanel"
      aria-labelledby="sd-tab-demand"
      class="space-y-4"
      aria-live="polite"
    >
      <p v-if="demand.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="demand.isError.value" tone="danger">
        Could not load the workload. {{ problemMessage(demand.error.value) }}
      </NoticeBox>

      <template v-else-if="data">
        <NoticeBox v-if="data.pools.length === 0" data-testid="no-work">
          There is no work yet, so there is nothing to size.
          <template v-if="canChange">Bring it in from the ticketing tool on the next tab.</template>
          <template v-else>A planner or admin brings it in from the ticketing tool.</template>
        </NoticeBox>

        <template v-else>
          <NoticeBox v-if="!data.complete" data-testid="minimum-notice">
            Some figures are minimums: items with no effort estimate cannot be sized, and a pool
            with nothing opened in the last 28 days has no arrival rate (that could be a quiet month
            or a missing export, so no arrivals are assumed).
          </NoticeBox>

          <ul class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Summary">
            <li class="rounded-xl border border-line bg-surface p-4" data-testid="kpi-fte">
              <p class="text-xs font-medium text-ink-muted">Required people</p>
              <p class="mt-1 text-xl font-semibold tabular-nums text-ink">
                {{ fteLabel(data.requiredFte, data.complete) }}
              </p>
              <p class="text-xs text-ink-muted">over {{ data.workingDays }} working days</p>
            </li>
            <li class="rounded-xl border border-line bg-surface p-4" data-testid="kpi-backlog">
              <p class="text-xs font-medium text-ink-muted">Backlog effort</p>
              <p class="mt-1 text-xl font-semibold tabular-nums text-ink">
                {{ formatMinutes(data.backlogMin) }}
              </p>
            </li>
            <li class="rounded-xl border border-line bg-surface p-4" data-testid="kpi-arriving">
              <p class="text-xs font-medium text-ink-muted">Arriving effort</p>
              <p class="mt-1 text-xl font-semibold tabular-nums text-ink">
                {{ data.arrivingMin === null ? '\u2014' : formatMinutes(data.arrivingMin) }}
              </p>
            </li>
            <li class="rounded-xl border border-line bg-surface p-4" data-testid="kpi-breached">
              <p class="text-xs font-medium text-ink-muted">Already breached</p>
              <p class="mt-1 text-xl font-semibold tabular-nums text-ink">{{ data.breached }}</p>
            </li>
          </ul>

          <div class="overflow-x-auto rounded-xl border border-line bg-surface">
            <table class="w-full min-w-[48rem] text-left text-sm" data-testid="pool-table">
              <caption class="px-4 py-3 text-left text-sm font-semibold text-ink">
                By resource pool
                <span class="block text-xs font-normal text-ink-muted">
                  Most people needed first. Breached means past its deadline when the period starts.
                </span>
              </caption>
              <thead class="border-y border-line bg-surface-muted text-xs text-ink-muted">
                <tr>
                  <th scope="col" class="px-4 py-2 font-medium">Pool</th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">Backlog</th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">Due in period</th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">Arriving</th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">Required people</th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">Breached</th>
                  <th scope="col" class="px-3 py-2 font-medium">Productive min / day</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="p in data.pools"
                  :key="p.poolId"
                  class="border-b border-line"
                  :data-testid="`pool-${p.poolId}`"
                >
                  <th scope="row" class="px-4 py-2 font-medium text-ink">
                    {{ p.pool }}
                    <span
                      v-if="p.unestimated > 0 || p.noDeadline > 0"
                      class="block text-xs font-normal text-ink-muted"
                    >
                      <template v-if="p.unestimated > 0"
                        >{{ p.unestimated }} with no estimate.
                      </template>
                      <template v-if="p.noDeadline > 0"
                        >{{ p.noDeadline }} with no deadline.</template
                      >
                    </span>
                  </th>
                  <td class="px-3 py-2 text-right tabular-nums" data-col="backlog">
                    {{ formatMinutes(p.backlogMin) }}
                  </td>
                  <td class="px-3 py-2 text-right tabular-nums" data-col="due">
                    {{ formatMinutes(p.dueMin) }}
                  </td>
                  <td class="px-3 py-2 text-right tabular-nums" data-col="arriving">
                    {{ p.arrivingMin === null ? '\u2014' : formatMinutes(p.arrivingMin) }}
                  </td>
                  <td class="px-3 py-2 text-right font-semibold tabular-nums" data-col="fte">
                    {{ fteLabel(p.requiredFte, p.complete) }}
                  </td>
                  <td class="px-3 py-2 text-right tabular-nums" data-col="breached">
                    {{ p.breached }}
                  </td>
                  <td class="px-3 py-2" data-col="minutes">
                    <PoolMinutes
                      v-if="canChange"
                      :key="`${p.poolId}-${p.productiveMinutesPerDay}`"
                      :pool-id="p.poolId"
                      :pool="p.pool"
                      :minutes="p.productiveMinutesPerDay"
                    />
                    <template v-else>{{ p.productiveMinutesPerDay }}</template>
                    <span v-if="!p.settingsConfirmed" class="mt-1 block text-[11px] text-warn"
                      >Default, not confirmed</span
                    >
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </template>
    </div>

    <div
      v-else-if="tab === 'metrics'"
      id="sd-panel-metrics"
      role="tabpanel"
      aria-labelledby="sd-tab-metrics"
    >
      <ServiceMetrics />
    </div>

    <div v-else id="sd-panel-import" role="tabpanel" aria-labelledby="sd-tab-import">
      <WorkItemImport />
    </div>
  </div>
</template>
