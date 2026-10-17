<script setup lang="ts">
import { computed, ref } from 'vue'

import { useMonths } from '@/entities/call-data'
import { useCallDetail, type CallDetailEvent } from '@/entities/call-data'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { formatMonth } from '@/shared/lib/month'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import SelectField from '@/shared/ui/SelectField.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'call-detail')
const NO_DATA = 'No data'
const NONE = '—'

const range = useMonths()
const months = computed(() => range.data.value?.months ?? [])
const chosen = ref('')
const month = computed(() =>
  months.value.includes(chosen.value) ? chosen.value : (months.value.at(-1) ?? null),
)
const selected = computed({
  get: () => month.value ?? '',
  set: (value: string) => (chosen.value = value),
})
const options = computed(() => months.value.map((m) => ({ value: m, label: formatMonth(m) })))
const detail = useCallDetail(month)

/** A figure that may be missing: an unknown value is a dash, never a zero. */
function fig(value: string | number | null | undefined, suffix = ''): string {
  return value === null || value === undefined ? NONE : `${value}${suffix}`
}
/** A count whose sheet was not in the import is "No data", which is not the same as 0. */
function count(value: number | null): string {
  return value === null ? NO_DATA : String(value)
}

const totals = computed<CallDetailEvent[]>(
  () => detail.data.value?.eventsByQueue?.filter((e) => e.day === null) ?? [],
)
const days = computed<CallDetailEvent[]>(
  () => detail.data.value?.eventsByDay?.filter((e) => e.day !== null) ?? [],
)
const scopeText = computed(() => {
  const scope = detail.data.value?.scope
  if (scope === 'team') return 'Only agents in your own team are listed.'
  if (scope === 'all') return 'All agents with a login are listed, mapped to people where known.'
  return ''
})
</script>

