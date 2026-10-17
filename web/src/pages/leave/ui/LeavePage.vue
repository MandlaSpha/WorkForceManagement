<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  canCancel,
  daysLeft,
  rangeLabel,
  STATUS_LABEL,
  STATUS_TONE,
  useAwayLimit,
  useBalances,
  useBlackouts,
  useLeaveTypes,
  useRequests,
} from '@/entities/leave'
import type { Decision } from '@/entities/leave'
import { useSessionStore } from '@/entities/session'
import { ApplyLeaveForm } from '@/features/leave/apply'
import { CancelLeaveButton, DecisionButtons, ImpactPanel } from '@/features/leave/decide'
import { EntitlementForm } from '@/features/leave/entitlement'
import { AwayLimitForm, BlackoutManager } from '@/features/leave/rules'
import { ApiProblem, problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { todayInJohannesburg } from '@/shared/lib/week'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TabBar from '@/shared/ui/TabBar.vue'

const session = useSessionStore()
const screen = NAV_ITEMS.find((item) => item.key === 'leave')
const role = computed(() => session.user?.role ?? '')
// Cosmetic: the API refuses deciding and entitlements for any other role.
const decides = computed(() => ['lead', 'planner', 'admin'].includes(role.value))
const configures = computed(() => role.value === 'admin')

const today = todayInJohannesburg()
const year = Number(today.slice(0, 4))

const balances = useBalances(year)
const noRecord = computed(
  () =>
    balances.error.value instanceof ApiProblem &&
    balances.error.value.code === 'leave.no_employee_record',
)
const mine = useRequests(null)
const myRequests = computed(() => (mine.data.value ?? []).filter((r) => r.mine))

const filter = ref('pending')
const FILTERS = [
  { value: 'pending', label: 'Waiting for a decision' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'cancelled', label: 'Cancelled' },
]
const queue = useRequests(computed(() => filter.value))

const types = useLeaveTypes()
const blackouts = useBlackouts()
const awayLimit = useAwayLimit()
// Blackout periods that have not ended yet: the ones that can still stop a request.
const upcomingBlackouts = computed(() =>
  (blackouts.data.value ?? []).filter((b) => b.dateTo >= today),
)
const open = ref<number | null>(null) // the request whose coverage impact is showing

// What the last decision did, kept on the page: the request leaves the waiting list as soon as it
// is decided, and its row goes with it.
const outcome = ref('')
function reported(who: string, d: Decision): void {
  const verb = { approved: 'Approved', rejected: 'Rejected', cancelled: 'Cancelled' }[
    d.request.status
  ]
  const shifts: string[] = []
  if (d.shiftsCleared > 0) shifts.push(`${d.shiftsCleared} shifts taken off the roster`)
  if (d.shiftsRestored > 0) shifts.push(`${d.shiftsRestored} shifts put back on the roster`)
  if (d.shiftsNotRestored > 0) shifts.push(`${d.shiftsNotRestored} could not be put back`)
  outcome.value = `${verb} leave for ${who}${shifts.length > 0 ? `: ${shifts.join(', ')}` : ''}.`
}

const tab = ref('mine')
const TABS = computed(() => [
  { key: 'mine', label: 'My leave' },
  ...(decides.value ? [{ key: 'approvals', label: 'Approvals' }] : []),
  ...(configures.value
    ? [
        { key: 'entitlements', label: 'Entitlements' },
        { key: 'rules', label: 'Rules' },
      ]
    : []),
])
</script>

<template>
  <PageHeader eyebrow="People" :title="screen?.label ?? 'Leave'" :subtitle="screen?.subtitle" />

  <div class="space-y-4">
    <TabBar v-model="tab" :tabs="TABS" label="Leave sections" id-prefix="leave" />

    <NoticeBox v-if="outcome" data-testid="decision-result" role="status">{{ outcome }}</NoticeBox>

    <div
      v-if="tab === 'mine'"
      id="leave-panel-mine"
      role="tabpanel"
      aria-labelledby="leave-tab-mine"
      class="space-y-6"
      aria-live="polite"
    >
      <NoticeBox v-if="noRecord" data-testid="no-record">
        You are not on the employee list yet, so there is no leave to show or ask for. A planner
        adds you.
      </NoticeBox>
      <template v-else>
        <p v-if="balances.isPending.value" class="text-sm text-ink-muted">Loading…</p>
        <NoticeBox v-else-if="balances.isError.value" tone="danger">
          Could not load your balances. {{ problemMessage(balances.error.value) }}
        </NoticeBox>
        <section v-else-if="balances.data.value" class="space-y-2" aria-labelledby="balances-title">
          <h2 id="balances-title" class="text-base font-semibold text-ink">
            My balances, {{ balances.data.value.year }}
          </h2>
          <ul class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <li
              v-for="b in balances.data.value.balances"
              :key="b.typeId"
              class="rounded-xl border border-line bg-surface p-4"
              :data-testid="`balance-${b.code}`"
            >
              <p class="text-xs font-medium text-ink-muted">{{ b.name }}</p>
              <p class="mt-1 text-lg font-semibold tabular-nums text-ink">
                {{ daysLeft(b.available, b.entitlement) }}
              </p>
              <p class="text-xs text-ink-muted">{{ b.taken }} taken, {{ b.pending }} waiting</p>
            </li>
          </ul>
          <NoticeBox
            v-if="(types.data.value ?? []).some((t) => !t.confirmed)"
            data-testid="defaults-notice"
          >
            The days a year are South African (BCEA) defaults that nobody has confirmed yet. An
            admin confirms them for your company.
          </NoticeBox>
        </section>

        <NoticeBox
          v-if="upcomingBlackouts.length > 0 || awayLimit.data.value?.maxConcurrent"
          data-testid="leave-rules-notice"
        >
          <p v-for="b in upcomingBlackouts" :key="b.id">
            {{ b.name }} ({{ rangeLabel(b.dateFrom, b.dateTo) }}): annual, study, training and
            unpaid leave cannot be asked for then. Sick and family leave can.
          </p>
          <p v-if="awayLimit.data.value?.maxConcurrent">
            At most {{ awayLimit.data.value.maxConcurrent }} people can be away at once.
          </p>
        </NoticeBox>

        <section class="space-y-2" aria-labelledby="ask-title">
          <h2 id="ask-title" class="text-base font-semibold text-ink">Ask for leave</h2>
          <ApplyLeaveForm />
        </section>

        <section class="space-y-2" aria-labelledby="mine-title">
          <h2 id="mine-title" class="text-base font-semibold text-ink">My requests</h2>
          <p v-if="mine.isPending.value" class="text-sm text-ink-muted">Loading…</p>
          <NoticeBox v-else-if="myRequests.length === 0"
            >You have not asked for any leave yet.</NoticeBox
          >
          <div v-else class="overflow-x-auto rounded-xl border border-line bg-surface">
            <table
              class="stack-on-phone w-full text-left text-sm sm:min-w-[34rem]"
              data-testid="my-requests"
            >
              <caption class="sr-only">
                My leave requests
              </caption>
              <thead class="border-b border-line bg-surface-muted text-xs text-ink-muted">
                <tr>
                  <th scope="col" class="px-4 py-2 font-medium">Kind</th>
                  <th scope="col" class="px-3 py-2 font-medium">Dates</th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">Days</th>
                  <th scope="col" class="px-3 py-2 font-medium">Status</th>
                  <th scope="col" class="px-4 py-2 text-right font-medium">
                    <span class="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="r in myRequests"
                  :key="r.id"
                  class="border-b border-line"
                  :data-testid="`mine-${r.id}`"
                >
                  <th scope="row" class="px-4 py-2 font-medium text-ink">{{ r.leaveType }}</th>
                  <td data-label="Dates" class="px-3 py-2">
                    {{ rangeLabel(r.startDate, r.endDate) }}
                  </td>
                  <td data-label="Days" class="px-3 py-2 text-right tabular-nums">{{ r.days }}</td>
                  <td data-label="Status" class="px-3 py-2">
                    <span
                      class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                      :class="STATUS_TONE[r.status]"
                    >
                      {{ STATUS_LABEL[r.status] ?? r.status }}
                    </span>
                  </td>
                  <td class="px-4 py-2 text-right">
                    <CancelLeaveButton
                      v-if="canCancel(r.status, r.endDate, today)"
                      :request-id="r.id"
                      :label="rangeLabel(r.startDate, r.endDate)"
                      @cancelled="reported(r.employee, $event)"
                    />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </div>

    <div
      v-else-if="tab === 'approvals'"
      id="leave-panel-approvals"
      role="tabpanel"
      aria-labelledby="leave-tab-approvals"
      class="space-y-4"
      aria-live="polite"
    >
      <div class="w-56">
        <SelectField v-model="filter" label="Show" :options="FILTERS" />
      </div>
      <p v-if="queue.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="queue.isError.value" tone="danger">
        Could not load the requests. {{ problemMessage(queue.error.value) }}
      </NoticeBox>
      <NoticeBox v-else-if="(queue.data.value ?? []).length === 0" data-testid="nothing-to-decide">
        No requests here.
      </NoticeBox>
      <ul v-else class="space-y-3" aria-label="Leave requests">
        <li
          v-for="r in queue.data.value"
          :key="r.id"
          class="rounded-xl border border-line bg-surface p-4"
          :data-testid="`request-${r.id}`"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p class="text-sm font-semibold text-ink">
                {{ r.employee }} <span class="font-normal text-ink-muted">({{ r.empNo }})</span>
              </p>
              <p class="text-sm text-ink">
                {{ r.leaveType }}: {{ rangeLabel(r.startDate, r.endDate) }}, {{ r.days }}
                {{ r.days === 1 ? 'day' : 'days' }}
              </p>
              <button
                type="button"
                class="mt-1 text-xs font-medium text-brand-ink underline"
                :aria-expanded="open === r.id"
                :aria-label="`${open === r.id ? 'Hide' : 'Show'} coverage impact for ${r.employee}`"
                @click="open = open === r.id ? null : r.id"
              >
                {{ open === r.id ? 'Hide impact' : 'Show impact on coverage' }}
              </button>
            </div>
            <DecisionButtons
              v-if="r.status === 'pending'"
              :request-id="r.id"
              :who="r.employee"
              :own="r.mine"
              @decided="reported(r.employee, $event)"
            />
            <span
              v-else
              class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
              :class="STATUS_TONE[r.status]"
            >
              {{ STATUS_LABEL[r.status] ?? r.status }}
            </span>
          </div>
          <div v-if="open === r.id" class="mt-3 rounded-lg bg-surface-muted p-3">
            <ImpactPanel :request-id="r.id" />
          </div>
        </li>
      </ul>
    </div>

    <div
      v-else-if="tab === 'rules'"
      id="leave-panel-rules"
      role="tabpanel"
      aria-labelledby="leave-tab-rules"
      class="space-y-6"
    >
      <section class="space-y-2" aria-labelledby="blackout-title">
        <h2 id="blackout-title" class="text-base font-semibold text-ink">Blackout periods</h2>
        <p class="text-sm text-ink-muted">
          Days on which leave that can wait cannot be asked for (a year-end close, a launch). Sick,
          family responsibility and maternity leave are never refused for these.
        </p>
        <BlackoutManager />
      </section>
      <section class="space-y-2" aria-labelledby="limit-title">
        <h2 id="limit-title" class="text-base font-semibold text-ink">Away at once</h2>
        <p class="text-sm text-ink-muted">
          The most people who may be on approved leave on the same day, counting leave that can
          wait. A request that would pass it is refused.
        </p>
        <AwayLimitForm />
      </section>
    </div>

    <div
      v-else
      id="leave-panel-entitlements"
      role="tabpanel"
      aria-labelledby="leave-tab-entitlements"
      class="space-y-3"
    >
      <p class="text-sm text-ink-muted">
        Days a year for each kind of leave. They start as South African (BCEA) defaults; saving one
        confirms it. Leave it blank for no limit.
      </p>
      <EntitlementForm
        v-for="t in types.data.value ?? []"
        :key="`${t.id}-${t.daysPerYear}-${t.confirmed}`"
        :type="t"
      />
    </div>
  </div>
</template>
