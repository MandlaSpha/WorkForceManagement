<script setup lang="ts">
import { computed } from 'vue'

import { useQueues } from '@/entities/call-data'
import {
  OUTCOME_LABEL,
  REPORT_LABEL,
  schedulesCsvUrl,
  useAllowedDomains,
  useSchedules,
  whenLabel,
} from '@/entities/report-schedule'
import { useSessionStore } from '@/entities/session'
import { DomainsForm } from '@/features/reports/domains'
import { ScheduleActions, ScheduleForm } from '@/features/reports/schedule'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { formatDateTime } from '@/shared/lib/datetime'
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

const rows = computed(() => schedules.data.value ?? [])
const activeCount = computed(() => rows.value.filter((s) => !s.paused).length)
const pausedCount = computed(() => rows.value.length - activeCount.value)

const outcomeChip = (o: string) =>
  o === 'failed' || o === 'stopped'
    ? 'bg-danger-soft text-danger'
    : o === 'sent'
      ? 'bg-ok-soft text-ok'
      : 'bg-surface-muted text-ink-muted'
</script>

<template>
  <PageHeader eyebrow="Insight" :title="screen?.label ?? 'Reports'">
    <template #subtitle>
      <template v-if="schedules.data.value && rows.length > 0">
        <strong class="font-semibold text-ink">{{ activeCount }}</strong>
        {{ activeCount === 1 ? 'report is' : 'reports are' }} scheduled to be emailed<template
          v-if="pausedCount > 0"
          >, and <strong class="font-semibold text-ink">{{ pausedCount }}</strong> paused</template
        >.
      </template>
      <template v-else>{{ screen?.subtitle }}</template>
    </template>
  </PageHeader>

  <section class="space-y-6" aria-live="polite">
    <ScheduleForm
      :queues="queues.data.value ?? []"
      :reports="reports"
      :domains="domains.data.value ?? []"
    />

    <section
      class="page-enter overflow-hidden rounded-3xl bg-surface shadow-[var(--shadow-card)]"
      aria-labelledby="schedules-title"
    >
      <h2
        id="schedules-title"
        class="px-5 pt-5 text-lg font-semibold tracking-tight text-ink sm:px-6"
      >
        {{ isAdmin ? 'All schedules' : 'Your schedules' }}
      </h2>
      <a
        v-if="rows.length > 0"
        :href="schedulesCsvUrl"
        download
        class="mx-5 mt-1 inline-block text-sm font-medium text-brand-ink underline sm:mx-6"
        data-testid="schedules-csv"
      >
        Download as CSV
      </a>
      <div v-if="schedules.isPending.value" class="space-y-2 p-5" data-testid="schedules-loading">
        <span class="sr-only">Loading…</span>
        <div v-for="n in 3" :key="n" class="skeleton h-12"></div>
      </div>
      <div v-else-if="schedules.isError.value" class="p-5">
        <NoticeBox tone="danger">
          Could not load schedules. {{ problemMessage(schedules.error.value) }}
        </NoticeBox>
      </div>
      <div v-else-if="rows.length === 0" class="p-5">
        <NoticeBox data-testid="no-schedules">No reports are scheduled.</NoticeBox>
      </div>
      <div v-else class="mt-3 overflow-x-auto">
        <table class="w-full min-w-[40rem] text-left text-sm" aria-labelledby="schedules-title">
          <thead class="border-y border-line bg-surface-muted text-xs text-ink-muted">
            <tr>
              <th scope="col" class="px-5 py-2 font-medium sm:px-6">Report</th>
              <th scope="col" class="px-3 py-2 font-medium">When and to whom</th>
              <th scope="col" class="px-3 py-2 font-medium">Last sent</th>
              <th scope="col" class="px-3 py-2 font-medium">Outcome</th>
              <th scope="col" class="px-5 py-2 text-right font-medium sm:px-6">
                <span class="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="s in rows"
              :key="s.id"
              class="border-b border-line align-top last:border-0"
              :data-testid="`schedule-${s.id}`"
            >
              <th scope="row" class="px-5 py-3 font-medium text-ink sm:px-6">
                {{ REPORT_LABEL[s.report] ?? s.report
                }}<template v-if="s.queue">: {{ s.queue }}</template>
                <span
                  v-if="s.paused"
                  class="ml-2 rounded-full bg-warn-soft px-2 py-0.5 text-[11px] font-semibold text-warn"
                  >Paused</span
                >
              </th>
              <td class="px-3 py-3 text-ink-muted">
                {{ whenLabel(s) }}, to {{ s.recipients.join(', ') }}
                <template v-if="isAdmin && s.owner"> (made by {{ s.owner }})</template>
              </td>
              <td class="px-3 py-3 tabular-nums text-ink-muted">
                {{ s.lastSentAt ? formatDateTime(s.lastSentAt) : 'Not yet' }}
              </td>
              <td class="px-3 py-3">
                <span
                  class="inline-block rounded-full px-2 py-0.5 text-[11px] font-semibold"
                  :class="outcomeChip(s.lastOutcome)"
                  data-testid="outcome"
                >
                  {{ OUTCOME_LABEL[s.lastOutcome] ?? s.lastOutcome }}
                </span>
              </td>
              <td class="px-5 py-2 sm:px-6">
                <ScheduleActions
                  :schedule-id="s.id"
                  :what="`${REPORT_LABEL[s.report] ?? s.report} schedule`"
                  :paused="s.paused"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <DomainsForm v-if="isAdmin" :domains="domains.data.value ?? []" />
  </section>
</template>