<template>
  <PageHeader
    eyebrow="Insight"
    :title="screen?.label ?? 'Call detail'"
    :subtitle="screen?.subtitle"
  >
    <template v-if="months.length > 0" #actions>
      <div class="w-44">
        <SelectField v-model="selected" label="Month" :options="options" />
      </div>
    </template>
  </PageHeader>

  <section class="space-y-8" aria-live="polite">
    <p v-if="range.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="months.length === 0">
      There is no call data yet, so there are no call-detail figures. A planner or admin imports a
      Call Detail Report from Data import.
    </NoticeBox>
    <p v-else-if="detail.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="detail.isError.value" tone="danger" data-testid="call-detail-error">
      Could not load the call detail. {{ problemMessage(detail.error.value) }}
    </NoticeBox>

    <template v-else-if="detail.data.value">
      <!-- (a) Ring-no-answer by agent -->
      <section v-if="detail.data.value.agentsAllowed" aria-labelledby="cd-ring">
        <h2 id="cd-ring" class="text-sm font-semibold text-ink">Ring-no-answer by agent</h2>
        <p class="mt-1 text-xs text-ink-muted">
          Rests on the Agent Offered Call sheet: every call offered to an agent's phone, and whether
          that agent took it. Listed in employee-number order, not ranked, with no team average.
          {{ scopeText }}
        </p>
        <NoticeBox v-if="!detail.data.value.sheets.ring" data-testid="ring-nodata">
          {{ NO_DATA }}: the Agent Offered Call sheet was not in the import for this month.
        </NoticeBox>
        <p v-else-if="detail.data.value.agents?.length === 0" class="mt-2 text-sm">
          No offers to show for this month.
        </p>
        <table v-else class="mt-2 w-full text-left text-sm" data-testid="ring-table">
          <thead class="text-xs text-ink-muted">
            <tr>
              <th scope="col">Employee</th>
              <th scope="col">Login</th>
              <th scope="col">Offers</th>
              <th scope="col">Answered</th>
              <th scope="col">Ring-no-answer</th>
              <th scope="col">Rate</th>
              <th scope="col">Average ring</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in detail.data.value.agents" :key="a.login">
              <td>
                {{ a.employeeNumber ? `${a.employeeNumber} ${a.employeeName}` : 'Not mapped' }}
              </td>
              <td>{{ a.login }}</td>
              <td>{{ a.offers }}</td>
              <td>{{ a.answered }}</td>
              <td>{{ a.ringNoAnswer }}</td>
              <td>{{ fig(a.ringNoAnswerPct, '%') }}</td>
              <td>{{ fig(a.avgRingS, ' s') }}</td>
            </tr>
          </tbody>
        </table>
      </section>
      <NoticeBox v-else data-testid="ring-hidden">
        Per-agent figures are not shown to your role. Everything below is aggregate.
      </NoticeBox>

      <!-- (b) IVR -->
      <section aria-labelledby="cd-ivr">
        <h2 id="cd-ivr" class="text-sm font-semibold text-ink">IVR menu and drop-off</h2>
        <p class="mt-1 text-xs text-ink-muted">
          Rests on the Call IVR Details sheet and on whether the call was later put in the queue.
          "Ended in IVR" means the call never reached the queue; "abandoned after IVR" reached the
          queue and was abandoned there. Aggregate per queue; no caller digits are kept.
        </p>
        <NoticeBox v-if="detail.data.value.ivr === null" data-testid="ivr-nodata">
          {{ NO_DATA }}: the Call IVR Details sheet was not in the import for this month.
        </NoticeBox>
        <p v-else-if="detail.data.value.ivr.length === 0" class="mt-2 text-sm">
          No calls went through the IVR this month.
        </p>
        <div v-for="q in detail.data.value.ivr ?? []" :key="q.queue" class="mt-3">
          <h3 class="text-sm font-medium">{{ q.queue }}</h3>
          <p class="text-sm" :data-testid="`ivr-${q.queue}`">
            {{ q.calls }} calls through the IVR: {{ q.reachedQueue }} reached the queue,
            {{ q.endedInIvr }} ended in the IVR, {{ q.abandonedAfterIvr }} abandoned after the IVR.
          </p>
          <table class="mt-1 w-full text-left text-sm">
            <thead class="text-xs text-ink-muted">
              <tr>
                <th scope="col">Step</th>
                <th scope="col">Key</th>
                <th scope="col">Menu</th>
                <th scope="col">Calls</th>
                <th scope="col">Ended here</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in q.steps" :key="`${s.step}-${s.digit}-${s.activity}`">
                <td>{{ s.step }}</td>
                <td>{{ s.digit || NONE }}</td>
                <td>{{ s.activity || NONE }}</td>
                <td>{{ s.calls }}</td>
                <td>{{ s.endedHere }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- (c) Transfers, hold, mute -->
      <section aria-labelledby="cd-events">
        <h2 id="cd-events" class="text-sm font-semibold text-ink">Transfers, holds and mutes</h2>
        <p class="mt-1 text-xs text-ink-muted">
          Rests on the Transfer, Hold and Mute detail sheets, by the day the call started. A column
          reads "{{ NO_DATA }}" when its sheet was not in the import; a real zero is shown as 0.
        </p>
        <NoticeBox v-if="detail.data.value.eventsByQueue === null" data-testid="events-nodata">
          {{ NO_DATA }}: none of the transfer, hold or mute sheets were in the import for this
          month.
        </NoticeBox>
        <template v-else>
          <table class="mt-2 w-full text-left text-sm" data-testid="events-queue">
            <caption class="text-left text-xs text-ink-muted">
              Per queue, for the month
            </caption>
            <thead class="text-xs text-ink-muted">
              <tr>
                <th scope="col">Queue</th>
                <th scope="col">Transfers</th>
                <th scope="col">Avg transfer talk</th>
                <th scope="col">Holds</th>
                <th scope="col">Avg hold</th>
                <th scope="col">Mutes</th>
                <th scope="col">Avg mute</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="e in totals" :key="e.queue">
                <td>{{ e.queue }}</td>
                <td>{{ count(e.transfers) }}</td>
                <td>{{ fig(e.avgTransferS, ' s') }}</td>
                <td>{{ count(e.holds) }}</td>
                <td>{{ fig(e.avgHoldS, ' s') }}</td>
                <td>{{ count(e.mutes) }}</td>
                <td>{{ fig(e.avgMuteS, ' s') }}</td>
              </tr>
            </tbody>
          </table>
          <table class="mt-4 w-full text-left text-sm" data-testid="events-day">
            <caption class="text-left text-xs text-ink-muted">
              Per queue and day
            </caption>
            <thead class="text-xs text-ink-muted">
              <tr>
                <th scope="col">Queue</th>
                <th scope="col">Day</th>
                <th scope="col">Transfers</th>
                <th scope="col">Holds</th>
                <th scope="col">Avg hold</th>
                <th scope="col">Mutes</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="e in days" :key="`${e.queue}-${e.day}`">
                <td>{{ e.queue }}</td>
                <td>{{ e.day }}</td>
                <td>{{ count(e.transfers) }}</td>
                <td>{{ count(e.holds) }}</td>
                <td>{{ fig(e.avgHoldS, ' s') }}</td>
                <td>{{ count(e.mutes) }}</td>
              </tr>
            </tbody>
          </table>
        </template>
      </section>

      <!-- (d) Incident links -->
      <section v-if="detail.data.value.incidentsAllowed" aria-labelledby="cd-inc">
        <h2 id="cd-inc" class="text-sm font-semibold text-ink">Incident links</h2>
        <p class="mt-1 text-xs text-ink-muted">
          Rests on the Call Disposition Details sheet: the first ITSM incident number found in an
          agent's remark. The remark itself is never kept. Incident numbers are not personal data.
        </p>
        <NoticeBox v-if="detail.data.value.incidents === null" data-testid="incidents-nodata">
          {{ NO_DATA }}: the Call Disposition Details sheet was not in the import for this month.
        </NoticeBox>
        <p v-else-if="detail.data.value.incidents.length === 0" class="mt-2 text-sm">
          No call carried an incident number this month.
        </p>
        <div v-for="q in detail.data.value.incidents ?? []" :key="q.queue" class="mt-3">
          <h3 class="text-sm font-medium">{{ q.queue }}</h3>
          <p class="text-sm" :data-testid="`incidents-${q.queue}`">
            {{ q.callsWithIncident }} calls linked to {{ q.incidents.length }} incidents:
            {{ q.incidents.join(', ') }}
          </p>
        </div>
      </section>
    </template>
  </section>
</template>
