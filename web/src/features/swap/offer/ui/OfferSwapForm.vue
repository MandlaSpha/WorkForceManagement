<script setup lang="ts">
import { computed, ref } from 'vue'

import { describe, optionLabel, useMyShifts, useOptions } from '@/entities/swap'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'

import { useOfferSwap } from '../model/useOfferSwap'

const mine = useMyShifts()
const give = ref('')
const take = ref('')
const myOptions = computed(() =>
  (mine.data.value ?? []).map((s) => ({ value: String(s.assignmentId), label: optionLabel(s) })),
)
const giveId = computed(() => Number(give.value || myOptions.value[0]?.value || 0) || null)

const candidates = useOptions(giveId)
const takeOptions = computed(() =>
  (candidates.data.value ?? []).map((s) => ({
    value: String(s.assignmentId),
    label: `${s.employee}: ${optionLabel(s)}`,
  })),
)
const takeId = computed(() => Number(take.value || takeOptions.value[0]?.value || 0) || null)

const offer = useOfferSwap()

function pickMine(value: string): void {
  give.value = value
  take.value = ''
}

function submit(): void {
  if (giveId.value === null || takeId.value === null) return
  offer.mutate({ giveAssignmentId: giveId.value, takeAssignmentId: takeId.value })
}
</script>

<template>
  <NoticeBox v-if="mine.isSuccess.value && myOptions.length === 0" data-testid="no-shifts">
    You have no coming shifts that can be swapped: nothing in the next four weeks, or they are
    already in a swap.
  </NoticeBox>
  <form v-else class="space-y-3" aria-label="Offer a shift swap" @submit.prevent="submit">
    <div class="grid gap-3 sm:grid-cols-2">
      <SelectField
        :model-value="String(giveId ?? '')"
        label="Your shift"
        :options="myOptions"
        @update:model-value="pickMine"
      />
      <SelectField
        v-if="takeOptions.length > 0"
        :model-value="String(takeId ?? '')"
        label="Swap it for"
        :options="takeOptions"
        @update:model-value="take = $event"
      />
    </div>
    <NoticeBox
      v-if="candidates.isSuccess.value && takeOptions.length === 0"
      data-testid="no-options"
    >
      No colleague's shift on this queue fits the rules for that swap. Another of your shifts may.
    </NoticeBox>
    <AppButton type="submit" :loading="offer.isPending.value" :disabled="takeId === null">
      Offer swap
    </AppButton>
    <NoticeBox v-if="offer.isError.value" tone="danger" data-testid="offer-error">
      <p class="font-medium">The swap was not offered.</p>
      <p>{{ problemMessage(offer.error.value) }}</p>
    </NoticeBox>
    <NoticeBox v-else-if="offer.data.value" data-testid="offer-result">
      Offered: {{ describe(offer.data.value) }}. It is waiting for
      {{ offer.data.value.toEmployee }} to accept.
    </NoticeBox>
  </form>
</template>
