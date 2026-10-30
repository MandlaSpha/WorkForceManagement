<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { shareLabel, slotLabel, usePlan, varianceLabel } from '@/entities/scheduling'
import { useContextStore } from '@/features/context-filters'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { formatDayLabel } from '@/shared/lib/datetime'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import StatTile from '@/shared/ui/StatTile.vue'
import SelectField from '@/shared/ui/SelectField.vue'

import DayView from './DayView.vue'
import HeatmapGrid from './HeatmapGrid.vue'

const context = useContextStore()
const screen = NAV_ITEMS.find((item) => item.key === 'planner')

const plan = usePlan(
  computed(() => context.queueNumber),
  computed(() => context.weekStart),
)

const view = ref<'week' | 'day'>('week')
const chosenDay = ref('')
const day = computed(() =>
  plan.data.value?.days.includes(chosenDay.value)
    ? chosenDay.value
    : (plan.data.value?.days[0] ?? ''),
)
const dayOptions = computed(() =>
  (plan.data.value?.days ?? []).map((d) => ({ value: d, label: formatDayLabel(d) })),
)
const selectedDay = computed({ get: () => day.value, set: (v: string) => (chosenDay.value = v) })

function open(clicked: string): void {
  chosenDay.value = clicked
  view.value = 'day'
}

const summary = computed(() => plan.data.value?.summary)
const rosterLabel = computed(() => {
  const status = plan.data.value?.rosterStatus ?? ''
  return status.charAt(0).toUpperCase() + status.slice(1)
})
const worst = computed(() => {
  const w = summary.value?.worst
  return w ? `${varianceLabel(w)} at ${slotLabel(w.slot)} on ${formatDayLabel(w.day)}` : null
})
const totalHalfHours = 7 * 48
</script>

<template>
  <PageHeader eyebrow="Operate" :title="screen?.label ?? 'Planner'" :subtitle="screen?.subtitle">
    <template v-if="plan.data.value" #actions>
      <div
        class="inline-flex rounded-lg border border-line bg-surface"
        role="group"
        aria-label="View"
      >
        <button
          type="button"
          class="min-h-9 rounded-l-lg px-3 text-sm"
          :class="view === 'week' ? 'bg-brand-soft font-medium text-brand-ink' : 'text-ink-muted'"
          :aria-pressed="view === 'week'"
          @click="view = 'week'"
        >
          Week heatmap
        </button>
        <button
          type="button"
          class="min-h-9 rounded-r-lg px-3 text-sm"
          :class="view === 'day' ? 'bg-brand-soft font-medium text-brand-ink' : 'text-ink-muted'"
          :aria-pressed="view === 'day'"
          @click="view = 'day'"
        >
          Day chart
        </button>
      </div>
    </template>
  </PageHeader>

  <section class="space-y-4" aria-live="polite">
    <NoticeBox v-if="context.queueNumber === null">
      Choose a queue at the top of the page. Queues appear once call data has been imported.
    </NoticeBox>
    <p v-else-if="plan.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="plan.isError.value" tone="danger">
      Could not load the plan. {{ problemMessage(plan.error.value) }}
    </NoticeBox>

    <template v-else-if="plan.data.value && summary">
      <NoticeBox v-if="plan.data.value.forecast === null" data-testid="no-forecast">
        There is no published forecast for {{ plan.data.value.queue }}, so there is no requirement
        to compare the roster with. Run and publish one on the
        <RouterLink to="/forecast" class="font-medium text-brand-ink underline"
          >Forecast</RouterLink
        >
        screen.
      </NoticeBox>

      <ul class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Week summary">
        <StatTile
          label="Under-staffed half-hours"
          :value="shareLabel(summary.underIntervals, summary.intervalsKnown)"
          tint="danger"
          data-testid="kpi-under"
        />
        <StatTile
          label="Coverage gap"
          :value="summary.intervalsKnown === 0 ? '—' : summary.gap"
          tint="warn"
          data-testid="kpi-gap"
        >
          {{ summary.scheduledTotal }} scheduled · {{ summary.requiredTotal }} required
        </StatTile>
        <StatTile
          label="Worst half-hour"
          :value="worst ?? (summary.intervalsKnown === 0 ? '—' : 'None')"
          tint="brand"
          data-testid="kpi-worst"
        />
        <StatTile
          label="Roster"
          :value="rosterLabel"
          :tint="plan.data.value.rosterStatus === 'published' ? 'ok' : undefined"
          data-testid="kpi-roster"
        />
      </ul>

      <HeatmapGrid v-if="view === 'week'" :plan="plan.data.value" @select-day="open" />
      <template v-else>
        <div class="w-44">
          <SelectField v-model="selectedDay" label="Day" :options="dayOptions" />
        </div>
        <DayView :plan="plan.data.value" :day="day" />
      </template>

      <template v-if="plan.data.value.forecast !== null">
        <NoticeBox
          v-if="!plan.data.value.forecast.assumptionsConfirmed"
          tone="warn"
          data-testid="assumptions-notice"
        >
          The requirement rests on staffing assumptions for {{ plan.data.value.queue }} that nobody
          has confirmed yet. An admin confirms them in Configure.
        </NoticeBox>
        <NoticeBox v-if="summary.intervalsKnown < totalHalfHours" data-testid="partial-notice">
          The published forecast covers {{ summary.intervalsKnown }} of the week's
          {{ totalHalfHours }} half-hours. The rest show a dot: no requirement is known there.
        </NoticeBox>
      </template>
    </template>
  </section>
</template>
