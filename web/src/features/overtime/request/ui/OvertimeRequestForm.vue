<script setup lang="ts">
import { computed, ref } from 'vue'

import type { Employee } from '@/entities/scheduling'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useAskForOvertime } from '../model/useAskForOvertime'

const props = defineProps<{ employees: ReadonlyArray<Employee> }>()

const ask = useAskForOvertime()
const employeeId = ref('')
const day = ref('')
const start = ref('18:00')
const end = ref('20:00')
const reason = ref('')

const options = computed(() => props.employees.map((e) => ({ value: String(e.id), label: e.name })))

function submit(): void {
  ask.mutate(
    {
      employeeId: Number(employeeId.value),
      day: day.value,
      startTime: start.value,
      endTime: end.value,
      reason: reason.value.trim(),
    },
    { onSuccess: () => (reason.value = '') },
  )
}
</script>

<template>
  <form
    class="space-y-3 rounded-xl border border-line bg-surface p-4"
    aria-label="Ask for overtime"
    @submit.prevent="submit"
  >
    <h3 class="text-sm font-semibold text-ink">Ask for overtime</h3>
    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <SelectField v-model="employeeId" label="Person" :options="options" />
      <TextField v-model="day" type="date" label="Day" />
      <TextField v-model="start" type="time" label="From" :step="900" />
      <TextField v-model="end" type="time" label="To" :step="900" />
      <TextField v-model="reason" label="Reason (optional)" />
    </div>
    <AppButton
      type="submit"
      :loading="ask.isPending.value"
      :disabled="employeeId === '' || day === ''"
    >
      Ask for overtime
    </AppButton>
    <NoticeBox v-if="ask.isSuccess.value" data-testid="ask-result">
      Asked for. It now waits for a planner or admin to approve it.
    </NoticeBox>
    <NoticeBox v-if="ask.isError.value" tone="danger" data-testid="ask-error">
      <p class="font-medium">The overtime was not asked for.</p>
      <p>{{ problemMessage(ask.error.value) }}</p>
    </NoticeBox>
  </form>
</template>
