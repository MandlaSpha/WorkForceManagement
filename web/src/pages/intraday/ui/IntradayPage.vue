<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { slotLabel, useIntraday } from '@/entities/intraday'
import { useSessionStore } from '@/entities/session'
import { useContextStore } from '@/features/context-filters'
import { ShortageActions } from '@/features/intraday/act'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import AppButton from '@/shared/ui/AppButton.vue'
import IntervalChart from '@/shared/ui/IntervalChart.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import StatTile from '@/shared/ui/StatTile.vue'

const context = useContextStore()
const screen = NAV_ITEMS.find((item) => item.key === 'intraday')

const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' })
const day = ref(today)
function step(days: number): void {
  const moved = new Date(Date.parse(`${day.value}T00:00:00Z`) + days * 86_400_000)
  day.value = moved.toISOString().slice(0, 10)
}
const queueId = computed(() => context.queueNumber)
const intraday = useIntraday(queueId, day)

const points = computed(() => {
  const all = (intraday.data.value?.slots ?? []).map((s, i) => ({
    label: slotLabel(i),
    // Calls: what came where the half-hour is over, what is now expected where it is not.
    bars: s.actual ?? s.reforecast ?? s.forecast ?? 0,
    line: s.scheduled,
  }))
  // The axis runs over the hours with calls or people, two half-hours either side, from an even
  // half-hour so the labels fall on whole hours.
  const busy = all.flatMap((p, i) => (p.bars > 0 || p.line > 0 ? [i] : []))
  if (busy.length === 0) return all
  const first = Math.max(0, Math.min(...busy) - 2)
  const last = Math.min(all.length - 1, Math.max(...busy) + 2)
  return all.slice(first - (first % 2), last + 1)
})

// Cosmetic: the API refuses suggestions to anyone but a planner or admin.
const session = useSessionStore()
const canAct = computed(() => ['planner', 'admin'].includes(session.user?.role ?? ''))
const openSlot = ref<number | null>(null)

/** Where the short stretch that begins at `slot` ends: the run of consecutive short half-hours. */
function runEnd(slot: number): string {
  const short = new Set((intraday.data.value?.alerts ?? []).map((a) => a.slot))
  let last = slot
  while (short.has(last + 1)) last += 1
  return last >= 47 ? '23:59' : slotLabel(last + 1)
}

const percent = computed(() =>
  intraday.data.value?.ratio == null ? null : Math.round(intraday.data.value.ratio * 100),
)
const through = computed(() =>
  intraday.data.value?.dataThrough == null ? null : slotLabel(intraday.data.value.dataThrough),
)
// With no forecast and no calls there is nothing to draw: the notice says so instead.
const showChart = computed(
  () => !!intraday.data.value && (intraday.data.value.hasForecast || through.value !== null),
)
const critical = computed(
  () => (intraday.data.value?.alerts ?? []).filter((a) => a.severity === 'critical').length,
)
</script>

