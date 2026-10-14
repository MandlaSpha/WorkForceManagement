<script setup lang="ts">
import { computed } from 'vue'

import { problemMessage } from '@/shared/api'
import { SHIFT_TONE, type Shift } from '@/entities/scheduling'

import { useAssignShift } from '../model/useAssignShift'

const props = defineProps<{
  queueId: number
  employeeId: number
  employeeName: string
  day: string
  dayLabel: string
  shifts: ReadonlyArray<Shift>
  currentShiftId: number | null
  editable: boolean
}>()
const emit = defineEmits<{ assigned: []; refused: [message: string] }>()

const assign = useAssignShift()

const tone = computed(() => {
  const current = props.shifts.find((s) => s.id === props.currentShiftId)
  return current ? (SHIFT_TONE[current.kind] ?? '') : 'bg-surface text-ink-muted'
})

function change(event: Event): void {
  const select = event.target as HTMLSelectElement
  const templateId = select.value === '' ? null : Number(select.value)
  assign.mutate(
    { queueId: props.queueId, employeeId: props.employeeId, day: props.day, templateId },
    {
      onSuccess: () => emit('assigned'),
      onError: (error) => {
        // The change was refused, so the cell goes back to what is really rostered.
        select.value = props.currentShiftId === null ? '' : String(props.currentShiftId)
        emit('refused', problemMessage(error))
      },
    },
  )
}
</script>

<template>
  <select
    :value="currentShiftId === null ? '' : String(currentShiftId)"
    :disabled="!editable || assign.isPending.value"
    :aria-label="`Shift for ${employeeName} on ${dayLabel}`"
    class="min-h-9 w-full rounded-md border border-line px-1 text-sm font-medium disabled:cursor-default disabled:opacity-100"
    :class="tone"
    @change="change"
  >
    <option value="">—</option>
    <option v-for="shift in shifts" :key="shift.id" :value="String(shift.id)">
      {{ shift.code }}
    </option>
  </select>
</template>
