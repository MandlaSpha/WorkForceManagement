<script setup lang="ts">
import { ref } from 'vue'

import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'

import { useRecordWorked } from '../model/useRecordWorked'

const props = defineProps<{
  requestId: number
  who: string
  workedMinutes: number | null
  extraMinutes: number
  canRecord: boolean // approved, its day has come, and the viewer decides overtime
  own: boolean
}>()
const record = useRecordWorked()
const minutes = ref('')

const label = (m: number) => `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`

function submit(): void {
  record.mutate(
    { requestId: props.requestId, minutes: Number(minutes.value) },
    { onSuccess: () => (minutes.value = '') },
  )
}
</script>

<template>
  <div class="space-y-1 text-sm">
    <p v-if="workedMinutes !== null" data-testid="worked">
      {{ label(workedMinutes) }} worked
      <span v-if="extraMinutes > 0" class="block text-xs text-warn" data-testid="extra">
        {{ label(extraMinutes) }} beyond what was approved, not paid
      </span>
    </p>
    <p v-else-if="canRecord && own" class="text-xs text-ink-muted">
      Somebody else records your overtime.
    </p>
    <p v-else-if="!canRecord" class="text-xs text-ink-muted">—</p>
    <form
      v-if="canRecord && !own"
      class="flex items-end gap-2"
      :aria-label="`Record worked time for ${who}`"
      @submit.prevent="submit"
    >
      <label class="text-xs text-ink-muted">
        Minutes worked
        <input
          v-model="minutes"
          type="number"
          min="0"
          max="720"
          required
          class="block min-h-9 w-24 rounded-lg border border-line bg-surface px-2 text-sm text-ink"
        />
      </label>
      <AppButton type="submit" variant="secondary" :loading="record.isPending.value">
        {{ workedMinutes === null ? 'Record' : 'Correct' }}
      </AppButton>
    </form>
    <span v-if="record.isError.value" class="block text-xs text-danger" role="alert">
      {{ problemMessage(record.error.value) }}
    </span>
  </div>
</template>
