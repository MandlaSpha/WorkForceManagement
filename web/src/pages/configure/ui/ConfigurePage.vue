<script setup lang="ts">
import { ref } from 'vue'

import { useQueues } from '@/entities/call-data'
import { QueueSettingsForm } from '@/features/confirm-queue-settings'
import { ShiftLibrary } from '@/features/manage-shifts'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'configure')
const tab = ref<'shifts' | 'queues'>('shifts')
const queues = useQueues()

const TABS = [
  { key: 'shifts', label: 'Shifts' },
  { key: 'queues', label: 'Queues' },
] as const
</script>

<template>
  <PageHeader eyebrow="Admin" :title="screen?.label ?? 'Configure'" :subtitle="screen?.subtitle" />

  <div class="space-y-6">
    <div class="flex gap-1 border-b border-line" role="tablist" aria-label="Configuration">
      <button
        v-for="t in TABS"
        :id="`tab-${t.key}`"
        :key="t.key"
        type="button"
        role="tab"
        class="-mb-px border-b-2 px-4 py-2 text-sm font-medium"
        :class="
          tab === t.key
            ? 'border-brand text-brand-ink'
            : 'border-transparent text-ink-muted hover:text-ink'
        "
        :aria-selected="tab === t.key"
        :aria-controls="`panel-${t.key}`"
        @click="tab = t.key"
      >
        {{ t.label }}
      </button>
    </div>

    <div v-if="tab === 'shifts'" id="panel-shifts" role="tabpanel" aria-labelledby="tab-shifts">
      <ShiftLibrary />
    </div>

    <div v-else id="panel-queues" role="tabpanel" aria-labelledby="tab-queues" class="space-y-4">
      <p class="text-sm text-ink-muted">
        The staffing assumptions behind every requirement. Until an admin confirms them they are
        defaults, and every screen that rests on them says so.
      </p>
      <p v-if="queues.isPending.value" class="text-sm text-ink-muted">Loading…</p>
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
