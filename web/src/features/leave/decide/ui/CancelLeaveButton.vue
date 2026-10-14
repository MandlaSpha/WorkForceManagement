<script setup lang="ts">
import type { Decision } from '@/entities/leave'
import { problemMessage } from '@/shared/api'

import { useDecideLeave } from '../model/useDecideLeave'

const props = defineProps<{ requestId: number; label: string }>()
const emit = defineEmits<{ cancelled: [decision: Decision] }>()
const cancel = useDecideLeave((d) => emit('cancelled', d))

function submit(): void {
  cancel.mutate({ requestId: props.requestId, what: 'cancel' })
}
</script>

<template>
  <span class="inline-flex flex-col items-end">
    <button
      type="button"
      class="text-xs font-medium text-danger underline disabled:opacity-60"
      :aria-label="`Cancel leave ${label}`"
      :disabled="cancel.isPending.value"
      @click="submit"
    >
      Cancel
    </button>
    <span v-if="cancel.isError.value" class="text-xs text-danger" role="alert">
      {{ problemMessage(cancel.error.value) }}
    </span>
  </span>
</template>
