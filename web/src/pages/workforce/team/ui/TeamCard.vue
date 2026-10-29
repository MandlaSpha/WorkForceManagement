<script setup lang="ts">
import { computed } from 'vue'

import { contractLine, hoursText, initials, type TeamPerson } from '@/entities/workforce/team'
import RingGauge from '@/shared/ui/RingGauge.vue'

const props = defineProps<{ person: TeamPerson; index: number }>()
const emit = defineEmits<{ open: [person: TeamPerson] }>()

const tone = computed(() =>
  props.person.onTrack === null ? 'brand' : props.person.onTrack ? 'ok' : 'warn',
)
const verdict = computed(() =>
  props.person.onTrack === null
    ? 'Adherence not loaded'
    : props.person.onTrack
      ? 'On track'
      : 'Below target',
)
// A stagger that stops growing after a few cards, so a big team does not wait seconds to appear.
const delay = computed(() => `${Math.min(props.index, 8) * 45}ms`)
</script>

<template>
  <li class="team-card" :style="{ animationDelay: delay }">
    <button
      type="button"
      class="lift press block w-full rounded-2xl border border-line bg-surface p-4 text-left shadow-card focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      :data-testid="`card-${person.empNo}`"
      :aria-label="`${person.name}, ${person.empNo}. Open this week.`"
      @click="emit('open', person)"
    >
      <div class="flex items-center gap-3">
        <span
          class="grid size-11 shrink-0 place-items-center rounded-full bg-brand-soft text-sm font-semibold text-brand-ink"
          aria-hidden="true"
        >
          {{ initials(person.name) }}
        </span>
        <div class="min-w-0">
          <p class="truncate text-sm font-semibold text-ink">{{ person.name }}</p>
          <p class="truncate text-xs text-ink-muted">{{ contractLine(person) }}</p>
          <p class="truncate text-xs text-ink-muted">{{ person.empNo }}</p>
        </div>
      </div>

      <div class="mt-4 flex items-center gap-4">
        <RingGauge
          :value="person.adherencePct"
          label="Adherence this week"
          :tone="tone"
          :size="84"
        />
        <div class="min-w-0 text-sm">
          <p class="font-medium text-ink">Adherence</p>
          <p class="text-xs text-ink-muted" :data-testid="`verdict-${person.empNo}`">
            {{ verdict }}
          </p>
        </div>
      </div>

      <dl class="mt-4 grid grid-cols-2 gap-2 rounded-xl bg-surface-muted p-3 text-xs">
        <div>
          <dt class="text-ink-muted">Rostered</dt>
          <dd class="mt-0.5 text-sm font-semibold tabular-nums text-ink">
            {{ hoursText(person.rosteredHours) }}
            <span class="font-normal text-ink-muted">of {{ hoursText(person.contractHours) }}</span>
          </dd>
        </div>
        <div>
          <dt class="text-ink-muted">Shifts</dt>
          <dd class="mt-0.5 text-sm font-semibold tabular-nums text-ink">{{ person.shifts }}</dd>
        </div>
      </dl>

      <ul
        v-if="person.pendingLeave > 0 || person.openSwaps > 0 || person.checkIn"
        class="mt-3 flex flex-wrap gap-1.5"
        aria-label="Waiting on this person"
      >
        <li
          v-if="person.pendingLeave > 0"
          class="rounded-full bg-warn-soft px-2.5 py-0.5 text-xs font-medium text-warn"
        >
          {{ person.pendingLeave > 1 ? `${person.pendingLeave} leave requests` : 'Leave request' }}
        </li>
        <li
          v-if="person.openSwaps > 0"
          class="rounded-full bg-brand-soft px-2.5 py-0.5 text-xs font-medium text-brand-ink"
        >
          {{ person.openSwaps > 1 ? `${person.openSwaps} open swaps` : 'Open swap' }}
        </li>
        <li
          v-if="person.checkIn"
          class="rounded-full bg-ok-soft px-2.5 py-0.5 text-xs font-medium text-ok"
        >
          Check in
        </li>
      </ul>
    </button>
  </li>
</template>

<style scoped>
@keyframes card-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
}
@media (prefers-reduced-motion: no-preference) {
  .team-card {
    animation: card-in 0.4s cubic-bezier(0.2, 0.7, 0.2, 1) both;
  }
}
</style>
