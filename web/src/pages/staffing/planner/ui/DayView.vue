<script setup lang="ts">
import { computed } from 'vue'

import { slotLabel, type Plan } from '@/entities/scheduling'
import { formatDayLabel } from '@/shared/lib/datetime'
import IntervalChart from '@/shared/ui/IntervalChart.vue'

const props = defineProps<{ plan: Plan; day: string }>()

const cells = computed(() => props.plan.cells[props.day] ?? [])
const points = computed(() =>
  cells.value.map((c) => ({ label: slotLabel(c.slot), bars: c.scheduled, line: c.required })),
)
const under = computed(() => cells.value.filter((c) => c.state === 'under').length)
const known = computed(() => cells.value.filter((c) => c.required !== null).length)
const summary = computed(
  () =>
    `People scheduled per half-hour and agents required, ${formatDayLabel(props.day)}. ` +
    (known.value === 0
      ? 'No requirement is known for this day.'
      : `${under.value} of ${known.value} half-hours are under-staffed.`),
)
</script>

<template>
  <section class="space-y-3" aria-labelledby="day-title">
    <h2 id="day-title" class="text-base font-semibold text-ink">{{ formatDayLabel(day) }}</h2>
    <IntervalChart
      :points="points"
      :summary="summary"
      bar-label="People scheduled"
      line-label="Agents required"
    />
  </section>
</template>
