<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'

import { useSessionStore } from '@/entities/session'
import {
  canCancel,
  KIND_LABEL,
  rands,
  timeLabel,
  useOvertime,
  usePay,
  useStandby,
  useSummary,
} from '@/entities/overtime'
import { useEmployees } from '@/entities/scheduling'
import { OvertimeActions } from '@/features/overtime/decide'
import { RatesBudgetForm } from '@/features/overtime/budget'
import { PayForm } from '@/features/overtime/pay'
import { OvertimeRequestForm } from '@/features/overtime/request'
import { BookStandbyForm, StandbyActions } from '@/features/overtime/standby'
import { WorkedCell } from '@/features/overtime/worked'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { formatDayLabel } from '@/shared/lib/datetime'
import { todayInJohannesburg } from '@/shared/lib/week'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TabBar from '@/shared/ui/TabBar.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'overtime')
const session = useSessionStore()
const role = computed(() => session.user?.role ?? '')
// Cosmetic: the API refuses everything below to any other role.
const canAsk = computed(() => ['lead', 'planner', 'admin'].includes(role.value))
const canDecide = computed(() => ['planner', 'admin'].includes(role.value))
const seesCost = canDecide
const isAdmin = computed(() => role.value === 'admin')

// The form can arrive filled in, e.g. from an intraday alert: /overtime?employeeId&day&from&to.
// The form is held back until the people have loaded so the person can be selected.
const route = useRoute()
const prefill = computed(() => {
  const one = (v: unknown) => (typeof v === 'string' && v !== '' ? v : undefined)
  const found = {
    employeeId: one(route.query.employeeId),
    day: one(route.query.day),
    from: one(route.query.from),
    to: one(route.query.to),
  }
  return Object.values(found).some(Boolean) ? found : null
})

const tab = ref('requests')
const tabs = computed(() => [
  { key: 'requests', label: 'Requests' },
  { key: 'standby', label: 'Standby' },
  ...(canDecide.value ? [{ key: 'summary', label: 'Month' }] : []),
  ...(isAdmin.value ? [{ key: 'pay', label: 'Pay' }] : []),
])

const status = ref('')
const statusOptions = [
  { value: '', label: 'All' },
  { value: 'pending', label: 'Waiting' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'cancelled', label: 'Cancelled' },
]
const requests = useOvertime(computed(() => (status.value === '' ? null : status.value)))
const employees = useEmployees(null, canAsk)
const pay = usePay(isAdmin)
const today = todayInJohannesburg()
const standby = useStandby()
const month = ref(today.slice(0, 7))
const monthFirst = computed(() => `${month.value}-01`)
const summary = useSummary(monthFirst, canDecide)

const STATUS_TONE: Record<string, string> = {
  pending: 'bg-warn-soft text-warn',
  approved: 'bg-brand-soft text-brand-ink',
  rejected: 'bg-danger-soft text-danger',
  cancelled: 'bg-surface-muted text-ink-muted',
}
const STATUS_LABEL: Record<string, string> = {
  pending: 'Waiting',
  approved: 'Approved',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
}
</script>

