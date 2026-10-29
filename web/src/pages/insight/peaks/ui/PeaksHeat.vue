<script setup lang="ts">
import { computed } from 'vue'

import { slotName, WEEKDAYS, type HeatCell } from '@/entities/peaks'

const props = defineProps<{ cells: ReadonlyArray<HeatCell> }>()

const HOURS = Array.from({ length: 24 }, (_, h) => h)
const SLOTS = Array.from({ length: 48 }, (_, s) => s)
const STEPS = [0, 0.25, 0.5, 0.75, 1]

const grid = computed(() => {
  const m = new Map<string, HeatCell>()
  for (const c of props.cells) m.set(`${c.weekday}-${c.slot}`, c)
  return m
})
const max = computed(() => Math.max(0, ...props.cells.map((c) => Number(c.averageOffered))))

function avg(w: number, s: number): string | null {
  return grid.value.get(`${w}-${s}`)?.averageOffered ?? null
}
// Darker is busier. The floor keeps the palest cell visible against the card.
function opacity(value: string): number {
  return 0.3 + 0.7 * (max.value > 0 ? Number(value) / max.value : 0)
}
function words(name: string, s: number): string {
  const v = avg(WEEKDAYS.indexOf(name), s)
  return `${name} ${slotName(s)}: ${v === null ? 'no calls' : `${v} calls on average`}`
}
</script>

<template>
  <section
    class="rounded-2xl border border-line bg-surface p-4 shadow-card"
    aria-labelledby="peaks-heat-title"
    data-testid="peaks-heat"
  >
    <h2 id="peaks-heat-title" class="text-sm font-semibold text-ink">
      Average calls, weekday by half-hour
    </h2>
    <div class="mt-3 overflow-x-auto">
      <table class="w-full min-w-[40rem] border-separate border-spacing-px text-xs">
        <caption class="sr-only">
          Average calls offered in each half-hour of each weekday, over the days measured. A darker
          cell is busier. A cell with a dashed outline had no calls. Busiest cell:
          {{
            max
          }}.
        </caption>
        <thead>
          <tr>
            <th scope="col" class="w-12 text-left font-medium text-ink-muted">Day</th>
            <th
              v-for="h in HOURS"
              :key="h"
              scope="col"
              colspan="2"
              class="text-left font-normal text-ink-muted"
            >
              <span class="sr-only">{{ slotName(h * 2) }}</span>
              <span aria-hidden="true">{{ h % 3 === 0 ? String(h).padStart(2, '0') : '' }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="name in WEEKDAYS" :key="name">
            <th scope="row" class="text-left font-normal text-ink">
              <span aria-hidden="true">{{ name.slice(0, 3) }}</span>
              <span class="sr-only">{{ name }}</span>
            </th>
            <td
              v-for="s in SLOTS"
              :key="s"
              class="h-6 min-w-2.5 p-0"
              :title="words(name, s)"
              :data-level="avg(WEEKDAYS.indexOf(name), s) ?? 'none'"
            >
              <div
                v-if="avg(WEEKDAYS.indexOf(name), s) !== null"
                class="h-6 rounded-sm bg-brand"
                :style="{ opacity: opacity(avg(WEEKDAYS.indexOf(name), s) as string) }"
              ></div>
              <div v-else class="h-6 rounded-sm border border-dashed border-line"></div>
              <span class="sr-only">{{ words(name, s) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div
      class="mt-3 flex flex-wrap items-center gap-2 text-xs text-ink-muted"
      data-testid="heat-legend"
    >
      <span>Fewer</span>
      <span class="flex gap-0.5" aria-hidden="true">
        <span
          v-for="f in STEPS"
          :key="f"
          class="inline-block h-3 w-6 rounded-sm bg-brand"
          :style="{ opacity: 0.3 + 0.7 * f }"
        ></span>
      </span>
      <span>More (busiest cell: {{ max.toFixed(1) }} calls)</span>
      <span class="ml-2 inline-flex items-center gap-1.5">
        <span class="inline-block size-3 rounded-sm border border-dashed border-line"></span>
        No calls
      </span>
    </div>
  </section>
</template>
