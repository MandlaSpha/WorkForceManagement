<script setup lang="ts">
import { computed, ref } from 'vue'

import type { QueueInfo } from '@/entities/call-data'
import type { ContractRow, Customer } from '@/entities/contract'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useSaveContract } from '../model/useSaveContract'

const props = defineProps<{
  contract: ContractRow | null
  customers: ReadonlyArray<Customer>
  queues: ReadonlyArray<QueueInfo>
}>()
const emit = defineEmits<{ saved: []; cancel: [] }>()

const { create, update } = useSaveContract()
const customerId = ref(String(props.contract?.customerId ?? props.customers[0]?.id ?? ''))
const name = ref(props.contract?.name ?? '')
// Text first: a number input hands back a number once something is typed.
const target = ref(String(props.contract?.slTargetPct ?? 80))
const threshold = ref(String(props.contract?.slThresholdS ?? 20))
const active = ref(props.contract?.active ?? true)
const chosen = ref<number[]>(props.contract?.queues.map((q) => q.id) ?? [])

const options = computed(() => props.customers.map((c) => ({ value: String(c.id), label: c.name })))
const pending = computed(() => create.isPending.value || update.isPending.value)
const failure = computed(() =>
  create.isError.value ? create.error.value : update.isError.value ? update.error.value : null,
)

function toggle(id: number, on: boolean): void {
  chosen.value = on ? [...chosen.value, id] : chosen.value.filter((q) => q !== id)
}

function submit(): void {
  const shared = {
    name: name.value.trim(),
    slTargetPct: Number(String(target.value).trim()),
    slThresholdS: Number(String(threshold.value).trim()),
    queueIds: chosen.value,
  }
  const done = { onSuccess: () => emit('saved') }
  if (props.contract)
    update.mutate({ id: props.contract.id, body: { ...shared, active: active.value } }, done)
  else create.mutate({ ...shared, customerId: Number(customerId.value) }, done)
}
</script>

<template>
  <form
    class="space-y-4 rounded-xl border border-line bg-surface p-4"
    :aria-label="contract ? `Change ${contract.name}` : 'Add a contract'"
    @submit.prevent="submit"
  >
    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <SelectField v-if="!contract" v-model="customerId" label="Customer" :options="options" />
      <TextField v-model="name" label="Contract name" />
      <TextField
        v-model="target"
        type="number"
        label="Service level promised (%)"
        :min="1"
        :max="100"
        :step="0.5"
      />
      <TextField v-model="threshold" type="number" label="Within (seconds)" :min="1" :max="600" />
    </div>

    <fieldset class="space-y-2">
      <legend class="text-xs font-medium text-ink-muted">
        Queues held to this promise (their target is set from it)
      </legend>
      <p v-if="queues.length === 0" class="text-sm text-ink-muted">
        There are no queues yet. They are created when call data is imported.
      </p>
      <label v-for="q in queues" :key="q.id" class="flex items-center gap-2 text-sm text-ink">
        <input
          type="checkbox"
          :checked="chosen.includes(q.id)"
          @change="toggle(q.id, ($event.target as HTMLInputElement).checked)"
        />
        {{ q.name }}
      </label>
    </fieldset>

    <label v-if="contract" class="flex items-center gap-2 text-sm text-ink">
      <input v-model="active" type="checkbox" />
      Active (an ended contract is kept for the history)
    </label>

    <div class="flex items-center gap-2">
      <AppButton
        type="submit"
        :loading="pending"
        :disabled="name.trim() === '' || (!contract && customerId === '')"
      >
        {{ contract ? 'Save changes' : 'Add contract' }}
      </AppButton>
      <AppButton v-if="contract" variant="ghost" @click="emit('cancel')">Cancel</AppButton>
    </div>
    <NoticeBox v-if="failure" tone="danger" data-testid="contract-error">
      <p class="font-medium">The contract was not saved.</p>
      <p>{{ problemMessage(failure) }}</p>
    </NoticeBox>
  </form>
</template>
