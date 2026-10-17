<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { slotLabel, useSuggestions } from '@/entities/intraday'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

import { useMoveBreak } from '../model/useMoveBreak'

const props = defineProps<{
  queueId: number
  day: string
  halfHour: number
  /** The short stretch as clock times, "HH:MM": what the overtime form is filled with. */
  from: string
  to: string
}>()

const suggestions = useSuggestions(
  computed(() => props.queueId),
  computed(() => props.day),
  computed(() => props.halfHour),
)
const move = useMoveBreak()

function overtimeLink(employeeId?: number) {
  return {
    path: '/overtime',
    query: {
      day: props.day,
      from: props.from,
      to: props.to,
      ...(employeeId === undefined ? {} : { employeeId: String(employeeId) }),
    },
  }
}
</script>

<template>
  <div
    class="mt-2 space-y-3 rounded-lg border border-line bg-surface-muted p-3"
    :data-testid="`actions-${halfHour}`"
  >
    <p v-if="suggestions.isPending.value" class="text-sm text-ink-muted">Looking for options…</p>
    <NoticeBox v-else-if="suggestions.isError.value" tone="danger">
      Could not look for options. {{ problemMessage(suggestions.error.value) }}
    </NoticeBox>
    <template v-else-if="suggestions.data.value">
      <section aria-label="Ask for overtime" class="space-y-1">
        <h3 class="text-sm font-semibold text-ink">Ask for overtime, {{ from }} to {{ to }}</h3>
        <p v-if="suggestions.data.value.people.length === 0" class="text-sm text-ink-muted">
          Nobody skilled on this queue is free and within the rest and hours rules.
        </p>
        <ul v-else class="space-y-1 text-sm" aria-label="People who could cover">
          <li
            v-for="p in suggestions.data.value.people"
            :key="p.employeeId"
            class="flex items-center gap-2"
          >
            <span class="font-medium text-ink">{{ p.name }}</span>
            <span class="text-xs text-ink-muted">
              {{ (p.weekMinutes / 60).toFixed(1) }} h this week
            </span>
            <RouterLink
              :to="overtimeLink(p.employeeId)"
              class="font-medium text-brand-ink underline"
              :aria-label="`Ask ${p.name} for overtime`"
            >
              Ask for overtime
            </RouterLink>
          </li>
        </ul>
        <RouterLink :to="overtimeLink()" class="text-sm font-medium text-brand-ink underline">
          Open the overtime form for this time
        </RouterLink>
      </section>

      <section
        v-if="suggestions.data.value.breaks.length > 0"
        aria-label="Move a break"
        class="space-y-1"
      >
        <h3 class="text-sm font-semibold text-ink">Move a break</h3>
        <ul class="space-y-1 text-sm" aria-label="Breaks that could move">
          <li v-for="b in suggestions.data.value.breaks" :key="b.activityId" class="flex gap-2">
            <span class="text-ink">
              {{ b.employee }}: {{ b.kind }} {{ b.start }} to {{ b.end }}
            </span>
            <AppButton
              variant="secondary"
              :loading="move.isPending.value"
              @click="move.mutate({ activityId: b.activityId, startTime: b.moveTo })"
            >
              Move to {{ b.moveTo }}
            </AppButton>
          </li>
        </ul>
        <p class="text-xs text-ink-muted">
          The new time keeps the phones covered. {{ slotLabel(halfHour) }} is freed.
        </p>
        <NoticeBox v-if="move.isError.value" tone="danger" data-testid="move-error">
          The break was not moved. {{ problemMessage(move.error.value) }}
        </NoticeBox>
      </section>
    </template>
  </div>
</template>
