<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { useOverview } from '@/entities/scheduling'
import { todayInJohannesburg, weekStartOf } from '@/shared/lib/week'

// This week's coverage from the planning overview the dashboard already loads. Nothing is drawn
// while it loads, when it fails, or when no queue has a forecast to compare against.
const overview = useOverview(weekStartOf(todayInJohannesburg()))

const figures = computed(() => {
  const totals = overview.data.value?.totals
  if (!totals || totals.intervalsKnown <= 0) return null
  const covered = Math.max(0, totals.intervalsKnown - totals.underIntervals)
  return {
    covered,
    known: totals.intervalsKnown,
    pct: Math.round((covered / totals.intervalsKnown) * 100),
  }
})
</script>

<template>
  <RouterLink
    v-if="figures"
    to="/planner"
    class="block rounded-2xl bg-side-hover p-3 hover:bg-side-line"
    data-testid="coverage-card"
  >
    <span class="flex items-baseline justify-between text-on-side">
      <span class="text-xs font-semibold">Coverage this week</span>
      <span class="text-sm font-semibold tabular-nums">{{ figures.pct }}%</span>
    </span>
    <span
      class="mt-2 block h-1.5 overflow-hidden rounded-full bg-side-line"
      role="progressbar"
      aria-label="Coverage this week"
      :aria-valuenow="figures.pct"
      aria-valuemin="0"
      aria-valuemax="100"
    >
      <span
        class="coverage-fill block h-full rounded-full bg-side-pill"
        :style="{ width: `${figures.pct}%` }"
      />
    </span>
    <span class="mt-1.5 block text-[11px] text-side-dim">
      {{ figures.covered }} of {{ figures.known }} half-hours covered
    </span>
  </RouterLink>
</template>

<style scoped>
.coverage-fill {
  transition: width 700ms ease-out;
  animation: coverage-grow 700ms ease-out;
}
@keyframes coverage-grow {
  from {
    width: 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .coverage-fill {
    transition: none;
    animation: none;
  }
}
</style>
