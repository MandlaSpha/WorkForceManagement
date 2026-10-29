<script setup lang="ts">
import { computed, ref } from 'vue'

import type { QueueInfo } from '@/entities/call-data'
import { problemMessage } from '@/shared/api'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SettingsCard from '@/shared/ui/SettingsCard.vue'
import SettingsFooter from '@/shared/ui/SettingsFooter.vue'
import SettingsRow from '@/shared/ui/SettingsRow.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useSaveQueueSettings } from '../model/useSaveQueueSettings'

const props = defineProps<{ queue: QueueInfo }>()

const target = ref(String(props.queue.slTargetPct))
const threshold = ref(String(props.queue.slThresholdS))
const occupancy = ref(String(props.queue.occupancyCeilingPct))
const shrinkage = ref(String(props.queue.shrinkagePct))
const outbound = ref(props.queue.outboundOnly)

const save = useSaveQueueSettings(props.queue.id)

const dirty = computed(
  () =>
    target.value !== String(props.queue.slTargetPct) ||
    threshold.value !== String(props.queue.slThresholdS) ||
    occupancy.value !== String(props.queue.occupancyCeilingPct) ||
    shrinkage.value !== String(props.queue.shrinkagePct) ||
    outbound.value !== props.queue.outboundOnly,
)

function discard(): void {
  target.value = String(props.queue.slTargetPct)
  threshold.value = String(props.queue.slThresholdS)
  occupancy.value = String(props.queue.occupancyCeilingPct)
  shrinkage.value = String(props.queue.shrinkagePct)
  outbound.value = props.queue.outboundOnly
  save.reset()
}

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
  <form :aria-label="`Staffing settings for ${queue.name}`" @submit.prevent="submit">
    <SettingsCard :title="queue.name">
      <template #status>
        <span
          class="rounded-full px-2.5 py-0.5 text-xs font-semibold"
          :class="
            queue.settingsConfirmed ? 'bg-brand-soft text-brand-ink' : 'bg-warn-soft text-warn'
          "
          :data-testid="`settings-state-${queue.id}`"
        >
          {{ queue.settingsConfirmed ? 'Confirmed' : 'Defaults, not confirmed' }}
        </span>
      </template>

      <SettingsRow
        label="Service level target"
        helper="The share of calls that should be answered in time."
      >
        <TextField
          v-model="target"
          type="number"
          label="Service level target (%)"
          hide-label
          :min="1"
          :max="100"
        />
      </SettingsRow>
      <SettingsRow label="Answer within" helper="The wait, in seconds, that counts as in time.">
        <TextField
          v-model="threshold"
          type="number"
          label="Answer within (seconds)"
          hide-label
          :min="1"
          :max="600"
        />
      </SettingsRow>
      <SettingsRow
        label="Occupancy ceiling"
        helper="The most of an agent's time that may be spent on calls."
      >
        <TextField
          v-model="occupancy"
          type="number"
          label="Occupancy ceiling (%)"
          hide-label
          :min="1"
          :max="100"
        />
      </SettingsRow>
      <SettingsRow label="Shrinkage" helper="Paid time lost to leave, breaks and training.">
        <TextField
          v-model="shrinkage"
          type="number"
          label="Shrinkage (%)"
          hide-label
          :min="0"
          :max="99"
        />
      </SettingsRow>
      <SettingsRow
        label="Outbound calls only"
        helper="No forecast is made for this queue: it has no inbound demand to staff."
      >
        <input
          v-model="outbound"
          type="checkbox"
          class="size-5 accent-[var(--brand)]"
          aria-label="Outbound calls only"
        />
      </SettingsRow>

      <template #footer>
        <SettingsFooter
          :dirty="dirty"
          :clean-text="
            queue.settingsConfirmed ? 'All changes saved' : 'Defaults, not yet confirmed'
          "
          :submit-label="queue.settingsConfirmed ? 'Save settings' : 'Confirm settings'"
          :loading="save.isPending.value"
          @discard="discard"
        />
        <NoticeBox
          v-if="save.isError.value"
          tone="danger"
          class="mt-3"
          data-testid="settings-error"
        >
          <p class="font-medium">The settings were not saved.</p>
          <p>{{ problemMessage(save.error.value) }}</p>
        </NoticeBox>
      </template>
    </SettingsCard>
  </form>
</template>
