<script setup lang="ts">
import { computed } from 'vue'

import { useScorecard } from '@/entities/scorecard'
import IntervalChart from '@/shared/ui/IntervalChart.vue'

const props = defineProps<{ month: string; periodLabel: string }>()

// The scorecard takes any range, so the month is its first to its last day.
const from = computed(() => `${props.month}-01`)
const to = computed(() => {
  const [year, mon] = props.month.split('-').map(Number)
  const last = new Date(year ?? 1970, mon ?? 1, 0).getDate()
  return `${props.month}-${String(last).padStart(2, '0')}`
})
const card = useScorecard(from, to)

const points = computed(() =>
  (card.data.value?.days ?? []).map((d) => ({
    label: String(Number(d.day.slice(8))),
    bars: d.offered,
    line: d.serviceLevelPct === null ? null : Math.round(d.serviceLevelPct),
  })),
)
const hasCalls = computed(() => points.value.some((p) => (p.bars ?? 0) > 0))
</script>

<template>
  <section
    v-if="hasCalls"
    class="rounded-2xl border border-line bg-surface p-4 shadow-[var(--shadow-card)]"
    aria-labelledby="trend-title"
    data-testid="service-trend"
  >
    <h2 id="trend-title" class="text-base font-semibold text-ink">
      Calls and service level, {{ periodLabel }}
    </h2>
    <IntervalChart
      :points="points"
      :summary="`Calls offered each day and the service level, ${periodLabel}.`"
      bar-label="Calls offered"
      line-label="Service level %"
      :label-every="5"
      category-label="Day"
    />
  </section>
</template>
