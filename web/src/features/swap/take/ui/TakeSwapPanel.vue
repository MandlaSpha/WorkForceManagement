<script setup lang="ts">
import { computed, ref } from 'vue'

import { describe, optionLabel, useOffers } from '@/entities/swap'
import type { BoardEntry } from '@/entities/swap'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'

import { useTakeSwap } from '../model/useTakeSwap'

const props = defineProps<{ request: BoardEntry }>()
const emit = defineEmits<{ taken: [message: string] }>()

const offers = useOffers(
  computed(() => props.request.id),
  true,
)
const choice = ref('')
const options = computed(() =>
  (offers.data.value ?? []).map((s) => ({ value: String(s.assignmentId), label: optionLabel(s) })),
)
const chosen = computed(() => Number(choice.value || options.value[0]?.value || 0) || null)

const take = useTakeSwap((swap) => emit('taken', `Taken: ${describe(swap)}. A lead decides next.`))

function submit(): void {
  if (chosen.value === null) return
  take.mutate({ swapId: props.request.id, assignmentId: chosen.value })
}
</script>

<template>
  <form
    class="mt-3 space-y-2 rounded-lg bg-surface-muted p-3"
    :aria-label="`Take the ${request.shift} request`"
    @submit.prevent="submit"
  >
    <p v-if="offers.isPending.value" class="text-sm text-ink-muted">Checking your shifts…</p>
    <NoticeBox v-else-if="options.length === 0" data-testid="no-offers">
      None of your shifts would work for this one any more.
    </NoticeBox>
    <template v-else>
      <div class="max-w-md">
        <SelectField
          v-model="choice"
          label="Offer this shift of yours in return"
          :options="options"
        />
      </div>
      <AppButton type="submit" :loading="take.isPending.value">Take this swap</AppButton>
    </template>
    <span v-if="take.isError.value" class="block text-sm text-danger" role="alert">
      {{ problemMessage(take.error.value) }}
    </span>
  </form>
</template>
