<script setup lang="ts">
import { ref } from 'vue'

import type { HiringPlan } from '@/entities/workforce/hiring-plan'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useSavePlan } from '../model/usePlanWrites'

const props = defineProps<{ plan: HiringPlan | null; seesPay: boolean }>()
const emit = defineEmits<{ saved: [id: number] }>()

const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' })
const list = (values: ReadonlyArray<number>) => values.join(', ')

const name = ref(props.plan?.name ?? '')
const startMonth = ref((props.plan?.startMonth ?? `${today.slice(0, 7)}-01`).slice(0, 7))
const incumbents = ref(String(props.plan?.incumbents ?? ''))
const attrition = ref(String(props.plan?.attritionPctPerMonth ?? '2'))
const ramp = ref(list(props.plan?.ramp ?? [0.25, 0.5, 0.75, 1]))
const required = ref(list(props.plan?.rows.map((r) => r.required) ?? []))
const cost = ref(
  props.plan?.costPerPersonMonth == null ? '' : String(props.plan.costPerPersonMonth),
)

const save = useSavePlan()
const numbers = (text: string) =>
  text
    .split(/[\s,;]+/)
    .filter(Boolean)
    .map(Number)

function submit(): void {
  save.mutate(
    {
      id: props.plan?.id ?? null,
      body: {
        name: name.value,
        startMonth: `${startMonth.value}-01`,
        incumbents: Number(incumbents.value),
        attritionPctPerMonth: Number(attrition.value),
        ramp: numbers(ramp.value),
        required: numbers(required.value),
        costPerPersonMonth: props.seesPay && cost.value !== '' ? Number(cost.value) : null,
      },
    },
    { onSuccess: (saved) => emit('saved', saved.id) },
  )
}
</script>

<template>
  <form
    class="space-y-3 rounded-xl border border-line bg-surface p-4"
    :aria-label="plan ? 'Change this hiring plan' : 'Make a hiring plan'"
    @submit.prevent="submit"
  >
    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <TextField v-model="name" label="Name" />
      <label class="block space-y-1 text-xs font-medium text-ink-muted">
        First month
        <input
          v-model="startMonth"
          type="month"
          class="block min-h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink"
        />
      </label>
      <TextField
        v-model="incumbents"
        type="number"
        label="People employed now"
        :min="0"
        :step="0.5"
      />
      <TextField
        v-model="attrition"
        type="number"
        label="Leave each month (%)"
        :min="0"
        :max="99"
        :step="0.1"
      />
    </div>
    <label class="block text-xs font-medium text-ink-muted">
      How productive a new hire is, month by month (ends at 1)
      <input
        v-model="ramp"
        class="mt-1 block min-h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink"
      />
    </label>
    <label class="block text-xs font-medium text-ink-muted">
      People needed each month (12 to 18 numbers, separated by commas)
      <textarea
        v-model="required"
        rows="2"
        class="mt-1 block w-full rounded-lg border border-line bg-surface p-2 text-sm text-ink"
      />
    </label>
    <TextField
      v-if="seesPay"
      v-model="cost"
      type="number"
      label="Cost of one person for a month (R, optional)"
      :min="0"
      :step="0.01"
    />
    <div class="flex items-center gap-3">
      <AppButton type="submit" :loading="save.isPending.value">
        {{ plan ? 'Save changes' : 'Make plan' }}
      </AppButton>
    </div>
    <p v-if="save.isError.value" class="text-sm text-danger" role="alert" data-testid="plan-error">
      {{ problemMessage(save.error.value) }}
    </p>
  </form>
</template>
