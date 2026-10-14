<script setup lang="ts">
import type { Decision } from '@/entities/leave'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'

import { useDecideLeave } from '../model/useDecideLeave'

const props = defineProps<{ requestId: number; who: string; own: boolean }>()
// The row leaves the waiting list the moment it is decided, so the outcome is reported upward.
const emit = defineEmits<{ decided: [decision: Decision] }>()
const decide = useDecideLeave((d) => emit('decided', d))

function act(what: 'approve' | 'reject'): void {
  decide.mutate({ requestId: props.requestId, what })
}
</script>

<template>
  <div class="flex flex-col items-end gap-1">
    <p v-if="own" class="text-xs text-ink-muted">Somebody else decides your leave.</p>
    <div v-else class="flex gap-2">
      <AppButton
        :aria-label="`Approve leave for ${who}`"
        :loading="decide.isPending.value"
        @click="act('approve')"
      >
        Approve
      </AppButton>
      <AppButton
        variant="secondary"
        :aria-label="`Reject leave for ${who}`"
        :loading="decide.isPending.value"
        @click="act('reject')"
      >
        Reject
      </AppButton>
    </div>
    <span v-if="decide.isError.value" class="text-xs text-danger" role="alert">
      {{ problemMessage(decide.error.value) }}
    </span>
  </div>
</template>
