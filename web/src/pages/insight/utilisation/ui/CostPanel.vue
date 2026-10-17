<script setup lang="ts">
import { hours, pct, rands, type CostReport } from '@/entities/workforce/utilisation'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

defineProps<{ costs: CostReport }>()
</script>

<template>
  <section class="space-y-3" aria-labelledby="cost-heading" data-testid="cost-panel">
    <h2 id="cost-heading" class="text-base font-semibold text-ink">Cost</h2>
    <NoticeBox>
      Modelled: rostered time at the hourly rate from the salary on file, plus approved overtime.
      Someone with no salary on file has no cost, not a zero cost.
      <span v-if="costs.engineersWithoutSalary > 0" data-testid="no-salary">
        {{ costs.engineersWithoutSalary }} engineer(s) have none.
      </span>
    </NoticeBox>

    <div class="overflow-x-auto rounded-xl border border-line bg-surface">
      <table class="w-full text-left text-sm">
        <caption class="sr-only">
          Cost against contract revenue
        </caption>
        <thead class="text-xs text-ink-muted">
          <tr>
            <th scope="col" class="px-3 py-2">Contract</th>
            <th scope="col" class="px-3 py-2">Ordinary</th>
            <th scope="col" class="px-3 py-2">Overtime</th>
            <th scope="col" class="px-3 py-2">Total</th>
            <th scope="col" class="px-3 py-2">Revenue</th>
            <th scope="col" class="px-3 py-2">Cost of revenue</th>
            <th scope="col" class="px-3 py-2">Overtime of revenue</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="c in costs.contracts"
            :key="c.contractId ?? 'none'"
            class="border-t border-line"
            :data-testid="`cost-${c.contractId ?? 'none'}`"
          >
            <th scope="row" class="px-3 py-2 font-medium text-ink">
              {{ c.name }}
              <span v-if="c.customer" class="font-normal text-ink-muted">({{ c.customer }})</span>
              <span v-if="c.incomplete" class="ml-1 text-xs text-warn">minimum</span>
            </th>
            <td class="px-3 py-2">{{ rands(c.ordinaryRands) }}</td>
            <td class="px-3 py-2">{{ rands(c.overtimeRands) }}</td>
            <td class="px-3 py-2 font-semibold">{{ rands(c.totalRands) }}</td>
            <td class="px-3 py-2">{{ rands(c.revenueRands) }}</td>
            <td class="px-3 py-2">{{ pct(c.costPctOfRevenue) }}</td>
            <td class="px-3 py-2">{{ pct(c.overtimePctOfRevenue) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="overflow-x-auto rounded-xl border border-line bg-surface">
      <table class="w-full text-left text-sm">
        <caption class="sr-only">
          Cost per engineer
        </caption>
        <thead class="text-xs text-ink-muted">
          <tr>
            <th scope="col" class="px-3 py-2">Engineer</th>
            <th scope="col" class="px-3 py-2">Worked (h)</th>
            <th scope="col" class="px-3 py-2">Ordinary</th>
            <th scope="col" class="px-3 py-2">Overtime</th>
            <th scope="col" class="px-3 py-2">Total</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="e in costs.engineers"
            :key="e.employeeId"
            class="border-t border-line"
            :data-testid="`engineer-${e.empNo}`"
          >
            <th scope="row" class="px-3 py-2 font-medium text-ink">
              {{ e.employee }} <span class="text-ink-muted">({{ e.empNo }})</span>
            </th>
            <td class="px-3 py-2">{{ hours(e.workedMin) }}</td>
            <td class="px-3 py-2">{{ rands(e.ordinaryRands) }}</td>
            <td class="px-3 py-2">
              {{ rands(e.overtimeRands) }}
              <span v-if="e.overtimeMissing > 0" class="text-xs text-warn">
                ({{ e.overtimeMissing }} unpriced)
              </span>
            </td>
            <td class="px-3 py-2 font-semibold">
              {{ e.totalRands == null ? 'No salary on file' : rands(e.totalRands) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="overflow-x-auto rounded-xl border border-line bg-surface">
      <table class="w-full text-left text-sm">
        <caption class="sr-only">
          Cost per ticket by pool
        </caption>
        <thead class="text-xs text-ink-muted">
          <tr>
            <th scope="col" class="px-3 py-2">Pool</th>
            <th scope="col" class="px-3 py-2">Tickets closed</th>
            <th scope="col" class="px-3 py-2">With an estimate</th>
            <th scope="col" class="px-3 py-2">Effort (h)</th>
            <th scope="col" class="px-3 py-2">Cost</th>
            <th scope="col" class="px-3 py-2">Per ticket</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="p in costs.pools"
            :key="p.pool"
            class="border-t border-line"
            :data-testid="`pool-${p.pool}`"
          >
            <th scope="row" class="px-3 py-2 font-medium text-ink">{{ p.pool }}</th>
            <td class="px-3 py-2">{{ p.closed }}</td>
            <td class="px-3 py-2">{{ p.estimated }}</td>
            <td class="px-3 py-2">{{ hours(p.effortMin) }}</td>
            <td class="px-3 py-2">{{ rands(p.costRands) }}</td>
            <td class="px-3 py-2 font-semibold">{{ rands(p.perTicketRands) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="text-xs text-ink-muted">
      A ticket is priced from its effort estimate at
      {{
        costs.blendedHourlyRands == null
          ? 'no rate (none known)'
          : `${rands(costs.blendedHourlyRands)} an hour`
      }}, the plain average of the hourly rates on file.
    </p>
  </section>
</template>
