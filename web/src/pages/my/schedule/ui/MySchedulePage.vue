<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { clock } from '@/entities/availability'
import {
  daysWithSomething,
  monthGrid,
  monthLabel,
  monthOf,
  shiftMonth,
  useMySchedule,
} from '@/entities/my-schedule'
import type { ScheduleDay } from '@/entities/my-schedule'
import { ApiProblem, problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { formatDayLabel } from '@/shared/lib/datetime'
import { todayInJohannesburg } from '@/shared/lib/week'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'my-schedule')
const today = todayInJohannesburg()

const month = ref(monthOf(today))
const view = ref<'month' | 'list'>('month')
const grid = computed(() => monthGrid(month.value))
const from = computed(() => grid.value.from)
const to = computed(() => grid.value.to)

const schedule = useMySchedule(from, to)
const noRecord = computed(
  () =>
    schedule.error.value instanceof ApiProblem &&
    schedule.error.value.code === 'schedule.no_employee_record',
)
const days = computed<ScheduleDay[]>(() => {
  const s = schedule.data.value
  return s ? daysWithSomething(s.shifts, s.leave, s.fromDate, s.toDate) : []
})
const byDay = computed(() => new Map(days.value.map((d) => [d.day, d])))

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const LEAVE_STATUS: Record<string, string> = {
  approved: 'approved',
  pending: 'waiting for a decision',
}
const SHORT_STATUS: Record<string, string> = { approved: '', pending: ' (asked)' }
const dayNumber = (iso: string) => String(Number(iso.slice(8)))
</script>

