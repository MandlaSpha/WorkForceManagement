<script setup lang="ts">
import { computed } from 'vue'

import { heat, slotLabel, type RangeDay } from '@/entities/forecast'
import { formatDayLabel } from '@/shared/lib/datetime'

const props = defineProps<{ days: ReadonlyArray<RangeDay> }>()
const emit = defineEmits<{ open: [day: string] }>()

const HOURS = Array.from({ length: 24 }, (_, h) => h)
const SLOTS = Array.from({ length: 48 }, (_, s) => s)

// The strongest colour is the most people needed in any half-hour of the week.
const max = computed(() =>
  Math.max(0, ...props.days.flatMap((d) => (d.requiredBySlot ?? []).map((n) => n ?? 0))),
)

function style(n: number | null): Record<string, string> | undefined {
  const level = heat(n, max.value)
  if (level === null || level === 0) return undefined
  return { opacity: String(0.15 + 0.85 * level) }
}
</script>

<template>
  <section class="space-y-2" aria-labelledby="heat-title">
    <h3 id="heat-title" class="text-sm font-semibold text-ink">
      People needed, half-hour by half-hour
    </h3>
    <div class="overflow-x-auto rounded-xl border border-line bg-surface p-2">
      <table class="w-full min-w-[44rem] border-separate border-spacing-px text-xs">
        <caption class="sr-only">
          Agents to roster in each half-hour of each day. A darker cell needs more people. A hatched
          cell could not be worked out. Busiest cell:
          {{
            max
          }}.
        </caption>
        <thead>
          <tr>
            <th scope="col" class="w-24 text-left font-medium text-ink-muted">Day</th>
            <th
              v-for="h in HOURS"
              :key="h"
              scope="col"
              colspan="2"
              class="text-left font-normal text-ink-muted"
            >
              <span class="sr-only">{{ slotLabel(h * 2) }}</span>
              <span aria-hidden="true">{{ h % 3 === 0 ? String(h).padStart(2, '0') : '' }}</span>
            </th>
          </tr>
        </thead>
        <tbody data-testid="heat-grid">
          <tr v-for="d in days" :key="d.day">
            <th scope="row" class="text-left font-normal">
              <button
                type="button"
                class="whitespace-nowrap text-brand-ink underline"
                @click="emit('open', d.day)"
              >
                {{ formatDayLabel(d.day) }}
              </button>
            </th>
            <td
              v-if="!d.hasForecast || !d.requiredBySlot"
              colspan="48"
              class="rounded bg-surface-muted px-2 py-0.5 text-ink-muted"
            >
              No forecast
            </td>
            <template v-else>
              <td
                v-for="s in SLOTS"
                :key="s"
                class="h-5 min-w-2.5 p-0"
                :title="`${formatDayLabel(d.day)} ${slotLabel(s)}: ${d.requiredBySlot[s] ?? 'unknown'}`"
                :data-level="d.requiredBySlot[s] ?? 'unknown'"
              >
                <div
                  v-if="d.requiredBySlot[s] === null"
                  class="h-5 rounded-sm border border-dashed border-ink-muted"
                />
                <div
                  v-else
                  class="h-5 rounded-sm"
                  :class="d.requiredBySlot[s] === 0 ? 'bg-surface-muted' : 'bg-brand'"
                  :style="style(d.requiredBySlot[s] ?? null)"
                />
                <span class="sr-only">{{ d.requiredBySlot[s] ?? 'unknown' }}</span>
              </td>
            </template>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
