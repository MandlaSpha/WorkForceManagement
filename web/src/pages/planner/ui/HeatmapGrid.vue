<script setup lang="ts">
import {
  cellDescription,
  heatTone,
  slotLabel,
  varianceLabel,
  type HeatTone,
  type Plan,
} from '@/entities/scheduling'
import { formatDayLabel } from '@/shared/lib/datetime'

defineProps<{ plan: Plan }>()
const emit = defineEmits<{ selectDay: [day: string] }>()

const TONE: Record<HeatTone, string> = {
  'under-high': 'bg-danger text-brand-contrast',
  under: 'bg-danger-soft text-danger',
  met: 'bg-surface-muted text-ink-muted',
  over: 'bg-brand-soft text-brand-ink',
  'over-high': 'bg-brand text-brand-contrast',
  unknown: 'text-ink-muted',
}
const SLOTS = Array.from({ length: 48 }, (_, slot) => slot)
</script>

<template>
  <div class="max-h-[34rem] overflow-auto rounded-xl border border-line bg-surface">
    <table class="w-full min-w-[40rem] border-collapse text-center text-xs" data-testid="heatmap">
      <caption class="sr-only">
        Scheduled minus required, for every half-hour of the week. A dot means the forecast does not
        say what is required.
      </caption>
      <thead class="sticky top-0 z-10 bg-surface-muted text-ink-muted">
        <tr>
          <th scope="col" class="px-2 py-2 text-left font-medium">Time</th>
          <th v-for="day in plan.days" :key="day" scope="col" class="px-1 py-1 font-medium">
            <button
              type="button"
              class="rounded-md px-2 py-1 font-medium text-brand-ink underline-offset-2 hover:underline"
              :aria-label="`Open ${formatDayLabel(day)} as a chart`"
              @click="emit('selectDay', day)"
            >
              {{ formatDayLabel(day) }}
            </button>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="slot in SLOTS" :key="slot">
          <th scope="row" class="px-2 py-0.5 text-left font-normal tabular-nums text-ink-muted">
            {{ slotLabel(slot) }}
          </th>
          <td
            v-for="day in plan.days"
            :key="day"
            class="border border-surface px-1 py-0.5 tabular-nums"
            :class="TONE[heatTone(plan.cells[day]![slot]!)]"
            :title="cellDescription(plan.cells[day]![slot]!, formatDayLabel(day))"
            :data-testid="`cell-${day}-${slot}`"
          >
            {{ varianceLabel(plan.cells[day]![slot]!) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <p class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-muted">
    <span>Number = scheduled minus required.</span>
    <span class="rounded bg-danger px-1.5 text-brand-contrast">Under</span>
    <span class="rounded bg-surface-muted px-1.5">Met</span>
    <span class="rounded bg-brand px-1.5 text-brand-contrast">Over</span>
    <span>· = no requirement known</span>
  </p>
</template>
