<script setup lang="ts">
import { ref, watch } from 'vue'

import { useCapacity } from '@/entities/workforce/capacity'
import { problemMessage } from '@/shared/api'
import { todayInJohannesburg, weekStartOf } from '@/shared/lib/week'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useSaveLimits } from '../model/useSaveLimits'

// The limits ride along with every capacity view; one week is enough to read them.
const view = useCapacity(weekStartOf(todayInJohannesburg()), 1)
const save = useSaveLimits()

const permanent = ref('100')
const seasonal = ref('250')
watch(
  () => view.data.value?.limits,
  (limits) => {
    if (!limits) return
    permanent.value = String(limits.permanentLimit)
    seasonal.value = String(limits.seasonalLimit)
  },
  { immediate: true },
)

function submit(): void {
  save.mutate({
    permanentLimit: Number(permanent.value),
    seasonalLimit: Number(seasonal.value),
  })
}
</script>

<template>
  <form
    class="space-y-3 rounded-xl border border-line bg-surface p-4"
    aria-label="Workforce limits"
    @submit.prevent="submit"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3 class="text-sm font-semibold text-ink">Permanent and seasonal pools</h3>
      <span
        v-if="view.data.value"
        class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
        :class="
          view.data.value.limits.confirmed
            ? 'bg-brand-soft text-brand-ink'
            : 'bg-warn-soft text-warn'
        "
        data-testid="limits-state"
      >
        {{ view.data.value.limits.confirmed ? 'Confirmed' : 'Tender figures, not confirmed' }}
      </span>
    </div>
    <p class="text-sm text-ink-muted">
      Capacity is planned against these two pools: permanent staff first, then seasonal agents. The
      tender allows up to 350 agents, 100 permanent and 250 seasonal.
    </p>
    <div class="grid gap-3 sm:grid-cols-2">
      <TextField v-model="permanent" type="number" label="Permanent staff" :min="0" :max="5000" />
      <TextField
        v-model="seasonal"
        type="number"
        label="Seasonal agents (at most)"
        :min="0"
        :max="5000"
      />
    </div>
    <AppButton type="submit" :loading="save.isPending.value" :disabled="view.isPending.value">
      {{ view.data.value?.limits.confirmed ? 'Save limits' : 'Confirm limits' }}
    </AppButton>
    <NoticeBox v-if="save.isError.value" tone="danger" data-testid="limits-error">
      <p class="font-medium">The limits were not saved.</p>
      <p>{{ problemMessage(save.error.value) }}</p>
    </NoticeBox>
  </form>
</template>
