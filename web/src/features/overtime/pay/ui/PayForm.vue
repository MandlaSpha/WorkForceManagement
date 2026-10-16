<script setup lang="ts">
import { ref } from 'vue'

import type { PayStatus } from '@/entities/overtime'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useSavePay } from '../model/useSavePay'

const props = defineProps<{ person: PayStatus }>()
const save = useSavePay()

// A salary is never shown back: the box starts empty, and saving it empty keeps the salary on file
// and changes only the Sunday flag. Removing it is its own button.
const salary = ref('')
const sundays = ref(props.person.ordinarilyWorksSundays)

function submit(): void {
  const text = String(salary.value).trim()
  save.mutate(
    {
      employeeId: props.person.employeeId,
      body: {
        monthlySalary: text === '' ? null : Number(text),
        ordinarilyWorksSundays: sundays.value,
        clear: false,
      },
    },
    { onSuccess: () => (salary.value = '') },
  )
}

function remove(): void {
  save.mutate({
    employeeId: props.person.employeeId,
    body: { monthlySalary: null, ordinarilyWorksSundays: false, clear: true },
  })
}
</script>

<template>
  <form
    class="flex flex-wrap items-end gap-3"
    :aria-label="`Pay for ${person.employee}`"
    @submit.prevent="submit"
  >
    <TextField
      v-model="salary"
      type="number"
      :label="`Monthly salary for ${person.employee} (R)`"
      :min="1"
      :step="0.01"
    />
    <label class="flex items-center gap-2 pb-2 text-sm text-ink">
      <input v-model="sundays" type="checkbox" />
      Ordinarily works Sundays
    </label>
    <AppButton
      type="submit"
      :loading="save.isPending.value"
      :disabled="salary === '' && !person.hasSalary"
    >
      Save pay
    </AppButton>
    <AppButton v-if="person.hasSalary" variant="ghost" @click="remove">Remove salary</AppButton>
    <span v-if="save.isError.value" class="text-xs text-danger" role="alert">
      {{ problemMessage(save.error.value) }}
    </span>
  </form>
</template>
