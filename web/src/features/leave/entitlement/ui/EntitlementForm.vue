<script setup lang="ts">
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { ref } from 'vue'

import { leaveKeys, setEntitlement, type LeaveType } from '@/entities/leave'
import { problemMessage } from '@/shared/api'
import { refreshQueries } from '@/shared/lib/refresh'
import AppButton from '@/shared/ui/AppButton.vue'

const props = defineProps<{ type: LeaveType }>()
// Blank means no limit. A number input gives back a number once something is typed, so the
// value is always read as text first.
const days = ref(props.type.daysPerYear === null ? '' : String(props.type.daysPerYear))
const queryClient = useQueryClient()
const save = useMutation({
  mutationFn: () =>
    setEntitlement(props.type.id, String(days.value).trim() === '' ? null : Number(days.value)),
  onSuccess: () => refreshQueries(queryClient, leaveKeys.all),
})
</script>

<template>
  <form
    class="flex flex-wrap items-center gap-2"
    :aria-label="`Days a year for ${type.name}`"
    @submit.prevent="save.mutate()"
  >
    <label :for="`days-${type.id}`" class="min-w-52 text-sm font-medium text-ink">{{
      type.name
    }}</label>
    <input
      :id="`days-${type.id}`"
      v-model="days"
      type="number"
      min="0"
      max="366"
      step="0.5"
      placeholder="no limit"
      class="w-24 rounded-md border border-line bg-surface px-2 py-1 text-right text-sm tabular-nums text-ink"
      :aria-label="`Days a year of ${type.name}, blank for no limit`"
    />
    <AppButton type="submit" variant="ghost" :loading="save.isPending.value">Save</AppButton>
    <span
      class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
      :class="type.confirmed ? 'bg-brand-soft text-brand-ink' : 'bg-warn-soft text-warn'"
      :data-testid="`entitlement-state-${type.id}`"
    >
      {{ type.confirmed ? 'Confirmed' : 'BCEA default, not confirmed' }}
    </span>
    <span
      v-if="save.isError.value"
      class="text-xs text-danger"
      role="alert"
      :data-testid="`entitlement-error-${type.id}`"
    >
      {{ problemMessage(save.error.value) }}
    </span>
  </form>
</template>
