<script setup lang="ts">
import { computed } from 'vue'

import { useImpact } from '@/entities/leave'

/** The effect on coverage a waiting request would have: the same figures the approval screen's
 * impact panel shows, in one chip. */
const props = defineProps<{ requestId: number }>()
const impact = useImpact(props.requestId, true)

const chip = computed(() => {
  const i = impact.data.value
  if (impact.isError.value)
    return { text: 'Effect unknown', tone: 'bg-surface-muted text-ink-muted' }
  if (!i) return { text: 'Working out the effect…', tone: 'bg-surface-muted text-ink-muted' }
  if (i.shifts === 0) return { text: 'No roster change', tone: 'bg-brand-soft text-brand-ink' }
  if (i.newlyUnder > 0) {
    return { text: `${i.newlyUnder} half-hours would be short`, tone: 'bg-danger-soft text-danger' }
  }
  return { text: 'Coverage holds', tone: 'bg-brand-soft text-brand-ink' }
})
</script>

<template>
  <span
    class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
    :class="chip.tone"
    data-testid="coverage-chip"
    >{{ chip.text }}</span
  >
</template>
