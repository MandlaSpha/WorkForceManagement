<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  cellDescription,
  heatTone,
  slotLabel,
  varianceLabel,
  type HeatTone,
  type Plan,
} from '@/entities/scheduling'
import { formatDayLabel } from '@/shared/lib/datetime'

const props = defineProps<{ plan: Plan }>()
const emit = defineEmits<{ selectDay: [day: string] }>()

const TONE: Record<HeatTone, string> = {
  'under-high': '',
  under: '',
  met: 'bg-surface-muted text-ink-muted',
  over: '',
  'over-high': '',
  unknown: 'text-ink-muted',
}
const ALL = Array.from({ length: 48 }, (_, slot) => slot)

// Hours nobody is needed or rostered are most of a day: open on the stretch that has something in
// it, with a half-hour either side, and let the planner ask for the whole day.
const showAll = ref(false)
const active = computed(() => {
  const busy = ALL.filter((slot) =>
    props.plan.days.some((day) => {
      const cell = props.plan.cells[day]![slot]!
      return cell.scheduled > 0 || (cell.required ?? 0) > 0
    }),
  )
  if (busy.length === 0) return ALL
  const first = Math.max(0, Math.min(...busy) - 1)
  const last = Math.min(47, Math.max(...busy) + 1)
  return ALL.filter((slot) => slot >= first && slot <= last)
})

// A gap is coloured by how deep it is against the deepest one of its kind this week, so a
// difference of one reads pale and the largest reads solid. Red is short, blue is over.
const deepest = computed(() => {
  let short = 1
  let over = 1
  for (const day of props.plan.days)
    for (const cell of props.plan.cells[day]!) {
      if (cell.variance === null) continue
      if (cell.variance < 0) short = Math.max(short, -cell.variance)
      else over = Math.max(over, cell.variance)
    }
  return { short, over }
})
function gapStyle(cell: Plan['cells'][string][number]): Record<string, string> | undefined {
  if (cell.variance === null || cell.variance === 0) return undefined
  const under = cell.variance < 0
  const share = Math.min(
    1,
    Math.abs(cell.variance) / (under ? deepest.value.short : deepest.value.over),
  )
  const strength = Math.round(14 + 86 * share)
  const hue = under ? 'var(--danger)' : 'var(--brand)'
  return {
    backgroundColor: `color-mix(in srgb, ${hue} ${strength}%, var(--surface))`,
    color: strength > 55 ? 'var(--brand-contrast)' : under ? 'var(--danger)' : 'var(--brand-ink)',
  }
}
const SLOTS = computed(() => (showAll.value ? ALL : active.value))
const trimmed = computed(() => active.value.length < ALL.length)
</script>

<template>
  <div
    class="max-h-[34rem] overflow-auto rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]"
  >
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
            :style="gapStyle(plan.cells[day]![slot]!)"
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
    <button
      v-if="trimmed"
      type="button"
      class="font-medium text-brand-ink underline-offset-2 hover:underline"
      :aria-pressed="showAll"
      data-testid="show-all-hours"
      @click="showAll = !showAll"
    >
      {{ showAll ? 'Show the busy hours only' : 'Show all 24 hours' }}
    </button>
    <span>Number = scheduled minus required.</span>
    <span class="inline-flex items-center gap-1">
      Under
      <span
        class="h-3 w-16 rounded"
        style="
          background: linear-gradient(
            to right,
            color-mix(in srgb, var(--danger) 14%, var(--surface)),
            var(--danger)
          );
        "
        aria-hidden="true"
      ></span>
      <span>deeper = further short</span>
    </span>
    <span class="rounded bg-surface-muted px-1.5">Met</span>
    <span class="inline-flex items-center gap-1">
      Over
      <span
        class="h-3 w-16 rounded"
        style="
          background: linear-gradient(
            to right,
            color-mix(in srgb, var(--brand) 14%, var(--surface)),
            var(--brand)
          );
        "
        aria-hidden="true"
      ></span>
    </span>
    <span>· = no requirement known</span>
  </p>
</template>
