<script setup lang="ts">
import { computed, ref } from 'vue'

import { rangeLabel, useLeaveTypes } from '@/entities/leave'
import { problemMessage } from '@/shared/api'
import { todayInJohannesburg } from '@/shared/lib/week'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useApplyLeave } from '../model/useApplyLeave'

const types = useLeaveTypes()
const options = computed(() =>
  (types.data.value ?? []).map((t) => ({ value: String(t.id), label: t.name })),
)
const today = todayInJohannesburg()
const type = ref('')
const from = ref(today)
const to = ref(today)
const chosen = computed(() => type.value || options.value[0]?.value || '')

const apply = useApplyLeave()

function submit(): void {
  apply.mutate({ leaveTypeId: Number(chosen.value), startDate: from.value, endDate: to.value })
}
</script>

<template>
  <form class="space-y-3" aria-label="Ask for leave" @submit.prevent="submit">
    <div class="grid gap-3 sm:grid-cols-3">
      <SelectField
        :model-value="chosen"
        label="Kind of leave"
        :options="options"
        @update:model-value="type = $event"
      />
      <TextField v-model="from" type="date" label="First day" />
      <TextField v-model="to" type="date" label="Last day" />
    </div>
    <AppButton type="submit" :loading="apply.isPending.value" :disabled="chosen === ''">
      Ask for leave
    </AppButton>
    <NoticeBox v-if="apply.isError.value" tone="danger" data-testid="apply-error">
      <p class="font-medium">The leave was not asked for.</p>
      <p>{{ problemMessage(apply.error.value) }}</p>
    </NoticeBox>
    <NoticeBox v-else-if="apply.data.value" data-testid="apply-result">
      Asked for {{ apply.data.value.days }}
      {{ apply.data.value.days === 1 ? 'working day' : 'working days' }}
      ({{ rangeLabel(apply.data.value.startDate, apply.data.value.endDate) }}). Weekends and public
      holidays are not counted. It is waiting for a decision.
    </NoticeBox>
  </form>
</template>
