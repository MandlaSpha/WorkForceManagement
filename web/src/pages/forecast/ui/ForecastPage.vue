<script setup lang="ts">
import { computed, ref } from 'vue'

import { useQueues } from '@/entities/call-data'
import { useVersions } from '@/entities/forecast'
import { useSessionStore } from '@/entities/session'
import { EventsPanel } from '@/features/manage-events'
import { RunForecastForm } from '@/features/run-forecast'
import { ScenarioPanel } from '@/features/run-scenario'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

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
      <NoticeBox v-else>
        You can read forecasts here. Planners and admins run and publish them.
      </NoticeBox>

      <p v-if="versions.isPending.value" class="text-sm text-ink-muted">Loading versions…</p>
      <NoticeBox v-else-if="versions.isError.value" tone="danger">
        Could not load the forecasts. {{ problemMessage(versions.error.value) }}
      </NoticeBox>
      <NoticeBox v-else-if="list.length === 0">
        No forecast has been run for this queue yet.
      </NoticeBox>
      <template v-else>
        <VersionsTable
          :versions="list"
          :selected-id="selected?.id ?? null"
          :can-publish="canChange"
          @select="show"
        />
        <VersionDetail v-if="selected" :key="selected.id" :version="selected" />
        <ScenarioPanel v-if="selected" :key="`scenario-${selected.id}`" :version="selected" />
      </template>

      <EventsPanel :queue-id="queueId" :can-change="canChange" />

      <AccuracyPanel v-if="queueId !== null" :queue-id="queueId" />
    </template>
  </div>
</template>
