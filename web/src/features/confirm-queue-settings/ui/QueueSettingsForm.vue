<script setup lang="ts">
import { ref } from 'vue'

import type { QueueInfo } from '@/entities/call-data'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useSaveQueueSettings } from '../model/useSaveQueueSettings'

const props = defineProps<{ queue: QueueInfo }>()

const target = ref(String(props.queue.slTargetPct))
const threshold = ref(String(props.queue.slThresholdS))
const occupancy = ref(String(props.queue.occupancyCeilingPct))
const shrinkage = ref(String(props.queue.shrinkagePct))
const outbound = ref(props.queue.outboundOnly)

const save = useSaveQueueSettings(props.queue.id)

function submit(): void {
  save.mutate({
    slTargetPct: Number(target.value),
    slThresholdS: Number(threshold.value),
    occupancyCeilingPct: Number(occupancy.value),
    shrinkagePct: Number(shrinkage.value),
    outboundOnly: outbound.value,
  })
}
</script>

<template>
  <form
    class="space-y-3 rounded-xl border border-line bg-surface p-4"
    :aria-label="`Staffing settings for ${queue.name}`"
    @submit.prevent="submit"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3 class="text-sm font-semibold text-ink">{{ queue.name }}</h3>
      <span
        class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
        :class="queue.settingsConfirmed ? 'bg-brand-soft text-brand-ink' : 'bg-warn-soft text-warn'"
        :data-testid="`settings-state-${queue.id}`"
      >
        {{ queue.settingsConfirmed ? 'Confirmed' : 'Defaults, not confirmed' }}
      </span>
    </div>
    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <TextField
        v-model="target"
        type="number"
        label="Service level target (%)"
        :min="1"
        :max="100"
      />
      <TextField
        v-model="threshold"
        type="number"
        label="Answer within (seconds)"
        :min="1"
        :max="600"
      />
      <TextField
        v-model="occupancy"
        type="number"
        label="Occupancy ceiling (%)"
        :min="1"
        :max="100"
      />
      <TextField v-model="shrinkage" type="number" label="Shrinkage (%)" :min="0" :max="99" />
    </div>
    <label class="flex items-start gap-2 text-sm text-ink">
      <input v-model="outbound" type="checkbox" class="mt-1" />
      <span>
        Outbound calls only
        <span class="block text-xs text-ink-muted">
          No forecast is made for this queue: it has no inbound demand to staff.
        </span>
      </span>
    </label>
    <AppButton type="submit" :loading="save.isPending.value">
      {{ queue.settingsConfirmed ? 'Save settings' : 'Confirm settings' }}
    </AppButton>
    <NoticeBox v-if="save.isError.value" tone="danger" data-testid="settings-error">
      <p class="font-medium">The settings were not saved.</p>
      <p>{{ problemMessage(save.error.value) }}</p>
    </NoticeBox>
  </form>
</template>
