<script setup lang="ts">
import { computed } from 'vue'

import { clock } from '@/entities/availability'
import { hoursLabel, summarise, upNext } from '@/entities/my-schedule'
import type { MyShift } from '@/entities/my-schedule'
import { formatDayLabel } from '@/shared/lib/datetime'

const props = defineProps<{
  /** Shifts that start inside the week shown. */
  weekShifts: MyShift[]
  /** Shifts to pick "up next" from (the week and what follows). */
  upcoming: MyShift[]
  today: string
  nowMinutes: number
}>()

const ACTIVITY: Record<string, string> = {
  break: 'Breaks',
  lunch: 'Lunch',
  training: 'Training',
  meeting: 'Meetings',
  coaching: 'Coaching',
  other: 'Other',
}

const summary = computed(() => summarise(props.weekShifts))
const next = computed(() => upNext(props.upcoming, props.today, props.nowMinutes, 3))
const hm = (minutes: number) =>
  `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')} min`
</script>

<template>
  <aside
    class="space-y-4 rounded-3xl bg-surface p-5 shadow-[var(--shadow-card)]"
    aria-labelledby="glance-title"
    data-testid="week-glance"
  >
    <h3 id="glance-title" class="text-base font-semibold text-ink">Week at a glance</h3>
    <dl class="grid grid-cols-2 gap-3">
      <div class="rounded-2xl bg-surface-muted p-3">
        <dt class="text-xs text-ink-muted">Paid hours</dt>
        <dd class="mt-1 text-xl font-semibold tabular-nums text-ink" data-testid="glance-hours">
          {{ hoursLabel(summary.paidHours) }}
        </dd>
      </div>
      <div class="rounded-2xl bg-surface-muted p-3">
        <dt class="text-xs text-ink-muted">Shifts</dt>
        <dd class="mt-1 text-xl font-semibold tabular-nums text-ink" data-testid="glance-shifts">
          {{ summary.shifts }}
        </dd>
      </div>
    </dl>

    <div v-if="summary.activityMinutes.length > 0">
      <h4 class="text-xs font-semibold uppercase tracking-wider text-ink-muted">By activity</h4>
      <ul class="mt-2 space-y-1 text-sm">
        <li
          v-for="a in summary.activityMinutes"
          :key="a.kind"
          class="flex justify-between"
          data-testid="glance-activity"
        >
          <span class="text-ink">{{ ACTIVITY[a.kind] ?? a.kind }}</span>
          <span class="tabular-nums text-ink-muted">{{ hm(a.minutes) }}</span>
        </li>
      </ul>
    </div>

    <div>
      <h4 class="text-xs font-semibold uppercase tracking-wider text-ink-muted">Up next</h4>
      <p v-if="next.length === 0" class="mt-2 text-sm text-ink-muted">No upcoming shifts.</p>
      <ol v-else class="mt-2 space-y-2" data-testid="up-next">
        <li
          v-for="s in next"
          :key="s.day + s.shift"
          class="rounded-2xl bg-surface-muted p-3 text-sm"
        >
          <span class="block font-medium text-ink">{{ s.shift }}</span>
          <span class="block tabular-nums text-ink-muted">
            {{ formatDayLabel(s.day) }}, {{ clock(s.startTime) }}-{{ clock(s.endTime) }}
          </span>
        </li>
      </ol>
    </div>
  </aside>
</template>
