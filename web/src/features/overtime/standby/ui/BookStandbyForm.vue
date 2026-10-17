<script setup lang="ts">
import { computed, ref } from 'vue'

import type { Employee } from '@/entities/scheduling'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useBookStandby } from '../model/useStandbyWrites'

const props = defineProps<{ employees: ReadonlyArray<Employee> }>()
const book = useBookStandby()
const employeeId = ref('')
const day = ref('')
const options = computed(() => props.employees.map((e) => ({ value: String(e.id), label: e.name })))

function submit(): void {
  book.mutate({ employeeId: Number(employeeId.value), day: day.value })
}
</script>

<template>
  <form
    class="flex flex-wrap items-end gap-3 rounded-xl border border-line bg-surface p-4"
    aria-label="Put somebody on standby"
    @submit.prevent="submit"
  >
    <SelectField
      v-model="employeeId"
      label="Person"
      :options="options"
      empty-text="No people yet"
    />
    <TextField v-model="day" type="date" label="Day" />
    <AppButton type="submit" :loading="book.isPending.value" :disabled="!employeeId || !day">
      Put on standby
    </AppButton>
    <p
      v-if="book.isError.value"
      class="w-full text-sm text-danger"
      role="alert"
      data-testid="standby-error"
    >
      {{ problemMessage(book.error.value) }}
    </p>
  </form>
</template>
