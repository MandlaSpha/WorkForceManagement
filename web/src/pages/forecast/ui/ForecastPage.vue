<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useQueues } from '@/entities/call-data'
import { useVersions, type ForecastView } from '@/entities/forecast'
import { useSessionStore } from '@/entities/session'
import { EventsPanel } from '@/features/manage-events'
import { RunForecastForm } from '@/features/run-forecast'
import { ScenarioPanel } from '@/features/run-scenario'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import TabBar from '@/shared/ui/TabBar.vue'

import AccuracyPanel from './AccuracyPanel.vue'
import VersionDetail from './VersionDetail.vue'
import VersionsTable from './VersionsTable.vue'

const session = useSessionStore()
const screen = NAV_ITEMS.find((item) => item.key === 'forecast')
// Cosmetic: the API refuses running and publishing for any other role.
const canChange = computed(() => ['planner', 'admin'].includes(session.user?.role ?? ''))

const queues = useQueues()
const chosenQueue = ref<number | null>(null)
const queueId = computed({
  get: () => chosenQueue.value ?? queues.data.value?.[0]?.id ?? null,
  set: (value: number | null) => (chosenQueue.value = value),
})

const versions = useVersions(queueId)
const list = computed(() => versions.data.value ?? [])

// Open on the live forecast, otherwise the newest draft.
const chosenVersion = ref<string | null>(null)
const selected = computed(
  () =>
    list.value.find((v) => v.id === chosenVersion.value) ??
    list.value.find((v) => v.status === 'published') ??
    list.value[0] ??
    null,
)

// The open tab lives in the address (?tab=events), so a link or a reload lands on the same tab.
const TABS = [
  { key: 'versions', label: 'Versions' },
  { key: 'events', label: 'Events' },
  { key: 'scenarios', label: 'What if' },
  { key: 'accuracy', label: 'Accuracy' },
]
const route = useRoute()
const router = useRouter()
const tab = computed({
  get: () => {
    const asked = String(route.query.tab ?? '')
    return TABS.some((t) => t.key === asked) ? asked : 'versions'
  },
  set: (value: string) => {
    void router.replace({ query: { ...route.query, tab: value } })
  },
})

// Day, week or month, and the day it is about, live in the address too (?view=week&day=2026-05-27).
const VIEWS: ForecastView[] = ['day', 'week', 'month']
const view = computed<ForecastView>(() => {
  const asked = String(route.query.view ?? '')
  return VIEWS.find((v) => v === asked) ?? 'day'
})
const anchor = computed(() => {
  const asked = String(route.query.day ?? '')
  return /^\d{4}-\d{2}-\d{2}$/.test(asked) ? asked : ''
})
function changeView(next: ForecastView, day: string): void {
  void router.replace({
    query: { ...route.query, view: next === 'day' ? undefined : next, day: day || undefined },
  })
}

function show(id: string): void {
  chosenVersion.value = id
}
</script>

<template>
  <PageHeader eyebrow="Operate" :title="screen?.label ?? 'Forecast'" :subtitle="screen?.subtitle" />

  <div class="space-y-8">
    <p v-if="queues.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="queues.isError.value" tone="danger">
      Could not load the queues. {{ problemMessage(queues.error.value) }}
    </NoticeBox>
    <NoticeBox v-else-if="(queues.data.value ?? []).length === 0">
      There are no queues yet. They are created when call data is imported.
    </NoticeBox>

    <template v-else>
      <RunForecastForm
        v-if="canChange"
        v-model:queue-id="queueId"
        :queues="queues.data.value ?? []"
        @ran="show($event.id)"
      />

      <p v-if="versions.isPending.value" class="text-sm text-ink-muted">Loading versions…</p>
      <NoticeBox v-else-if="versions.isError.value" tone="danger">
        Could not load the forecasts. {{ problemMessage(versions.error.value) }}
      </NoticeBox>
      <NoticeBox v-else-if="list.length === 0">
        No forecast has been run for this queue yet.
      </NoticeBox>
      <VersionDetail
        v-else-if="selected"
        :key="selected.id"
        :version="selected"
        :view="view"
        :anchor="anchor"
        @change="changeView"
      />

      <TabBar v-model="tab" :tabs="TABS" label="Forecast sections" id-prefix="forecast" />

      <div
        v-if="tab === 'versions'"
        id="forecast-panel-versions"
        role="tabpanel"
        aria-labelledby="forecast-tab-versions"
      >
        <VersionsTable
          v-if="list.length > 0"
          :versions="list"
          :selected-id="selected?.id ?? null"
          :can-publish="canChange"
          @select="show"
        />
        <NoticeBox v-else-if="!versions.isPending.value && !versions.isError.value">
          Versions appear here once a forecast has been run.
        </NoticeBox>
      </div>

      <div
        v-else-if="tab === 'events'"
        id="forecast-panel-events"
        role="tabpanel"
        aria-labelledby="forecast-tab-events"
      >
        <EventsPanel :queue-id="queueId" :can-change="canChange" />
      </div>

      <div
        v-else-if="tab === 'scenarios'"
        id="forecast-panel-scenarios"
        role="tabpanel"
        aria-labelledby="forecast-tab-scenarios"
      >
        <ScenarioPanel v-if="selected" :key="`scenario-${selected.id}`" :version="selected" />
        <NoticeBox v-else>Run a forecast first: a what-if asks about one forecast.</NoticeBox>
      </div>

      <div
        v-else
        id="forecast-panel-accuracy"
        role="tabpanel"
        aria-labelledby="forecast-tab-accuracy"
      >
        <AccuracyPanel v-if="queueId !== null" :queue-id="queueId" />
      </div>
    </template>
  </div>
</template>
