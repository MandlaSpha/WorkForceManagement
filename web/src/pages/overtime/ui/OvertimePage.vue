<script setup lang="ts">
import { computed, ref } from 'vue'

import { useSessionStore } from '@/entities/session'
import { canCancel, KIND_LABEL, rands, timeLabel, useOvertime, usePay } from '@/entities/overtime'
import { useEmployees } from '@/entities/scheduling'
import { OvertimeActions } from '@/features/overtime/decide'
import { PayForm } from '@/features/overtime/pay'
import { OvertimeRequestForm } from '@/features/overtime/request'
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

const tab = ref('requests')
const tabs = computed(() => [
  { key: 'requests', label: 'Requests' },
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
    <TabBar v-if="isAdmin" v-model="tab" :tabs="tabs" label="Overtime" id-prefix="overtime" />

    <section
      v-if="tab === 'requests'"
      id="overtime-panel-requests"
      role="tabpanel"
      aria-labelledby="overtime-tab-requests"
      class="space-y-4"
      aria-live="polite"
    >
      <OvertimeRequestForm v-if="canAsk" :employees="employees.data.value ?? []" />

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
