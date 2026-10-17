<script setup lang="ts">
import { computed } from 'vue'

import { useQueues } from '@/entities/call-data'
import {
  OUTCOME_LABEL,
  REPORT_LABEL,
  useAllowedDomains,
  useSchedules,
  whenLabel,
} from '@/entities/report-schedule'
import { useSessionStore } from '@/entities/session'
import { DomainsForm } from '@/features/reports/domains'
import { ScheduleActions, ScheduleForm } from '@/features/reports/schedule'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'reports')
const session = useSessionStore()
const role = computed(() => session.user?.role ?? '')
const isAdmin = computed(() => role.value === 'admin')
// Cosmetic: the API refuses a role the report it may not see.
const reports = computed(() =>
  role.value === 'lead' ? ['peaks'] : ['scorecard', 'peaks', 'board'],
)

const schedules = useSchedules()
const domains = useAllowedDomains()
const queues = useQueues()

const outcomeTone = (o: string) =>
  o === 'failed' || o === 'stopped' ? 'text-danger' : 'text-ink-muted'
</script>

<template>
  <PageHeader eyebrow="Insight" :title="screen?.label ?? 'Reports'" :subtitle="screen?.subtitle" />

  <section class="space-y-6" aria-live="polite">
    <ScheduleForm
      :queues="queues.data.value ?? []"
      :reports="reports"
      :domains="domains.data.value ?? []"
    />

    <div class="space-y-2">
      <h2 class="text-base font-semibold text-ink">
        {{ isAdmin ? 'All schedules' : 'Your schedules' }}
      </h2>
      <p v-if="schedules.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="schedules.isError.value" tone="danger">
        Could not load schedules. {{ problemMessage(schedules.error.value) }}
      </NoticeBox>
      <NoticeBox v-else-if="(schedules.data.value ?? []).length === 0" data-testid="no-schedules">
        No reports are scheduled.
      </NoticeBox>
      <ul v-else class="space-y-2" aria-label="Schedules">
        <li
          v-for="s in schedules.data.value"
          :key="s.id"
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface p-4"
          :data-testid="`schedule-${s.id}`"
        >
          <div class="text-sm">
            <p class="font-medium text-ink">
              {{ REPORT_LABEL[s.report] ?? s.report
              }}<template v-if="s.queue">: {{ s.queue }}</template>
              <span v-if="s.paused" class="ml-2 text-xs font-normal text-warn">Paused</span>
            </p>
            <p class="text-xs text-ink-muted">
              {{ whenLabel(s) }}, to {{ s.recipients.join(', ') }}
              <template v-if="isAdmin && s.owner"> (made by {{ s.owner }})</template>
            </p>
            <p class="text-xs" :class="outcomeTone(s.lastOutcome)" data-testid="outcome">
              {{ OUTCOME_LABEL[s.lastOutcome] ?? s.lastOutcome }}
            </p>
          </div>
          <ScheduleActions
            :schedule-id="s.id"
            :what="`${REPORT_LABEL[s.report] ?? s.report} schedule`"
            :paused="s.paused"
          />
        </li>
      </ul>
    </div>

    <DomainsForm v-if="isAdmin" :domains="domains.data.value ?? []" />
  </section>
</template>