<template>
  <PageHeader eyebrow="People" :title="screen?.label ?? 'Overtime'" :subtitle="screen?.subtitle" />

  <div class="space-y-6">
    <TabBar v-model="tab" :tabs="tabs" label="Overtime" id-prefix="overtime" />

    <section
      v-if="tab === 'requests'"
      id="overtime-panel-requests"
      role="tabpanel"
      aria-labelledby="overtime-tab-requests"
      class="space-y-4"
      aria-live="polite"
    >
      <OvertimeRequestForm
        v-if="canAsk && (prefill === null || employees.data.value)"
        :employees="employees.data.value ?? []"
        :prefill="prefill ?? undefined"
      />

      <div class="max-w-48">
        <SelectField v-model="status" label="Show" :options="statusOptions" />
      </div>

      <p v-if="requests.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="requests.isError.value" tone="danger">
        Could not load overtime. {{ problemMessage(requests.error.value) }}
      </NoticeBox>
      <NoticeBox v-else-if="(requests.data.value ?? []).length === 0" data-testid="no-overtime">
        No overtime{{ status === '' ? ' yet' : ' with that status' }}.
      </NoticeBox>
      <div v-else class="overflow-x-auto rounded-xl border border-line bg-surface">
        <table class="w-full min-w-[48rem] text-left text-sm" data-testid="overtime-table">
          <caption class="sr-only">
            Overtime requests
          </caption>
          <thead class="border-b border-line bg-surface-muted text-xs text-ink-muted">
            <tr>
              <th scope="col" class="px-4 py-2 font-medium">Person</th>
              <th scope="col" class="px-3 py-2 font-medium">When</th>
              <th scope="col" class="px-3 py-2 font-medium">Kind of day</th>
              <th v-if="seesCost" scope="col" class="px-3 py-2 font-medium">Cost</th>
              <th scope="col" class="px-3 py-2 font-medium">Worked</th>
              <th scope="col" class="px-3 py-2 font-medium">Status</th>
              <th scope="col" class="px-4 py-2 text-right font-medium">
                <span class="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="r in requests.data.value"
              :key="r.id"
              class="border-b border-line align-top"
              :data-testid="`overtime-${r.id}`"
            >
              <th scope="row" class="px-4 py-2 text-left font-medium text-ink">
                {{ r.employee }}
                <span v-if="r.reason" class="block text-xs font-normal text-ink-muted">
                  {{ r.reason }}
                </span>
              </th>
              <td class="px-3 py-2">
                {{ formatDayLabel(r.day) }}
                <span class="block text-xs text-ink-muted">
                  {{ timeLabel(r.startTime, r.endTime, r.minutes) }}
                </span>
              </td>
              <td class="px-3 py-2">{{ KIND_LABEL[r.kind] ?? r.kind }}</td>
              <td v-if="seesCost" class="px-3 py-2 tabular-nums" data-testid="cost">
                <template v-if="r.costRands !== null">{{ rands(r.costRands) }}</template>
                <span v-else-if="r.costMissing" class="text-ink-muted">No salary on file</span>
                <span v-else class="text-ink-muted">—</span>
              </td>
              <td class="px-3 py-2">
                <WorkedCell
                  v-if="r.status === 'approved'"
                  :request-id="r.id"
                  :who="`${r.employee} on ${formatDayLabel(r.day)}`"
                  :worked-minutes="r.workedMinutes"
                  :extra-minutes="r.extraMinutes"
                  :can-record="canDecide && r.day <= today"
                  :own="r.mine"
                />
                <span v-else class="text-ink-muted">—</span>
                <span
                  v-if="seesCost && r.workedCostRands !== null"
                  class="block text-xs text-ink-muted tabular-nums"
                  data-testid="worked-cost"
                >
                  Paid {{ rands(r.workedCostRands) }}
                </span>
              </td>
              <td class="px-3 py-2">
                <span
                  class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                  :class="STATUS_TONE[r.status]"
                >
                  {{ STATUS_LABEL[r.status] ?? r.status }}
                </span>
              </td>
              <td class="px-4 py-2 text-right">
                <OvertimeActions
                  :request-id="r.id"
                  :who="`${r.employee} on ${formatDayLabel(r.day)}`"
                  :can-decide="canDecide && r.status === 'pending'"
                  :can-cancel="canAsk && canCancel(r.status, r.day, today)"
                  :own="r.mine"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section
      v-else-if="tab === 'standby'"
      id="overtime-panel-standby"
      role="tabpanel"
      aria-labelledby="overtime-tab-standby"
      class="space-y-4"
      aria-live="polite"
    >
      <BookStandbyForm v-if="canAsk" :employees="employees.data.value ?? []" />
      <p v-if="standby.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="standby.isError.value" tone="danger">
        Could not load standby. {{ problemMessage(standby.error.value) }}
      </NoticeBox>
      <NoticeBox v-else-if="(standby.data.value ?? []).length === 0" data-testid="no-standby">
        Nobody is on standby yet.
      </NoticeBox>
      <ul v-else class="space-y-2" aria-label="Standby">
        <li
          v-for="s in standby.data.value"
          :key="s.id"
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface p-4"
          :class="s.status === 'cancelled' ? 'opacity-60' : ''"
          :data-testid="`standby-${s.id}`"
        >
          <div class="text-sm">
            <p class="font-medium text-ink">{{ s.employee }}, {{ formatDayLabel(s.day) }}</p>
            <p class="text-xs text-ink-muted">
              {{ s.status === 'cancelled' ? 'Cancelled' : 'On standby' }}
              <template v-if="seesCost && s.allowanceRands !== null">
                , allowance {{ rands(s.allowanceRands) }}
              </template>
              <template v-if="s.callOutMinutes">
                , called out for {{ s.callOutMinutes }} minutes
                <template v-if="seesCost && s.callOutCostRands !== null">
                  ({{ rands(s.callOutCostRands) }})
                </template>
                <template v-else-if="seesCost && s.callOutCostMissing">
                  (no salary on file)
                </template>
              </template>
            </p>
          </div>
          <StandbyActions
            :standby-id="s.id"
            :who="`${s.employee} on ${formatDayLabel(s.day)}`"
            :booked="s.status === 'booked'"
            :can-cancel="canAsk && s.day >= today && !s.callOutMinutes"
            :can-record="canDecide && s.day <= today"
            :own="s.mine"
          />
        </li>
      </ul>
    </section>

    <section
      v-else-if="tab === 'summary'"
      id="overtime-panel-summary"
      role="tabpanel"
      aria-labelledby="overtime-tab-summary"
      class="space-y-4"
      aria-live="polite"
    >
      <label class="flex items-center gap-2 text-sm text-ink">
        Month
        <input
          v-model="month"
          type="month"
          class="rounded-lg border border-line bg-surface px-2 py-1"
        />
      </label>
      <p v-if="summary.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="summary.isError.value" tone="danger">
        Could not load the month. {{ problemMessage(summary.error.value) }}
      </NoticeBox>
      <template v-else-if="summary.data.value">
        <dl class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="summary">
          <div class="rounded-xl border border-line bg-surface p-4">
            <dt class="text-xs text-ink-muted">Overtime</dt>
            <dd class="text-lg font-semibold tabular-nums" data-testid="overtime-cost">
              {{ rands(summary.data.value.overtimeCostRands) }}
            </dd>
            <dd class="text-xs text-ink-muted">
              {{ summary.data.value.approved }} approved, {{ summary.data.value.workedMinutes }}
              minutes paid
            </dd>
          </div>
          <div class="rounded-xl border border-line bg-surface p-4">
            <dt class="text-xs text-ink-muted">Standby allowances</dt>
            <dd class="text-lg font-semibold tabular-nums" data-testid="standby-cost">
              {{ rands(summary.data.value.standbyAllowancesRands) }}
            </dd>
            <dd class="text-xs text-ink-muted">{{ summary.data.value.standbyDays }} days</dd>
          </div>
          <div class="rounded-xl border border-line bg-surface p-4">
            <dt class="text-xs text-ink-muted">Call-outs</dt>
            <dd class="text-lg font-semibold tabular-nums" data-testid="callout-cost">
              {{ rands(summary.data.value.callOutCostRands) }}
            </dd>
            <dd class="text-xs text-ink-muted">{{ summary.data.value.callOutMinutes }} minutes</dd>
          </div>
          <div class="rounded-xl border border-line bg-surface p-4">
            <dt class="text-xs text-ink-muted">Total</dt>
            <dd class="text-lg font-semibold tabular-nums" data-testid="total-cost">
              {{ rands(summary.data.value.totalRands) }}
            </dd>
            <dd class="text-xs text-ink-muted" data-testid="budget-line">
              <template v-if="summary.data.value.budgetRands !== null">
                Budget {{ rands(summary.data.value.budgetRands) }}:
                {{
                  summary.data.value.totalRands > summary.data.value.budgetRands
                    ? `${rands(summary.data.value.totalRands - summary.data.value.budgetRands)} over`
                    : `${rands(summary.data.value.budgetRands - summary.data.value.totalRands)} left`
                }}
              </template>
              <template v-else>No budget set for this month</template>
            </dd>
          </div>
        </dl>
        <NoticeBox
          v-if="summary.data.value.unreconciled > 0"
          tone="warn"
          data-testid="unreconciled"
        >
          {{ summary.data.value.unreconciled }} approved
          {{ summary.data.value.unreconciled === 1 ? 'request has' : 'requests have' }} happened but
          {{ summary.data.value.unreconciled === 1 ? 'has' : 'have' }} no worked time recorded yet,
          so the approved amount is counted.
        </NoticeBox>
        <NoticeBox
          v-if="summary.data.value.extraMinutes > 0"
          tone="warn"
          data-testid="extra-minutes"
        >
          {{ summary.data.value.extraMinutes }} minutes were worked beyond what was approved. They
          are not paid and not in the total.
        </NoticeBox>
        <NoticeBox
          v-if="summary.data.value.missingPrices > 0"
          tone="warn"
          data-testid="missing-prices"
        >
          {{ summary.data.value.missingPrices }}
          {{ summary.data.value.missingPrices === 1 ? 'request has' : 'requests have' }} no salary
          on file and {{ summary.data.value.missingPrices === 1 ? 'is' : 'are' }} not in the total.
        </NoticeBox>
        <p class="text-sm">
          <a
            :href="`/api/v1/overtime/payroll.csv?month=${monthFirst}`"
            class="font-medium text-brand-ink underline"
            download
            data-testid="payroll-link"
          >
            Download the payroll file for this month (CSV)
          </a>
          <span class="block text-xs text-ink-muted">
            Names, hours, leave days, overtime, standby and call-outs. It holds pay, so keep it with
            payroll. Each download is recorded.
          </span>
        </p>
        <RatesBudgetForm v-if="isAdmin" :month="monthFirst" />
      </template>
    </section>

    <section
      v-else
      id="overtime-panel-pay"
      role="tabpanel"
      aria-labelledby="overtime-tab-pay"
      class="space-y-4"
      aria-live="polite"
    >
      <NoticeBox data-testid="pay-note">
        Salaries are payroll data. They are used only to price overtime, are never shown again once
        saved, and never appear in the audit trail or in any message.
      </NoticeBox>
      <p v-if="pay.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="pay.isError.value" tone="danger">
        Could not load the pay list. {{ problemMessage(pay.error.value) }}
      </NoticeBox>
      <ul v-else class="space-y-3" aria-label="Pay">
        <li
          v-for="person in pay.data.value"
          :key="person.employeeId"
          class="rounded-xl border border-line bg-surface p-4"
          :data-testid="`pay-${person.empNo}`"
        >
          <p class="mb-2 text-sm font-medium text-ink">
            {{ person.employee }}
            <span class="ml-2 text-xs font-normal text-ink-muted">
              {{ person.hasSalary ? 'Salary on file' : 'No salary on file' }}
            </span>
          </p>
          <PayForm :person="person" />
        </li>
      </ul>
    </section>
  </div>
</template>
