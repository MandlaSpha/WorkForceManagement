<script setup lang="ts">
import { computed } from 'vue'

import type { Swap, SwapAnswer } from '@/entities/swap'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'

import { useAnswerSwap } from '../model/useAnswerSwap'

const props = defineProps<{ swap: Swap; decides: boolean }>()
const emit = defineEmits<{ answered: [what: SwapAnswer, swap: Swap] }>()
const answer = useAnswerSwap((what, swap) => emit('answered', what, swap))

// Cosmetic: the API enforces who may answer. These only decide which buttons to offer.
const approverTurn = computed(
  () =>
    props.swap.status === 'awaiting_approval' &&
    props.decides &&
    !props.swap.asker &&
    !props.swap.colleague,
)
const canWithdraw = computed(
  () =>
    props.swap.asker && (props.swap.status === 'open' || props.swap.status === 'awaiting_approval'),
)

function act(what: SwapAnswer): void {
  answer.mutate({ swapId: props.swap.id, what })
}
</script>

<template>
  <div class="flex flex-col items-end gap-1">
    <div v-if="approverTurn" class="flex gap-2">
      <AppButton
        :aria-label="`Approve the swap between ${swap.fromEmployee} and ${swap.toEmployee}`"
        :loading="answer.isPending.value"
        @click="act('approve')"
      >
        Approve
      </AppButton>
      <AppButton
        variant="secondary"
        :aria-label="`Reject the swap between ${swap.fromEmployee} and ${swap.toEmployee}`"
        :loading="answer.isPending.value"
        @click="act('reject')"
      >
        Reject
      </AppButton>
    </div>
    <button
      v-if="canWithdraw"
      type="button"
      class="text-xs font-medium text-danger underline disabled:opacity-60"
      aria-label="Withdraw this swap request"
      :disabled="answer.isPending.value"
      @click="act('cancel')"
    >
      Withdraw
    </button>
    <span v-if="answer.isError.value" class="text-xs text-danger" role="alert">
      {{ problemMessage(answer.error.value) }}
    </span>
  </div>
</template>
