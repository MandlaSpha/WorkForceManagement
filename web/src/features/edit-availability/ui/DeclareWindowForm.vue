<script setup lang="ts">
import { ref } from 'vue'

import { KIND_LABEL, WEEKDAYS } from '@/entities/availability'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useDeclareWindow } from '../model/useAvailabilityEdits'

const weekday = ref('0')
const start = ref('09:00')
const end = ref('17:00')
const kind = ref('unavailable')
const declare = useDeclareWindow()

const DAY_OPTIONS = WEEKDAYS.map((name, index) => ({ value: String(index), label: name }))
const KIND_OPTIONS = Object.entries(KIND_LABEL).map(([value, label]) => ({ value, label }))

function submit(): void {
  declare.mutate({
    weekday: Number(weekday.value),
    startTime: start.value,
    endTime: end.value,
    kind: kind.value,
  })
}
</script>

<template>
  <form class="space-y-3" aria-label="Declare availability" @submit.prevent="submit">
    <div class="grid gap-3 sm:grid-cols-4">
      <SelectField v-model="weekday" label="Day" :options="DAY_OPTIONS" />
      <TextField v-model="start" type="time" label="From" />
      <TextField v-model="end" type="time" label="To" />
      <SelectField v-model="kind" label="This is a time I" :options="KIND_OPTIONS" />
    </div>
    <AppButton type="submit" :loading="declare.isPending.value">Add</AppButton>
    <NoticeBox v-if="declare.isError.value" tone="danger" data-testid="declare-error">
      <p class="font-medium">That was not added.</p>
      <p>{{ problemMessage(declare.error.value) }}</p>
    </NoticeBox>
  </form>
</template>
