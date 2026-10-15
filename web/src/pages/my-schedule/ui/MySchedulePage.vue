<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { clock } from '@/entities/availability'
import { daysWithSomething, useMySchedule } from '@/entities/my-schedule'
import { ApiProblem, problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { formatDayLabel } from '@/shared/lib/datetime'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'my-schedule')
const schedule = useMySchedule()
const noRecord = computed(
  () =>
    schedule.error.value instanceof ApiProblem &&
    schedule.error.value.code === 'schedule.no_employee_record',
)
const days = computed(() => {
  const s = schedule.data.value
  return s ? daysWithSomething(s.shifts, s.leave, s.fromDate, s.toDate) : []
})

const LEAVE_STATUS: Record<string, string> = {
  approved: 'approved',
  pending: 'waiting for a decision',
}
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
    <p v-else-if="schedule.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="schedule.isError.value" tone="danger">
      Could not load your schedule. {{ problemMessage(schedule.error.value) }}
    </NoticeBox>
    <template v-else-if="schedule.data.value">
      <p class="text-sm text-ink-muted">
        Your published shifts and leave from {{ formatDayLabel(schedule.data.value.fromDate) }} to
        {{ formatDayLabel(schedule.data.value.toDate) }}.
      </p>

      <NoticeBox v-if="schedule.data.value.unpublishedShifts > 0" data-testid="unpublished">
        {{ schedule.data.value.unpublishedShifts }}
        {{ schedule.data.value.unpublishedShifts === 1 ? 'shift is' : 'shifts are' }} not published
        yet, so {{ schedule.data.value.unpublishedShifts === 1 ? 'it is' : 'they are' }} not shown.
        They can still change.
      </NoticeBox>
      <NoticeBox v-if="schedule.data.value.openSwaps > 0" data-testid="open-swaps">
        {{ schedule.data.value.openSwaps }}
        {{ schedule.data.value.openSwaps === 1 ? 'shift swap is' : 'shift swaps are' }} waiting.
        <RouterLink to="/shift-swaps" class="font-medium text-brand-ink underline">
          Open shift swaps
        </RouterLink>
      </NoticeBox>

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
          <p v-for="l in d.leave" :key="l.startDate + l.leaveType" class="mt-1 text-sm text-ink">
            {{ l.leaveType }}
            <span class="text-ink-muted">({{ LEAVE_STATUS[l.status] ?? l.status }})</span>
          </p>
        </li>
      </ul>

      <p class="text-sm text-ink-muted">
        Need time off?
        <RouterLink to="/leave" class="font-medium text-brand-ink underline"
          >Ask for leave</RouterLink
        >
      </p>
    </template>
  </div>
</template>
