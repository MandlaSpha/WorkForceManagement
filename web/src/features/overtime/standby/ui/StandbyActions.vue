<script setup lang="ts">
import { ref } from 'vue'

import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'

import { useCancelStandby, useRecordCallOut } from '../model/useStandbyWrites'

const props = defineProps<{
  standbyId: number
  who: string
  booked: boolean
  canCancel: boolean // the viewer may cancel and the day is not over
  canRecord: boolean // the viewer decides overtime and the day has come
  own: boolean
}>()
const cancel = useCancelStandby()
const callOut = useRecordCallOut()
const minutes = ref('')

function submit(): void {
  callOut.mutate(
    { standbyId: props.standbyId, minutes: Number(minutes.value) },
    { onSuccess: () => (minutes.value = '') },
  )
}
</script>

<template>
  <div v-if="booked" class="flex flex-col items-end gap-1">
    <form
      v-if="canRecord && !own"
      class="flex items-end gap-2"
      :aria-label="`Record a call-out for ${who}`"
      @submit.prevent="submit"
    >
      <label class="text-xs text-ink-muted">
        Call-out minutes
        <input
          v-model="minutes"
          type="number"
          min="0"
          max="720"
          required
          class="block min-h-9 w-24 rounded-lg border border-line bg-surface px-2 text-sm text-ink"
        />
      </label>
      <AppButton type="submit" variant="secondary" :loading="callOut.isPending.value">
        Record
      </AppButton>
    </form>
    <p v-else-if="canRecord && own" class="text-xs text-ink-muted">
      Somebody else records your call-out.
    </p>
    <button
      v-if="canCancel"
      type="button"
      class="text-xs font-medium text-danger underline disabled:opacity-60"
      :aria-label="`Cancel standby for ${who}`"
      :disabled="cancel.isPending.value"
      @click="cancel.mutate(standbyId)"
    >
      Cancel
    </button>
    <span
      v-if="callOut.isError.value || cancel.isError.value"
      class="text-xs text-danger"
      role="alert"
    >
      {{ problemMessage(callOut.error.value ?? cancel.error.value) }}
    </span>
  </div>
</template>
