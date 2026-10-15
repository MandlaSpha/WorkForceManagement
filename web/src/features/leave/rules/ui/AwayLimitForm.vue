<script setup lang="ts">
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { ref, watch } from 'vue'

import { leaveKeys, setAwayLimit, useAwayLimit } from '@/entities/leave'
import { problemMessage } from '@/shared/api'
import { refreshQueries } from '@/shared/lib/refresh'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

const limit = useAwayLimit()
const queryClient = useQueryClient()
// Blank means no limit. A number input gives back a number once something is typed, so the
// value is always read as text first.
const most = ref('')
// Fill the box from the saved value once, when it arrives. Doing it again would wipe what the admin
// has already started typing if the answer comes in late.
let filled = false
watch(
  () => limit.data.value,
  (saved) => {
    if (saved === undefined || filled) return
    filled = true
    most.value = saved.maxConcurrent === null ? '' : String(saved.maxConcurrent)
  },
  { immediate: true },
)

const save = useMutation({
  mutationFn: () => setAwayLimit(String(most.value).trim() === '' ? null : Number(most.value)),
  onSuccess: () => refreshQueries(queryClient, leaveKeys.all),
})
</script>

<template>
  <form
    class="flex flex-wrap items-center gap-2"
    aria-label="Most people away at once"
    @submit.prevent="save.mutate()"
  >
    <label for="away-limit" class="min-w-52 text-sm font-medium text-ink">
      Most people away at once
    </label>
    <input
      id="away-limit"
      v-model="most"
      type="number"
      min="1"
      max="1000"
      step="1"
      placeholder="no limit"
      class="w-24 rounded-md border border-line bg-surface px-2 py-1 text-right text-sm tabular-nums text-ink"
      aria-label="Most people away at once, blank for no limit"
    />
    <AppButton type="submit" variant="ghost" :loading="save.isPending.value">Save</AppButton>
    <NoticeBox v-if="save.isError.value" tone="danger" data-testid="limit-error">
      {{ problemMessage(save.error.value) }}
    </NoticeBox>
  </form>
</template>
