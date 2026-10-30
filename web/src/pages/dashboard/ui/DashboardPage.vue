<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { useKpis, useMonths } from '@/entities/call-data'
import { canOpen, isAvailable, useSessionStore } from '@/entities/session'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { greeting, longDay } from '@/shared/lib/datetime'
import { formatMonth } from '@/shared/lib/month'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import { PlanningOverview } from '@/widgets/planning-overview'
import { ServiceKpis } from '@/widgets/service-kpis'

const session = useSessionStore()
const dashboard = NAV_ITEMS.find((item) => item.key === 'dashboard')
const mayImport = computed(() => (session.user ? canOpen(session.user, 'imports') : false))
// Call data is a separate module: when it is not part of the plan there is nothing to load.
const hasCallData = computed(() =>
  session.user ? isAvailable(session.user.features, 'imports') : false,
)

// Shown on screen only: the name is never sent to telemetry or logs.
const now = new Date()
const today = longDay(now)
const hello = computed(() => greeting(now, session.user?.displayName))

const range = useMonths(hasCallData)
const months = computed(() => range.data.value?.months ?? [])

// Open on the latest month that has calls, not on an empty current week.
const chosen = ref('')
const month = computed(() =>
  months.value.includes(chosen.value) ? chosen.value : (months.value.at(-1) ?? null),
)
const selected = computed({
  get: () => month.value ?? '',
  set: (value: string) => (chosen.value = value),
})
const options = computed(() => months.value.map((m) => ({ value: m, label: formatMonth(m) })))

const kpis = useKpis(month)

// The calendar month before, when it has calls: the tiles compare with it.
const previousMonth = computed(() => {
  if (!month.value) return null
  const [year, mon] = month.value.split('-').map(Number)
  const d = new Date(year ?? 1970, (mon ?? 1) - 2, 1)
  const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  return months.value.includes(key) ? key : null
})
const previous = useKpis(previousMonth)

// The planning overview is the planner's: only those who may open the planner see it, and only
// when scheduling is part of the plan. The API refuses everyone else anyway.
const showPlanning = computed(
  () =>
    !!session.user &&
    canOpen(session.user, 'planner') &&
    isAvailable(session.user.features, 'planner'),
)
</script>

<template>
  <PageHeader :eyebrow="today" :title="hello" :subtitle="dashboard?.subtitle" />

  <div v-if="showPlanning" class="mb-8"><PlanningOverview /></div>

  <section class="space-y-4" aria-live="polite">
    <div v-if="months.length > 0" class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 class="text-base font-semibold text-ink" data-testid="service-title">
          Service figures{{ month ? ` · ${formatMonth(month)}` : '' }}
        </h2>
      </div>
      <div class="w-44">
        <SelectField v-model="selected" label="Month" :options="options" />
      </div>
    </div>

    <NoticeBox v-if="!hasCallData">
      Call data is not part of your plan, so there are no service figures to show here.
    </NoticeBox>

    <p v-else-if="range.isPending.value" class="text-sm text-ink-muted">Loading…</p>

    <NoticeBox v-else-if="range.isError.value" tone="danger">
      Could not check which months have call data. {{ problemMessage(range.error.value) }}
    </NoticeBox>

    <NoticeBox v-else-if="months.length === 0">
      There is no call data to show yet, so there are no figures rather than invented ones.
      <template v-if="mayImport">
        <RouterLink to="/imports" class="font-medium text-brand-ink underline">
          Import a call detail report
        </RouterLink>
        to see service figures here.
      </template>
      <template v-else>A planner or admin imports it from Data import.</template>
    </NoticeBox>

    <template v-else-if="month">
      <p v-if="kpis.isPending.value" class="text-sm text-ink-muted">
        Loading {{ formatMonth(month) }}…
      </p>
      <NoticeBox v-else-if="kpis.isError.value" tone="danger">
        Could not load the figures for {{ formatMonth(month) }}.
        {{ problemMessage(kpis.error.value) }}
      </NoticeBox>
      <ServiceKpis
        v-else-if="kpis.data.value"
        :summary="kpis.data.value"
        :period-label="formatMonth(month)"
        :month="month"
        :previous="previousMonth ? (previous.data.value ?? null) : null"
        :previous-label="previousMonth ? formatMonth(previousMonth) : undefined"
      />
    </template>
  </section>
</template>
