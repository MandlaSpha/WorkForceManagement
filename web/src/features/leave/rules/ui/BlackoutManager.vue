<script setup lang="ts">
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { ref } from 'vue'

import { addBlackout, leaveKeys, removeBlackout, useBlackouts } from '@/entities/leave'
import { problemMessage } from '@/shared/api'
import { refreshQueries } from '@/shared/lib/refresh'
import { rangeLabel } from '@/entities/leave'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import TextField from '@/shared/ui/TextField.vue'

const blackouts = useBlackouts()
const queryClient = useQueryClient()
const name = ref('')
const from = ref('')
const to = ref('')

const add = useMutation({
  mutationFn: () =>
    addBlackout({ name: name.value.trim(), dateFrom: from.value, dateTo: to.value }),
  onSuccess: async () => {
    name.value = ''
    await refreshQueries(queryClient, leaveKeys.all)
  },
})
const remove = useMutation({
  mutationFn: (id: number) => removeBlackout(id),
  onSuccess: () => refreshQueries(queryClient, leaveKeys.all),
})
</script>

<template>
  <div class="space-y-3">
    <form class="space-y-3" aria-label="Add a blackout period" @submit.prevent="add.mutate()">
      <div class="grid gap-3 sm:grid-cols-3">
        <TextField v-model="name" label="Name (for example Year-end close)" />
        <TextField v-model="from" type="date" label="First day" />
        <TextField v-model="to" type="date" label="Last day" />
      </div>
      <AppButton
        type="submit"
        :loading="add.isPending.value"
        :disabled="name.trim() === '' || from === '' || to === ''"
      >
        Add blackout period
      </AppButton>
      <NoticeBox v-if="add.isError.value" tone="danger" data-testid="blackout-error">
        <p class="font-medium">The blackout period was not added.</p>
        <p>{{ problemMessage(add.error.value) }}</p>
      </NoticeBox>
    </form>

    <NoticeBox v-if="(blackouts.data.value ?? []).length === 0" data-testid="no-blackouts">
      No blackout periods are set.
    </NoticeBox>
    <ul v-else class="space-y-2" aria-label="Blackout periods">
      <li
        v-for="b in blackouts.data.value"
        :key="b.id"
        class="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface px-4 py-2"
      >
        <span class="text-sm text-ink">
          <span class="font-medium">{{ b.name }}</span>
          <span class="text-ink-muted"> · {{ rangeLabel(b.dateFrom, b.dateTo) }}</span>
        </span>
        <button
          type="button"
          class="text-xs font-medium text-danger underline disabled:opacity-60"
          :aria-label="`Remove ${b.name}`"
          :disabled="remove.isPending.value"
          @click="remove.mutate(b.id)"
        >
          Remove
        </button>
      </li>
    </ul>
  </div>
</template>
