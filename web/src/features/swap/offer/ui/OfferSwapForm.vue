<script setup lang="ts">
import { computed, ref } from 'vue'

import { describe, optionLabel, useMyShifts } from '@/entities/swap'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'

import { useOfferSwap } from '../model/useOfferSwap'

const mine = useMyShifts()
const give = ref('')
const myOptions = computed(() =>
  (mine.data.value ?? []).map((s) => ({ value: String(s.assignmentId), label: optionLabel(s) })),
)
const giveId = computed(() => Number(give.value || myOptions.value[0]?.value || 0) || null)

const post = useOfferSwap()

function submit(): void {
  if (giveId.value === null) return
  post.mutate({ giveAssignmentId: giveId.value })
}
</script>

<template>
  <NoticeBox v-if="mine.isSuccess.value && myOptions.length === 0" data-testid="no-shifts">
    You have no coming shifts that can be swapped: nothing in the next four weeks, or they are
    already in a swap.
  </NoticeBox>
  <form v-else class="space-y-3" aria-label="Post a shift swap" @submit.prevent="submit">
    <div class="max-w-md">
      <SelectField v-model="give" label="The shift you want to swap away" :options="myOptions" />
    </div>
    <AppButton type="submit" :loading="post.isPending.value" :disabled="giveId === null">
      Post swap request
    </AppButton>
    <NoticeBox v-if="post.isError.value" tone="danger" data-testid="offer-error">
      <p class="font-medium">The request was not posted.</p>
      <p>{{ problemMessage(post.error.value) }}</p>
    </NoticeBox>
    <NoticeBox v-else-if="post.data.value" data-testid="offer-result">
      Posted: {{ describe(post.data.value) }}. Colleagues on the same queue whose shifts fit the
      rules can take it; they will not see your name until someone does.
    </NoticeBox>
  </form>
</template>
