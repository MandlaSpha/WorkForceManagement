<script setup lang="ts">
import { computed, ref } from 'vue'

import type { ForecastVersion } from '@/entities/forecast'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useRetireForecast } from '../model/useRetireForecast'

const props = defineProps<{ version: ForecastVersion }>()

const retire = useRetireForecast()
const asking = ref(false)
const reason = ref('')

// A draft is deleted; the live forecast is withdrawn and kept as history.
const isDraft = computed(() => props.version.status === 'draft')
const verb = computed(() => (isDraft.value ? 'Discard' : 'Archive'))
const name = computed(() => props.version.label || 'forecast')
const mutation = computed(() => (isDraft.value ? retire.discard : retire.archive))
const consequence = computed(() =>
  isDraft.value
    ? 'This deletes the draft and its half-hours. It cannot be undone.'
    : `This withdraws the live forecast. ${props.version.queue} will have no published forecast: ` +
      'the roster, capacity and dashboard show none until another is published. The forecast ' +
      'stays here as history.',
)
const ready = computed(() => reason.value.trim().length >= 3)

function confirm(): void {
  mutation.value.mutate(
    { versionId: props.version.id, reason: reason.value.trim() },
    {
      onSuccess: () => {
        asking.value = false
        reason.value = ''
      },
    },
  )
}

function cancel(): void {
  asking.value = false
  reason.value = ''
  mutation.value.reset()
}
</script>

<template>
  <div class="inline-flex flex-col items-end gap-1">
    <AppButton
      v-if="!asking"
      variant="ghost"
      :aria-label="`${verb} ${name} for ${version.queue}`"
      @click="asking = true"
    >
      {{ verb }}
    </AppButton>

    <form
      v-else
      class="w-64 space-y-2 rounded-lg border border-danger bg-surface p-3 text-left"
      :aria-label="`${verb} ${name}`"
      data-testid="retire-form"
      @submit.prevent="confirm"
    >
      <p class="text-xs text-ink" data-testid="retire-consequence">{{ consequence }}</p>
      <TextField v-model="reason" label="Reason (kept in the audit trail)" autocomplete="off" />
      <div class="flex justify-end gap-2">
        <AppButton variant="ghost" @click="cancel">Keep it</AppButton>
        <AppButton
          type="submit"
          :loading="mutation.isPending.value"
          :disabled="!ready"
          :aria-label="`Confirm: ${verb.toLowerCase()} ${name}`"
        >
          {{ verb }}
        </AppButton>
      </div>
      <p v-if="mutation.isError.value" class="text-xs text-danger" role="alert">
        {{ problemMessage(mutation.error.value) }}
      </p>
    </form>
  </div>
</template>
