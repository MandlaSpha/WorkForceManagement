<script setup lang="ts">
import { computed, ref } from 'vue'

import { useQueues } from '@/entities/call-data'
import { changeLabel, useEvents } from '@/entities/forecast'
import { problemMessage } from '@/shared/api'
import { formatDayLabel } from '@/shared/lib/datetime'
import { addDays, todayInJohannesburg } from '@/shared/lib/week'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useEventMutations } from '../model/useEventMutations'

const props = defineProps<{ queueId: number | null; canChange: boolean }>()

const events = useEvents(computed(() => props.queueId))
const queues = useQueues()
const { create, remove } = useEventMutations()

const today = todayInJohannesburg()
const name = ref('')
const from = ref(today)
const to = ref(addDays(today, 0))
const change = ref('20')
const scope = ref('') // "" is every queue

const scopeOptions = computed(() => [
  { value: '', label: 'All queues' },
  ...(queues.data.value ?? []).map((q) => ({ value: String(q.id), label: q.name })),
])

function add(): void {
  create.mutate(
    {
      name: name.value.trim(),
      queueId: scope.value === '' ? null : Number(scope.value),
      dateFrom: from.value,
      dateTo: to.value,
      upliftPct: Number(change.value),
    },
    { onSuccess: () => (name.value = '') },
  )
}
</script>

<template>
  <section class="space-y-3" aria-labelledby="events-title">
    <h2 id="events-title" class="text-base font-semibold text-ink">Events</h2>
    <p v-if="events.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="events.isError.value" tone="danger">
      Could not load the events. {{ problemMessage(events.error.value) }}
    </NoticeBox>
    <NoticeBox v-else-if="(events.data.value ?? []).length === 0">
      No events yet. Forecasts rest on the usual weekly pattern alone.
    </NoticeBox>
    <div v-else class="overflow-x-auto rounded-xl border border-line bg-surface">
      <table class="w-full min-w-[34rem] text-left text-sm">
        <caption class="sr-only">
          Events
        </caption>
        <thead class="border-b border-line bg-surface-muted text-xs text-ink-muted">
          <tr>
            <th scope="col" class="px-4 py-2 font-medium">Event</th>
            <th scope="col" class="px-3 py-2 font-medium">Queue</th>
            <th scope="col" class="px-3 py-2 font-medium">Days</th>
            <th scope="col" class="px-3 py-2 font-medium">Calls</th>
            <th scope="col" class="px-4 py-2 text-right font-medium">
              <span class="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in events.data.value" :key="e.id" class="border-b border-line">
            <th scope="row" class="px-4 py-2 font-medium text-ink">{{ e.name }}</th>
            <td class="px-3 py-2">{{ e.queue ?? 'All queues' }}</td>
            <td class="px-3 py-2 tabular-nums">
              {{ formatDayLabel(e.dateFrom) }}
              <template v-if="e.dateTo !== e.dateFrom">to {{ formatDayLabel(e.dateTo) }}</template>
            </td>
            <td class="px-3 py-2 tabular-nums">{{ changeLabel(e.upliftPct) }}</td>
            <td class="px-4 py-2 text-right">
              <button
                v-if="canChange"
                type="button"
                class="text-xs font-medium text-danger underline"
                :aria-label="`Remove event ${e.name}`"
                @click="remove.mutate(e.id)"
              >
                Remove
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <NoticeBox v-if="remove.isError.value" tone="danger" data-testid="event-remove-error">
      {{ problemMessage(remove.error.value) }}
    </NoticeBox>

    <form v-if="canChange" class="space-y-3" aria-label="Add an event" @submit.prevent="add">
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <TextField v-model="name" label="Name" />
        <TextField v-model="from" type="date" label="First day" />
        <TextField v-model="to" type="date" label="Last day" />
        <SelectField v-model="scope" label="Applies to" :options="scopeOptions" />
        <TextField
          v-model="change"
          type="number"
          label="Change in calls (%)"
          :min="-100"
          :max="500"
          :step="1"
        />
      </div>
      <AppButton type="submit" :loading="create.isPending.value" :disabled="name.trim() === ''">
        Add event
      </AppButton>
      <NoticeBox v-if="create.isError.value" tone="danger" data-testid="event-error">
        <p class="font-medium">The event was not added.</p>
        <p>{{ problemMessage(create.error.value) }}</p>
      </NoticeBox>
    </form>
  </section>
</template>
