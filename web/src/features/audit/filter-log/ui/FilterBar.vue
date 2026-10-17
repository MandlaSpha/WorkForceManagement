<script setup lang="ts">
import { reactive } from 'vue'

import { NO_FILTERS, useAuditOptions, type AuditFilters } from '@/entities/audit-log'
import AppButton from '@/shared/ui/AppButton.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TextField from '@/shared/ui/TextField.vue'

const props = defineProps<{ applied: AuditFilters }>()
const emit = defineEmits<{ apply: [filters: AuditFilters] }>()

const options = useAuditOptions()
const draft = reactive<AuditFilters>({ ...props.applied })

const ANY = { value: '', label: 'Any' }
const list = (items: ReadonlyArray<{ value: string; label: string }> | undefined) => [
  ANY,
  ...(items ?? []),
]

function search(): void {
  emit('apply', { ...draft })
}

function reset(): void {
  Object.assign(draft, NO_FILTERS)
  emit('apply', { ...NO_FILTERS })
}
</script>

<template>
  <form class="space-y-3" aria-label="Filter the audit log" @submit.prevent="search">
    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <TextField v-model="draft.actor" label="Who (username, or system)" autocomplete="off" />
      <SelectField
        v-model="draft.action"
        label="What (action)"
        :options="list(options.data.value?.actions)"
      />
      <SelectField
        v-model="draft.entityType"
        label="Entity"
        :options="list(options.data.value?.entityTypes)"
      />
      <SelectField
        v-model="draft.outcome"
        label="Outcome"
        :options="list(options.data.value?.outcomes)"
      />
      <TextField v-model="draft.fromDay" type="date" label="From (South African time)" />
      <TextField v-model="draft.toDay" type="date" label="To (South African time)" />
    </div>
    <div class="flex flex-wrap gap-2">
      <AppButton type="submit">Search</AppButton>
      <AppButton variant="secondary" @click="reset">Clear filters</AppButton>
    </div>
  </form>
</template>
