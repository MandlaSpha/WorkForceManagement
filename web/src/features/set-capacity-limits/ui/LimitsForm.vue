<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { useCapacity } from '@/entities/workforce/capacity'
import { problemMessage } from '@/shared/api'
import { todayInJohannesburg, weekStartOf } from '@/shared/lib/week'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SettingsCard from '@/shared/ui/SettingsCard.vue'
import SettingsFooter from '@/shared/ui/SettingsFooter.vue'
import SettingsRow from '@/shared/ui/SettingsRow.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useSaveLimits } from '../model/useSaveLimits'

// The limits ride along with every capacity view; one week is enough to read them.
const view = useCapacity(weekStartOf(todayInJohannesburg()), 1)
const save = useSaveLimits()

const permanent = ref('100')
const seasonal = ref('250')
const saved = computed(() => view.data.value?.limits)
const dirty = computed(
  () =>
    saved.value !== undefined &&
    (permanent.value !== String(saved.value.permanentLimit) ||
      seasonal.value !== String(saved.value.seasonalLimit)),
)

function reset(): void {
  const limits = view.data.value?.limits
  if (!limits) return
  permanent.value = String(limits.permanentLimit)
  seasonal.value = String(limits.seasonalLimit)
}
watch(() => view.data.value?.limits, reset, { immediate: true })

function discard(): void {
  reset()
  save.reset()
}

function submit(): void {
  save.mutate({
    permanentLimit: Number(permanent.value),
    seasonalLimit: Number(seasonal.value),
  })
}
</script>

<template>
  <div v-if="view.isPending.value" class="space-y-3" aria-busy="true" aria-label="Loading">
    <div class="skeleton h-14" />
    <div class="skeleton h-14" />
  </div>
  <NoticeBox v-else-if="view.isError.value && !view.data.value" tone="danger">
    Could not load the workforce limits. {{ problemMessage(view.error.value) }}
  </NoticeBox>
  <form v-else aria-label="Workforce limits" @submit.prevent="submit">
    <SettingsCard
      title="Permanent and seasonal pools"
      description="Capacity is planned against these two pools: permanent staff first, then seasonal agents. The tender allows up to 350 agents, 100 permanent and 250 seasonal."
    >
      <template #status>
        <span
          v-if="view.data.value"
          class="rounded-full px-2.5 py-0.5 text-xs font-semibold"
          :class="
            view.data.value.limits.confirmed
              ? 'bg-brand-soft text-brand-ink'
              : 'bg-warn-soft text-warn'
          "
          data-testid="limits-state"
        >
          {{ view.data.value.limits.confirmed ? 'Confirmed' : 'Tender figures, not confirmed' }}
        </span>
      </template>
      <SettingsRow label="Permanent staff" helper="People on permanent contracts.">
        <TextField
          v-model="permanent"
          type="number"
          label="Permanent staff"
          hide-label
          :min="0"
          :max="5000"
        />
      </SettingsRow>
      <SettingsRow label="Seasonal agents" helper="The most seasonal agents that may be hired.">
        <TextField
          v-model="seasonal"
          type="number"
          label="Seasonal agents (at most)"
          hide-label
          :min="0"
          :max="5000"
        />
      </SettingsRow>
      <template #footer>
        <SettingsFooter
          :dirty="dirty"
          :clean-text="
            view.data.value?.limits.confirmed ? 'All changes saved' : 'Not yet confirmed'
          "
          :submit-label="view.data.value?.limits.confirmed ? 'Save limits' : 'Confirm limits'"
          :loading="save.isPending.value"
          @discard="discard"
        />
        <NoticeBox v-if="save.isError.value" tone="danger" class="mt-3" data-testid="limits-error">
          <p class="font-medium">The limits were not saved.</p>
          <p>{{ problemMessage(save.error.value) }}</p>
        </NoticeBox>
      </template>
    </SettingsCard>
  </form>
</template>
