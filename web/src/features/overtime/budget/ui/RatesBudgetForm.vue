<script setup lang="ts">
import { ref } from 'vue'

import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useSaveAllowance, useSaveBudget } from '../model/useRatesBudget'

const props = defineProps<{ month: string }>() // the first day of the month shown
const allowance = ref('')
const budget = ref('')
const saveAllowance = useSaveAllowance()
const saveBudget = useSaveBudget()

function submitAllowance(): void {
  saveAllowance.mutate(Number(allowance.value), { onSuccess: () => (allowance.value = '') })
}
function submitBudget(clear: boolean): void {
  saveBudget.mutate(
    { month: props.month, amount: clear ? null : Number(budget.value) },
    { onSuccess: () => (budget.value = '') },
  )
}
</script>

<template>
  <div class="grid gap-4 md:grid-cols-2">
    <form
      class="flex flex-wrap items-end gap-3 rounded-xl border border-line bg-surface p-4"
      aria-label="Standby allowance"
      @submit.prevent="submitAllowance"
    >
      <TextField
        v-model="allowance"
        type="number"
        label="Allowance for a day on standby (R)"
        :min="0"
        :step="0.01"
      />
      <AppButton
        type="submit"
        :loading="saveAllowance.isPending.value"
        :disabled="allowance === ''"
      >
        Save allowance
      </AppButton>
      <p v-if="saveAllowance.isError.value" class="w-full text-sm text-danger" role="alert">
        {{ problemMessage(saveAllowance.error.value) }}
      </p>
    </form>
    <form
      class="flex flex-wrap items-end gap-3 rounded-xl border border-line bg-surface p-4"
      aria-label="Budget for the month"
      @submit.prevent="submitBudget(false)"
    >
      <TextField
        v-model="budget"
        type="number"
        label="Budget for this month (R)"
        :min="0"
        :step="0.01"
      />
      <AppButton type="submit" :loading="saveBudget.isPending.value" :disabled="budget === ''">
        Save budget
      </AppButton>
      <AppButton variant="ghost" @click="submitBudget(true)">Remove budget</AppButton>
      <p v-if="saveBudget.isError.value" class="w-full text-sm text-danger" role="alert">
        {{ problemMessage(saveBudget.error.value) }}
      </p>
    </form>
  </div>
</template>
