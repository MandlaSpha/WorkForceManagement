<script setup lang="ts">
import { computed, ref } from 'vue'

import { useMonths } from '@/entities/call-data'
import { useCallDetail, type CallDetailEvent } from '@/entities/call-data'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { formatMonth } from '@/shared/lib/month'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import StatTile from '@/shared/ui/StatTile.vue'
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

// Each part is a card; its table is given the same padding and header look as the other screens.
const CARD =
  'overflow-x-auto rounded-2xl border border-line bg-surface p-4 shadow-[var(--shadow-card)] ' +
  '[&_table]:w-full [&_th]:px-3 [&_td]:px-3 [&_th]:py-2 [&_td]:py-2 [&_thead]:bg-surface-muted ' +
  '[&_tbody_tr]:border-t [&_tbody_tr]:border-line [&_caption]:pb-2'

// Headline figures, each only when its sheet was in the import.
const rate = (part: number, whole: number): string =>
  whole > 0 ? `${((part / whole) * 100).toFixed(1)}%` : NONE
const sum = <T,>(rows: readonly T[], pick: (row: T) => number): number =>
  rows.reduce((total, row) => total + pick(row), 0)

const headline = computed(() => {
  const d = detail.data.value
  if (!d) return []
  const tiles: Array<{
    key: string
    label: string
    value: string
    note: string
    tint: 'brand' | 'ok' | 'warn' | 'danger'
  }> = []
  if (d.agentsAllowed && d.agents && d.agents.length > 0) {
    tiles.push({
      key: 'ring',
      label: 'Ring-no-answer',
      value: rate(
        sum(d.agents, (a) => a.ringNoAnswer),
        sum(d.agents, (a) => a.offers),
      ),
      note: `${count(sum(d.agents, (a) => a.ringNoAnswer))} of ${count(sum(d.agents, (a) => a.offers))} offers`,
      tint: 'warn',
    })
  }
  if (d.ivr && d.ivr.length > 0) {
    tiles.push({
      key: 'ivr',
      label: 'Ended in the IVR',
      value: rate(
        sum(d.ivr, (q) => q.endedInIvr),
        sum(d.ivr, (q) => q.calls),
      ),
      note: `${count(sum(d.ivr, (q) => q.endedInIvr))} of ${count(sum(d.ivr, (q) => q.calls))} calls`,
      tint: 'brand',
    })
  }
  if (totals.value.length > 0) {
    tiles.push({
      key: 'transfers',
      label: 'Transfers',
      value: count(sum(totals.value, (e) => e.transfers ?? 0)),
      note: 'in the month',
      tint: 'ok',
    })
    tiles.push({
      key: 'holds',
      label: 'Holds',
      value: count(sum(totals.value, (e) => e.holds ?? 0)),
      note: 'in the month',
      tint: 'danger',
    })
  }
  return tiles
})

// With none of the four sheets in the import there is nothing to lay out: one card says so.
const missing = computed(() => {
  const d = detail.data.value
  if (!d) return []
  const out: Array<{ key: string; text: string }> = []
  if (d.agentsAllowed && !d.sheets.ring)
    out.push({ key: 'ring-nodata', text: 'the Agent Offered Call sheet' })
  if (d.ivr === null) out.push({ key: 'ivr-nodata', text: 'the Call IVR Details sheet' })
  if (d.eventsByQueue === null)
    out.push({ key: 'events-nodata', text: 'the transfer, hold and mute sheets' })
  if (d.incidentsAllowed && d.incidents === null)
    out.push({ key: 'incidents-nodata', text: 'the Call Disposition Details sheet' })
  return out
})
const allMissing = computed(() => {
  const d = detail.data.value
  if (!d) return false
  const wanted = 2 + (d.agentsAllowed ? 1 : 0) + (d.incidentsAllowed ? 1 : 0)
  return missing.value.length === wanted
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

    <section
      v-else-if="detail.data.value && allMissing"
      :class="CARD"
      aria-labelledby="cd-missing"
      data-testid="call-detail-missing"
    >
      <h2 id="cd-missing" class="text-base font-semibold text-ink">Not in this month's import</h2>
      <ul class="mt-2 space-y-1 text-sm text-ink-muted">
        <li v-for="m in missing" :key="m.key" :data-testid="m.key">
          {{ NO_DATA }}: {{ m.text }} was not in the import for this month.
        </li>
      </ul>
    </section>

    <template v-else-if="detail.data.value">
      <ul
        v-if="headline.length > 0"
        class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        aria-label="Headline figures"
      >
        <StatTile
          v-for="t in headline"
          :key="t.key"
          :label="t.label"
          :value="t.value"
          :tint="t.tint"
          :data-testid="`tile-${t.key}`"
        >
          {{ t.note }}
        </StatTile>
      </ul>

      <!-- (a) Ring-no-answer by agent -->
      <section v-if="detail.data.value.agentsAllowed" :class="CARD" aria-labelledby="cd-ring">
        <h2 id="cd-ring" class="text-base font-semibold text-ink">Ring-no-answer by agent</h2>
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
      <section :class="CARD" aria-labelledby="cd-ivr">
        <h2 id="cd-ivr" class="text-base font-semibold text-ink">IVR menu and drop-off</h2>
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
      <section :class="CARD" aria-labelledby="cd-events">
        <h2 id="cd-events" class="text-base font-semibold text-ink">Transfers, holds and mutes</h2>
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
      <section v-if="detail.data.value.incidentsAllowed" :class="CARD" aria-labelledby="cd-inc">
        <h2 id="cd-inc" class="text-base font-semibold text-ink">Incident links</h2>
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