<template>
  <PageHeader eyebrow="Operate" :title="screen?.label ?? 'Intraday'" :subtitle="screen?.subtitle" />

  <section class="space-y-4" aria-live="polite">
    <div class="flex flex-wrap items-center gap-2">
      <button
        type="button"
        class="press grid size-9 place-items-center rounded-lg border border-line bg-surface text-lg text-ink"
        aria-label="Earlier date"
        @click="step(-1)"
      >
        ‹
      </button>
      <label class="flex items-center gap-2 text-sm text-ink">
        Day
        <input
          v-model="day"
          type="date"
          class="rounded-lg border border-line bg-surface px-2 py-1"
        />
      </label>
      <button
        type="button"
        class="press grid size-9 place-items-center rounded-lg border border-line bg-surface text-lg text-ink"
        aria-label="Later date"
        @click="step(1)"
      >
        ›
      </button>
      <AppButton v-if="day !== today" variant="ghost" @click="day = today">Today</AppButton>
    </div>

    <NoticeBox v-if="context.queueNumber === null">
      Choose a queue at the top of the page. Queues appear once call data has been imported.
    </NoticeBox>
    <p v-else-if="intraday.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="intraday.isError.value" tone="danger" data-testid="intraday-error">
      Could not load the day. {{ problemMessage(intraday.error.value) }}
    </NoticeBox>

    <template v-else-if="intraday.data.value">
      <NoticeBox v-if="!intraday.data.value.hasForecast" data-testid="no-forecast">
        No forecast has been published for this day, so there is nothing to compare the calls with.
      </NoticeBox>

      <div class="grid gap-4 lg:grid-cols-3">
        <section
          v-if="showChart"
          aria-labelledby="chart-title"
          class="rounded-2xl border border-line bg-surface p-4 shadow-[var(--shadow-card)] lg:col-span-2"
        >
          <h2 id="chart-title" class="text-base font-semibold text-ink">
            Calls and people scheduled
          </h2>
          <IntervalChart
            :points="points"
            summary="Calls in each half-hour of the day as bars, and the people scheduled as a line"
            bar-label="Calls (actual, then expected)"
            line-label="People scheduled"
            :label-every="2"
          />
        </section>

        <ul
          class="grid content-start gap-3"
          :class="showChart ? '' : 'sm:grid-cols-3 lg:col-span-3'"
          aria-label="The day"
        >
          <StatTile
            label="The day so far"
            :value="percent ?? '-'"
            :format="(n) => `${Math.round(n)}% of forecast`"
            tint="brand"
            data-testid="running"
          >
            <template v-if="through">Calls are imported up to {{ through }}.</template>
            <template v-else>No calls imported for this day yet.</template>
          </StatTile>
          <StatTile
            label="Service level so far"
            :value="intraday.data.value.serviceLevelPct ?? '-'"
            :format="(n) => `${n.toFixed(1)}%`"
            tint="ok"
            data-testid="sl"
          />
          <StatTile
            label="Half-hours short to come"
            :value="intraday.data.value.alerts.length"
            :tint="critical > 0 ? 'danger' : 'warn'"
            data-testid="alert-count"
          >
            {{ critical }} critical
          </StatTile>
        </ul>
      </div>

      <section
        aria-labelledby="alerts-title"
        class="space-y-2 rounded-2xl border border-line bg-surface p-4 shadow-[var(--shadow-card)]"
      >
        <h2 id="alerts-title" class="text-base font-semibold text-ink">Where cover falls short</h2>
        <NoticeBox v-if="intraday.data.value.alerts.length === 0" data-testid="no-alerts">
          Nothing short for the rest of the day.
        </NoticeBox>
        <template v-else>
          <ul class="space-y-1 text-sm" aria-label="Alerts">
            <li v-for="a in intraday.data.value.alerts" :key="a.slot">
              <div class="flex items-center gap-2" :data-testid="`alert-${a.slot}`">
                <span
                  class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                  :class="
                    a.severity === 'critical'
                      ? 'bg-danger-soft text-danger'
                      : 'bg-warn-soft text-warn'
                  "
                >
                  {{ a.severity === 'critical' ? 'Critical' : 'Warning' }}
                </span>
                {{ slotLabel(a.slot) }}: {{ a.scheduled }} scheduled, {{ a.required }} needed ({{
                  a.short
                }}
                short)
                <AppButton
                  v-if="canAct && context.queueNumber !== null"
                  variant="ghost"
                  :aria-expanded="openSlot === a.slot"
                  :aria-label="`What can be done about ${slotLabel(a.slot)}`"
                  @click="openSlot = openSlot === a.slot ? null : a.slot"
                >
                  What can I do?
                </AppButton>
              </div>
              <ShortageActions
                v-if="canAct && context.queueNumber !== null && openSlot === a.slot"
                :queue-id="context.queueNumber"
                :day="day"
                :half-hour="a.slot"
                :from="slotLabel(a.slot)"
                :to="runEnd(a.slot)"
              />
            </li>
          </ul>
          <p class="text-sm text-ink-muted" data-testid="actions">
            To close the gap: ask for
            <RouterLink to="/overtime" class="font-medium text-brand-ink underline"
              >overtime</RouterLink
            >
            or look at the
            <RouterLink to="/recommendations" class="font-medium text-brand-ink underline">
              recommendations
            </RouterLink>
            for the week.
          </p>
        </template>
      </section>
    </template>
  </section>
</template>
