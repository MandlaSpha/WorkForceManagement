<script setup lang="ts">
import { ref } from 'vue'

import { useQueues } from '@/entities/call-data'
import { QueueSettingsForm } from '@/features/confirm-queue-settings'
import { ShiftLibrary } from '@/features/manage-shifts'
import { LimitsForm } from '@/features/set-capacity-limits'
import { ComplianceRulesForm } from '@/features/set-compliance-rules'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import TabBar from '@/shared/ui/TabBar.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'configure')
const tab = ref('shifts')
const queues = useQueues()

const TABS = [
  { key: 'shifts', label: 'Shifts' },
  { key: 'queues', label: 'Queues' },
  { key: 'workforce', label: 'Workforce' },
  { key: 'rules', label: 'Rules' },
]
</script>

<template>
  <PageHeader eyebrow="Admin" :title="screen?.label ?? 'Configure'" :subtitle="screen?.subtitle">
    <template #actions>
      <TabBar
        v-model="tab"
        :tabs="TABS"
        label="Configuration"
        id-prefix="configure"
        variant="pill"
      />
    </template>
  </PageHeader>

  <div class="space-y-6">
    <div
      v-if="tab === 'shifts'"
      id="configure-panel-shifts"
      role="tabpanel"
      aria-labelledby="configure-tab-shifts"
    >
      <ShiftLibrary />
    </div>

    <div
      v-else-if="tab === 'workforce'"
      id="configure-panel-workforce"
      role="tabpanel"
      aria-labelledby="configure-tab-workforce"
    >
      <LimitsForm />
    </div>

    <div
      v-else-if="tab === 'rules'"
      id="configure-panel-rules"
      role="tabpanel"
      aria-labelledby="configure-tab-rules"
    >
      <ComplianceRulesForm />
    </div>

    <div
      v-else
      id="configure-panel-queues"
      role="tabpanel"
      aria-labelledby="configure-tab-queues"
      class="space-y-4"
    >
      <p class="max-w-2xl text-sm text-ink-muted">
        The staffing assumptions behind every requirement. Until an admin confirms them they are
        defaults, and every screen that rests on them says so.
      </p>
      <div v-if="queues.isPending.value" class="space-y-3" aria-busy="true" aria-label="Loading">
        <div class="skeleton h-14" />
        <div class="skeleton h-14" />
      </div>
      <NoticeBox v-else-if="queues.isError.value" tone="danger">
        Could not load the queues. {{ problemMessage(queues.error.value) }}
      </NoticeBox>
      <NoticeBox v-else-if="(queues.data.value ?? []).length === 0">
        There are no queues yet. They are created when call data is imported.
      </NoticeBox>
      <QueueSettingsForm
        v-for="q in queues.data.value"
        :key="`${q.id}-${q.settingsConfirmed}`"
        :queue="q"
      />
    </div>
  </div>
</template>
