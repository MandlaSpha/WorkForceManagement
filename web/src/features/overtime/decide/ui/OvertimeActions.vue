<script setup lang="ts">
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'

import { useDecideOvertime } from '../model/useDecideOvertime'

const props = defineProps<{
  requestId: number
  who: string
  canDecide: boolean
  canCancel: boolean
  own: boolean
}>()
const act = useDecideOvertime()

const send = (what: 'approve' | 'reject' | 'cancel') =>
  act.mutate({ requestId: props.requestId, what })
</script>

<template>
  <div class="flex flex-col items-end gap-1">
    <p v-if="canDecide && own" class="text-xs text-ink-muted">
      Somebody else decides your overtime.
    </p>
    <div v-else-if="canDecide" class="flex gap-2">
      <AppButton
        :aria-label="`Approve overtime for ${who}`"
        :loading="act.isPending.value"
        @click="send('approve')"
      >
        Approve
      </AppButton>
      <AppButton
        variant="secondary"
        :aria-label="`Reject overtime for ${who}`"
        :loading="act.isPending.value"
        @click="send('reject')"
      >
        Reject
      </AppButton>
    </div>
    <button
      v-if="canCancel"
      type="button"
      class="text-xs font-medium text-danger underline disabled:opacity-60"
      :aria-label="`Cancel overtime for ${who}`"
      :disabled="act.isPending.value"
      @click="send('cancel')"
    >
      Cancel
    </button>
    <span v-if="act.isError.value" class="max-w-64 text-right text-xs text-danger" role="alert">
      {{ problemMessage(act.error.value) }}
    </span>
  </div>
</template>
