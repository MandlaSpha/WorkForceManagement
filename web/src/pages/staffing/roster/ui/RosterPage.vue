<script setup lang="ts">
import { computed, ref } from 'vue'

import { useSessionStore } from '@/entities/session'
import {
  SHIFT_KIND_LABEL,
  SHIFT_KINDS,
  SHIFT_TONE,
  formatHours,
  rosterExportUrl,
  useRoster,
} from '@/entities/scheduling'
import { ShiftCellSelect } from '@/features/assign-shift'
import { AutoScheduleButton } from '@/features/optimise/auto-schedule'
import { useContextStore } from '@/features/context-filters'
import { PublishRosterButton } from '@/features/publish-roster'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { formatDayLabel } from '@/shared/lib/datetime'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const session = useSessionStore()
const context = useContextStore()
const screen = NAV_ITEMS.find((item) => item.key === 'roster')
// Cosmetic: the API refuses changes from any other role.
const canChange = computed(() => ['planner', 'admin'].includes(session.user?.role ?? ''))

const roster = useRoster(
  computed(() => context.queueNumber),
  computed(() => context.weekStart),
)
const published = computed(() => roster.data.value?.status === 'published')
const editable = computed(() => canChange.value && !published.value)

const refusal = ref('')

const shiftIdOf = (row: { cells: ReadonlyArray<{ day: string; shiftId: number }> }, day: string) =>
  row.cells.find((c) => c.day === day)?.shiftId ?? null
</script>

<template>
  <PageHeader eyebrow="Operate" :title="screen?.label ?? 'Roster'" :subtitle="screen?.subtitle">
    <template v-if="roster.data.value && context.queueNumber !== null" #actions>
      <span
        class="rounded-full px-2.5 py-1 text-xs font-semibold capitalize"
        :class="published ? 'bg-brand-soft text-brand-ink' : 'bg-surface-muted text-ink-muted'"
        data-testid="roster-status"
      >
        {{ roster.data.value.status }}
      </span>
      <a
        :href="rosterExportUrl(context.queueNumber, context.weekStart)"
        class="inline-flex min-h-10 items-center rounded-lg border border-line bg-surface px-4 text-sm font-medium text-ink hover:bg-surface-muted"
        download
      >
        Export CSV
      </a>
      <PublishRosterButton
        v-if="canChange"
        :queue-id="context.queueNumber"
        :week-start="context.weekStart"
        :published="published"
      />
    </template>
  </PageHeader>

  <section class="space-y-4" aria-live="polite">
    <NoticeBox v-if="context.queueNumber === null">
      Choose a queue at the top of the page. Queues appear once call data has been imported.
    </NoticeBox>
    <p v-else-if="roster.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="roster.isError.value" tone="danger">
      Could not load the roster. {{ problemMessage(roster.error.value) }}
    </NoticeBox>

    <template v-else-if="roster.data.value">
      <NoticeBox v-if="published">
        This week is published, so it is locked. Return it to draft to change it.
      </NoticeBox>
      <NoticeBox v-else-if="!canChange">
        You can read the roster here. Planners and admins build it.
      </NoticeBox>

      <AutoScheduleButton
        v-if="editable && context.queueNumber !== null"
        :queue-id="context.queueNumber"
        :week-start="context.weekStart"
      />

      <NoticeBox v-if="refusal" tone="danger" data-testid="assign-refusal">
        <p class="font-medium">That change was not made.</p>
        <p>{{ refusal }}</p>
      </NoticeBox>

      <ul class="flex flex-wrap gap-2 text-xs" aria-label="Legend">
        <li
          v-for="kind in SHIFT_KINDS"
          :key="kind"
          class="rounded-full px-2.5 py-1 font-medium"
          :class="SHIFT_TONE[kind]"
        >
          {{ SHIFT_KIND_LABEL[kind] }}
        </li>
      </ul>

      <NoticeBox v-if="roster.data.value.rows.length === 0">
        Nobody is skilled on {{ roster.data.value.queue }} yet. Add people on the Employees screen.
      </NoticeBox>
      <NoticeBox v-else-if="roster.data.value.shifts.length === 0">
        There are no shift templates yet. An admin adds them in Configure.
      </NoticeBox>

      <div v-else class="overflow-x-auto rounded-xl border border-line bg-surface">
        <table class="w-full min-w-[56rem] text-left text-sm">
          <caption class="px-4 py-3 text-left text-sm font-semibold text-ink">
            Weekly roster,
            {{
              roster.data.value.queue
            }}:
            {{
              roster.data.value.rows.length
            }}
            people
          </caption>
          <thead class="border-y border-line bg-surface-muted text-xs text-ink-muted">
            <tr>
              <th scope="col" class="px-4 py-2 font-medium">Person</th>
              <th
                v-for="day in roster.data.value.days"
                :key="day"
                scope="col"
                class="px-2 py-2 font-medium"
              >
                {{ formatDayLabel(day) }}
                <span class="block font-normal" :data-testid="`on-${day}`">
                  {{ roster.data.value.onCounts[day] ?? 0 }} on
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in roster.data.value.rows"
              :key="row.employeeId"
              class="border-b border-line"
            >
              <th scope="row" class="px-4 py-2 font-normal">
                <span class="block font-medium text-ink">{{ row.name }}</span>
                <span class="block text-xs text-ink-muted">
                  {{ row.empNo }} · {{ row.daysWorked }}d {{ formatHours(row.paidMinutes) }} of
                  {{ row.weeklyHours }}h
                </span>
              </th>
              <td v-for="day in roster.data.value.days" :key="day" class="px-2 py-1.5">
                <ShiftCellSelect
                  :queue-id="roster.data.value.queueId"
                  :employee-id="row.employeeId"
                  :employee-name="row.name"
                  :day="day"
                  :day-label="formatDayLabel(day)"
                  :shifts="roster.data.value.shifts"
                  :current-shift-id="shiftIdOf(row, day)"
                  :editable="editable"
                  @assigned="refusal = ''"
                  @refused="refusal = $event"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>
