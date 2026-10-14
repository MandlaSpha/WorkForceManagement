<script setup lang="ts">
import { ref } from 'vue'

import { formatHours, useShifts } from '@/entities/scheduling'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useShiftMutations } from '../model/useShiftMutations'

const shifts = useShifts()
const { create, remove } = useShiftMutations()

const code = ref('')
const start = ref('09:00')
const end = ref('17:30')
const paid = ref('480')

function add(): void {
  create.mutate(
    {
      code: code.value.trim(),
      startTime: start.value,
      endTime: end.value,
      paidMinutes: Number(paid.value),
    },
    { onSuccess: () => (code.value = '') },
  )
}
</script>

<template>
  <section class="space-y-4" aria-labelledby="shifts-title">
    <h2 id="shifts-title" class="text-base font-semibold text-ink">Shift templates</h2>
    <p class="text-sm text-ink-muted">
      Times are on the hour or half-hour. A shift that ends at or before its start runs overnight.
      Once people are rostered on a shift its times cannot change.
    </p>

    <p v-if="shifts.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="shifts.isError.value" tone="danger">
      Could not load the shifts. {{ problemMessage(shifts.error.value) }}
    </NoticeBox>
    <NoticeBox v-else-if="(shifts.data.value ?? []).length === 0">
      No shifts yet. Add one below.
    </NoticeBox>
    <ul v-else class="flex flex-wrap gap-2" aria-label="Shifts">
      <li
        v-for="shift in shifts.data.value"
        :key="shift.id"
        class="flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-sm"
      >
        <span class="font-semibold">{{ shift.code }}</span>
        <span class="tabular-nums text-ink-muted">
          {{ shift.startTime }}–{{ shift.endTime }}{{ shift.overnight ? ' (overnight)' : '' }} ·
          {{ formatHours(shift.paidMinutes) }} paid
        </span>
        <button
          type="button"
          class="text-xs font-medium text-danger underline"
          :aria-label="`Delete shift ${shift.code}`"
          @click="remove.mutate(shift.id)"
        >
          Delete
        </button>
      </li>
    </ul>
    <NoticeBox v-if="remove.isError.value" tone="danger" data-testid="shift-delete-error">
      {{ problemMessage(remove.error.value) }}
    </NoticeBox>

    <form class="space-y-3" aria-label="Add a shift" @submit.prevent="add">
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <TextField v-model="code" label="Code" />
        <TextField v-model="start" type="time" label="Start" :step="1800" />
        <TextField v-model="end" type="time" label="End" :step="1800" />
        <TextField v-model="paid" type="number" label="Paid minutes" :min="1" />
      </div>
      <AppButton type="submit" :loading="create.isPending.value" :disabled="code.trim() === ''">
        Add shift
      </AppButton>
      <NoticeBox v-if="create.isError.value" tone="danger" data-testid="shift-error">
        <p class="font-medium">The shift was not added.</p>
        <p>{{ problemMessage(create.error.value) }}</p>
      </NoticeBox>
    </form>
  </section>
</template>
