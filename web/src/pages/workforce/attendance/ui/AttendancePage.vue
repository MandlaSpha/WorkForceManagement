<script setup lang="ts">
import { computed, ref } from 'vue'

import { useSessionStore } from '@/entities/session'
import { EXCEPTION_LABEL, useAdherence } from '@/entities/workforce/attendance'
import { StateImportPanel } from '@/features/attendance/import-states'
import { useContextStore } from '@/features/context-filters'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { todayInJohannesburg } from '@/shared/lib/week'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const context = useContextStore()
const session = useSessionStore()
const screen = NAV_ITEMS.find((item) => item.key === 'attendance')

const day = ref(todayInJohannesburg())
const queueId = computed(() => context.queueNumber)
const adherence = useAdherence(queueId, day)
// Cosmetic: the API refuses anyone but a planner or admin.
const canImport = computed(() => ['planner', 'admin'].includes(session.user?.role ?? ''))

const pct = (v: number | null) => (v === null ? '-' : `${v.toFixed(1)}%`)
</script>

<template>
  <PageHeader
    eyebrow="People"
    :title="screen?.label ?? 'Attendance'"
    :subtitle="screen?.subtitle"
  />

  <div class="space-y-4">
    <StateImportPanel v-if="canImport" />

    <section class="space-y-4" aria-live="polite">
      <label class="flex items-center gap-2 text-sm text-ink">
        Day
        <input
          v-model="day"
          type="date"
          class="rounded-lg border border-line bg-surface px-2 py-1"
        />
      </label>

      <NoticeBox v-if="context.queueNumber === null">
        Choose a queue at the top of the page. Queues appear once call data has been imported.
      </NoticeBox>
      <p v-else-if="adherence.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="adherence.isError.value" tone="danger" data-testid="attendance-error">
        Could not load the day. {{ problemMessage(adherence.error.value) }}
      </NoticeBox>

      <template v-else-if="adherence.data.value">
        <div class="grid gap-3 sm:grid-cols-3">
          <div class="rounded-xl border border-line bg-surface p-4" data-testid="team-adherence">
            <p class="text-xs text-ink-muted">Adherence of people with data</p>
            <p class="text-lg font-semibold text-ink">
              {{ pct(adherence.data.value.teamAdherencePct) }}
            </p>
          </div>
          <div class="rounded-xl border border-line bg-surface p-4" data-testid="with-data">
            <p class="text-xs text-ink-muted">People measured</p>
            <p class="text-lg font-semibold text-ink">{{ adherence.data.value.withData }}</p>
          </div>
          <div class="rounded-xl border border-line bg-surface p-4" data-testid="without-data">
            <p class="text-xs text-ink-muted">No agent-state data yet</p>
            <p class="text-lg font-semibold text-ink">{{ adherence.data.value.withoutData }}</p>
          </div>
        </div>

        <NoticeBox v-if="adherence.data.value.people.length === 0" data-testid="nobody">
          Nobody is on a published roster for this queue and day (or nobody in your team).
        </NoticeBox>
        <div v-else class="overflow-x-auto rounded-xl border border-line bg-surface">
          <table class="w-full text-left text-sm">
            <caption class="sr-only">
              Adherence for each person rostered on the queue
            </caption>
            <thead class="text-xs text-ink-muted">
              <tr>
                <th scope="col" class="px-3 py-2">Person</th>
                <th scope="col" class="px-3 py-2">Shift</th>
                <th scope="col" class="px-3 py-2">Scheduled (min)</th>
                <th scope="col" class="px-3 py-2">Out of adherence (min)</th>
                <th scope="col" class="px-3 py-2">Adherence</th>
                <th scope="col" class="px-3 py-2">Exceptions</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="p in adherence.data.value.people"
                :key="p.employeeId"
                class="border-t border-line"
                :data-testid="`row-${p.empNo}`"
              >
                <th scope="row" class="px-3 py-2 font-medium text-ink">
                  {{ p.employee }} <span class="text-ink-muted">({{ p.empNo }})</span>
                </th>
                <td class="px-3 py-2">{{ p.shiftCode }}</td>
                <td class="px-3 py-2">{{ p.scheduledMin }}</td>
                <template v-if="p.hasData">
                  <td class="px-3 py-2">{{ p.outOfAdherenceMin }}</td>
                  <td class="px-3 py-2 font-semibold">{{ pct(p.adherencePct) }}</td>
                  <td class="px-3 py-2">
                    <span v-if="p.exceptions.length === 0" class="text-ink-muted">None</span>
                    <ul v-else class="flex flex-wrap gap-1" aria-label="Exceptions">
                      <li
                        v-for="e in p.exceptions"
                        :key="e"
                        class="rounded-full bg-warn-soft px-2 py-0.5 text-[11px] font-semibold text-warn"
                      >
                        {{ EXCEPTION_LABEL[e] ?? e }}
                        <template v-if="e === 'late_start'"> ({{ p.lateStartMin }} min)</template>
                        <template v-if="e === 'early_finish'">
                          ({{ p.earlyFinishMin }} min)</template
                        >
                      </li>
                    </ul>
                  </td>
                </template>
                <td v-else colspan="3" class="px-3 py-2 text-ink-muted">
                  No agent-state data for this shift
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </section>
  </div>
</template>
