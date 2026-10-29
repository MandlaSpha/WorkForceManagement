<script setup lang="ts">
// TODO(WFM-dialog): swap this inline drawer for shared/ui/Dialog.vue once that component is on
// main. It keeps its own focus handling meanwhile: focus moves in on open, Tab stays inside,
// Escape and the backdrop close it, and focus goes back to the card that opened it.
import { X } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import {
  contractLine,
  dayLabel,
  hoursText,
  initials,
  type TeamPerson,
} from '@/entities/workforce/team'
import BarSeries from '@/shared/ui/BarSeries.vue'

const props = defineProps<{ person: TeamPerson; thresholdPct: number }>()
const emit = defineEmits<{ close: [] }>()

const panel = ref<HTMLElement | null>(null)
const closeButton = ref<HTMLButtonElement | null>(null)
const titleId = 'team-drawer-title'

const dayBars = computed(() =>
  props.person.shiftList.map((s) => ({
    label: dayLabel(s.day).split(' ')[0] ?? s.day,
    title: `${dayLabel(s.day)}, ${s.shift}`,
    value: s.adherencePct,
  })),
)
const anyAdherence = computed(() => props.person.shiftList.some((s) => s.adherencePct !== null))
const days = (n: number | null) => (n === null ? 'Not set' : `${n} d`)

const FOCUSABLE =
  'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])'

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    event.stopPropagation()
    emit('close')
    return
  }
  if (event.key !== 'Tab' || !panel.value) return
  const items = [...panel.value.querySelectorAll<HTMLElement>(FOCUSABLE)]
  const first = items[0]
  const last = items[items.length - 1]
  if (!first || !last) return
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

onMounted(async () => {
  document.addEventListener('keydown', onKey)
  await nextTick()
  closeButton.value?.focus()
})
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="fixed inset-0 z-40 flex justify-end">
    <div
      class="drawer-backdrop absolute inset-0 bg-ink/40"
      data-testid="drawer-backdrop"
      aria-hidden="true"
      @click="emit('close')"
    />
    <aside
      ref="panel"
      class="drawer-panel relative flex h-full w-full max-w-md flex-col overflow-y-auto bg-surface shadow-pop"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="titleId"
      data-testid="team-drawer"
    >
      <header class="flex items-start gap-3 border-b border-line p-5">
        <span
          class="grid size-12 shrink-0 place-items-center rounded-full bg-brand-soft font-semibold text-brand-ink"
          aria-hidden="true"
        >
          {{ initials(person.name) }}
        </span>
        <div class="min-w-0 flex-1">
          <h2 :id="titleId" class="truncate text-lg font-semibold text-ink">{{ person.name }}</h2>
          <p class="text-xs text-ink-muted">{{ person.empNo }} · {{ contractLine(person) }}</p>
          <p class="mt-1 text-xs text-ink-muted">
            {{ hoursText(person.rosteredHours) }} rostered of
            {{ hoursText(person.contractHours) }} this week
          </p>
        </div>
        <button
          ref="closeButton"
          type="button"
          class="press grid size-9 place-items-center rounded-full text-ink-muted hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-focus"
          aria-label="Close"
          @click="emit('close')"
        >
          <X :size="18" aria-hidden="true" />
        </button>
      </header>

      <div class="space-y-6 p-5">
        <section aria-labelledby="drawer-shifts">
          <h3 id="drawer-shifts" class="text-sm font-semibold text-ink">Shifts this week</h3>
          <p v-if="person.shiftList.length === 0" class="mt-2 text-sm text-ink-muted">
            No published shifts this week.
          </p>
          <ul v-else class="mt-2 divide-y divide-line rounded-xl border border-line text-sm">
            <li
              v-for="s in person.shiftList"
              :key="s.day"
              class="flex items-center justify-between gap-3 px-3 py-2"
            >
              <span class="text-ink">{{ dayLabel(s.day) }}</span>
              <span class="tabular-nums text-ink-muted">
                {{ s.shift }} {{ s.startTime }}–{{ s.endTime }}
              </span>
            </li>
          </ul>
        </section>

        <section aria-labelledby="drawer-adherence">
          <h3 id="drawer-adherence" class="text-sm font-semibold text-ink">Adherence by day</h3>
          <p v-if="!anyAdherence" class="mt-2 text-sm text-ink-muted" data-testid="drawer-no-data">
            No adherence data for this week.
          </p>
          <div v-else class="mt-2">
            <BarSeries
              :items="dayBars"
              value-label="Adherence (%)"
              :format="(n: number) => `${Math.round(n)}%`"
              :summary="`Adherence by day for ${person.name}. The target is ${thresholdPct}%.`"
            />
          </div>
        </section>

        <section aria-labelledby="drawer-balance">
          <h3 id="drawer-balance" class="text-sm font-semibold text-ink">Leave balance</h3>
          <p v-if="person.leaveBalances.length === 0" class="mt-2 text-sm text-ink-muted">
            No leave types are set up.
          </p>
          <table v-else class="mt-2 w-full text-left text-sm">
            <thead class="text-xs text-ink-muted">
              <tr>
                <th scope="col" class="py-1 font-medium">Type</th>
                <th scope="col" class="py-1 text-right font-medium">Taken</th>
                <th scope="col" class="py-1 text-right font-medium">Pending</th>
                <th scope="col" class="py-1 text-right font-medium">Left</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-line">
              <tr v-for="b in person.leaveBalances" :key="b.leaveType">
                <th scope="row" class="py-1.5 font-normal text-ink">{{ b.leaveType }}</th>
                <td class="py-1.5 text-right tabular-nums text-ink-muted">
                  {{ days(b.takenDays) }}
                </td>
                <td class="py-1.5 text-right tabular-nums text-ink-muted">
                  {{ days(b.pendingDays) }}
                </td>
                <td class="py-1.5 text-right font-medium tabular-nums text-ink">
                  {{ days(b.availableDays) }}
                </td>
              </tr>
            </tbody>
          </table>
        </section>

        <section aria-labelledby="drawer-pending">
          <h3 id="drawer-pending" class="text-sm font-semibold text-ink">Waiting for a decision</h3>
          <p
            v-if="person.pendingRequests.length === 0 && person.openSwaps === 0"
            class="mt-2 text-sm text-ink-muted"
          >
            Nothing is waiting.
          </p>
          <ul v-else class="mt-2 space-y-2 text-sm">
            <li
              v-for="(r, i) in person.pendingRequests"
              :key="i"
              class="rounded-xl bg-warn-soft px-3 py-2 text-warn"
            >
              {{ r.leaveType }}: {{ r.startDate }} to {{ r.endDate }} ({{ r.days }}
              {{ r.days === 1 ? 'day' : 'days' }})
            </li>
            <li
              v-if="person.openSwaps > 0"
              class="rounded-xl bg-brand-soft px-3 py-2 text-brand-ink"
            >
              {{ person.openSwaps }} shift swap{{ person.openSwaps === 1 ? '' : 's' }} waiting
            </li>
          </ul>
        </section>
      </div>
    </aside>
  </div>
</template>

<style scoped>
@keyframes drawer-in {
  from {
    transform: translateX(24px);
    opacity: 0;
  }
}
@keyframes backdrop-in {
  from {
    opacity: 0;
  }
}
@media (prefers-reduced-motion: no-preference) {
  .drawer-panel {
    animation: drawer-in 0.28s cubic-bezier(0.2, 0.7, 0.2, 1) both;
  }
  .drawer-backdrop {
    animation: backdrop-in 0.2s ease-out both;
  }
}
</style>