<template>
  <PageHeader
    eyebrow="My work"
    :title="screen?.label ?? 'My schedule'"
    :subtitle="screen?.subtitle"
  />

  <div class="space-y-4" aria-live="polite">
    <NoticeBox v-if="noRecord" data-testid="no-record">
      You are not on the employee list yet, so there is no schedule to show. A planner adds you.
    </NoticeBox>
    <template v-else>
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-2">
          <AppButton
            variant="secondary"
            aria-label="Previous month"
            @click="month = shiftMonth(month, -1)"
          >
            ‹
          </AppButton>
          <h2
            class="min-w-40 text-center text-base font-semibold text-ink"
            data-testid="month-title"
          >
            {{ monthLabel(month) }}
          </h2>
          <AppButton
            variant="secondary"
            aria-label="Next month"
            @click="month = shiftMonth(month, 1)"
          >
            ›
          </AppButton>
          <AppButton
            v-if="month !== monthOf(today)"
            variant="ghost"
            @click="month = monthOf(today)"
          >
            This month
          </AppButton>
        </div>
        <div class="flex gap-1" role="group" aria-label="How to show the schedule">
          <AppButton
            :variant="view === 'month' ? 'primary' : 'secondary'"
            :aria-pressed="view === 'month'"
            @click="view = 'month'"
          >
            Month
          </AppButton>
          <AppButton
            :variant="view === 'list' ? 'primary' : 'secondary'"
            :aria-pressed="view === 'list'"
            @click="view = 'list'"
          >
            List
          </AppButton>
        </div>
      </div>

      <p v-if="schedule.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="schedule.isError.value" tone="danger">
        Could not load your schedule. {{ problemMessage(schedule.error.value) }}
      </NoticeBox>
      <template v-else-if="schedule.data.value">
        <NoticeBox v-if="schedule.data.value.unpublishedShifts > 0" data-testid="unpublished">
          Your planner has pencilled in {{ schedule.data.value.unpublishedShifts }} more
          {{ schedule.data.value.unpublishedShifts === 1 ? 'shift' : 'shifts' }} for you, but that
          roster is not final yet. Do not plan around
          {{ schedule.data.value.unpublishedShifts === 1 ? 'it' : 'them' }}: you will see
          {{ schedule.data.value.unpublishedShifts === 1 ? 'it' : 'them' }} here once the roster is
          published.
        </NoticeBox>
        <NoticeBox v-if="schedule.data.value.openSwaps > 0" data-testid="open-swaps">
          {{ schedule.data.value.openSwaps }}
          {{ schedule.data.value.openSwaps === 1 ? 'shift swap is' : 'shift swaps are' }} waiting.
          <RouterLink to="/shift-swaps" class="font-medium text-brand-ink underline">
            Open shift swaps
          </RouterLink>
        </NoticeBox>

        <div
          v-if="view === 'month'"
          class="overflow-x-auto rounded-xl border border-line bg-surface"
        >
          <table
            class="w-full min-w-[40rem] table-fixed border-collapse text-sm"
            data-testid="month-grid"
          >
            <caption class="sr-only">
              {{
                monthLabel(month)
              }}
            </caption>
            <thead class="border-b border-line bg-surface-muted text-xs text-ink-muted">
              <tr>
                <th v-for="name in WEEKDAYS" :key="name" scope="col" class="px-2 py-2 font-medium">
                  {{ name }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="week in grid.weeks"
                :key="week[0]"
                class="border-b border-line align-top last:border-0"
              >
                <td
                  v-for="iso in week"
                  :key="iso"
                  class="h-24 border-l border-line p-1 first:border-l-0"
                  :class="monthOf(iso) !== month ? 'bg-surface-muted/60 text-ink-muted' : ''"
                  :data-testid="`day-${iso}`"
                >
                  <time
                    :datetime="iso"
                    class="inline-flex h-6 min-w-6 items-center justify-center rounded-full px-1 text-xs font-medium"
                    :class="iso === today ? 'bg-brand text-white' : ''"
                    :aria-label="formatDayLabel(iso)"
                  >
                    {{ dayNumber(iso) }}
                  </time>
                  <p
                    v-for="s in byDay.get(iso)?.shifts ?? []"
                    :key="s.shift + s.queue"
                    class="mt-1 rounded bg-brand-soft px-1 py-0.5 text-[11px] leading-tight text-brand-ink"
                  >
                    <span class="block font-semibold">{{ s.shift }}</span>
                    <span class="block tabular-nums">
                      {{ clock(s.startTime) }} to {{ clock(s.endTime) }}
                    </span>
                  </p>
                  <p
                    v-for="l in byDay.get(iso)?.leave ?? []"
                    :key="l.startDate + l.leaveType"
                    class="mt-1 rounded bg-warn-soft px-1 py-0.5 text-[11px] leading-tight text-warn"
                  >
                    {{ l.leaveType }}{{ SHORT_STATUS[l.status] ?? '' }}
                  </p>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <template v-else>
          <NoticeBox v-if="days.length === 0" data-testid="nothing-scheduled">
            Nothing is scheduled for you in this time.
          </NoticeBox>
          <ul v-else class="space-y-3" aria-label="My days">
            <li
              v-for="d in days"
              :key="d.day"
              class="rounded-xl border border-line bg-surface p-4"
              :data-testid="`day-${d.day}`"
            >
              <p class="text-sm font-semibold text-ink">{{ formatDayLabel(d.day) }}</p>
              <p v-for="s in d.shifts" :key="s.shift + s.queue" class="mt-1 text-sm text-ink">
                <span class="font-medium">{{ s.shift }}</span>
                <span class="tabular-nums"> {{ clock(s.startTime) }}-{{ clock(s.endTime) }}</span>
                <span class="text-ink-muted"> ({{ s.queue }})</span>
              </p>
              <p
                v-for="l in d.leave"
                :key="l.startDate + l.leaveType"
                class="mt-1 text-sm text-ink"
              >
                {{ l.leaveType }}
                <span class="text-ink-muted">({{ LEAVE_STATUS[l.status] ?? l.status }})</span>
              </p>
            </li>
          </ul>
        </template>
      </template>

      <p class="text-sm text-ink-muted">
        Need time off?
        <RouterLink to="/leave" class="font-medium text-brand-ink underline"
          >Ask for leave</RouterLink
        >
      </p>
    </template>
  </div>
</template>
