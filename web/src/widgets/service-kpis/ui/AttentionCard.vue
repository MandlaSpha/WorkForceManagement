<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { formatPercent, type QueueKpis } from '@/entities/call-data'
import { useContracts } from '@/entities/contract'

const props = defineProps<{ queues: ReadonlyArray<QueueKpis> }>()

const contracts = useContracts()
const atRisk = computed(() => (contracts.data.value ?? []).filter((c) => c.active && c.atRisk))

// The queue furthest below the others: only queues with a measured figure can be compared.
const weakest = computed(() => {
  const known = props.queues.filter((q) => q.offered > 0 && q.serviceLevelPct.value !== null)
  return known.reduce<QueueKpis | null>(
    (worst, q) =>
      worst === null || (q.serviceLevelPct.value ?? 0) < (worst.serviceLevelPct.value ?? 0)
        ? q
        : worst,
    null,
  )
})
</script>

<template>
  <section
    class="h-full rounded-2xl border border-line bg-surface p-4 shadow-[var(--shadow-card)]"
    aria-labelledby="attention-title"
    data-testid="attention-card"
  >
    <h2 id="attention-title" class="text-base font-semibold text-ink">Needs attention</h2>

    <div v-if="weakest" class="mt-3 rounded-xl bg-warn-soft p-3">
      <p class="text-xs text-ink-muted">Lowest service level</p>
      <p class="text-2xl font-semibold tabular-nums text-ink">
        {{ formatPercent(weakest.serviceLevelPct.value, 1) }}
      </p>
      <p class="text-xs text-ink-muted">{{ weakest.queue }}</p>
    </div>

    <h3 class="mt-4 text-sm font-semibold text-ink">
      Contracts at risk
      <span class="ml-1 tabular-nums text-ink-muted" data-testid="risk-count">{{
        atRisk.length
      }}</span>
    </h3>
    <p v-if="atRisk.length === 0" class="mt-1 text-sm text-ink-muted">None at risk.</p>
    <ul v-else class="mt-2 divide-y divide-line">
      <li
        v-for="c in atRisk.slice(0, 5)"
        :key="c.id"
        class="flex items-center justify-between gap-3 py-2 text-sm"
      >
        <span class="min-w-0">
          <span class="block truncate font-medium text-ink">{{ c.name }}</span>
          <span class="block truncate text-xs text-ink-muted">{{ c.customer }}</span>
        </span>
        <span class="shrink-0 tabular-nums text-danger">
          {{ c.measuredSlPct === null ? 'n/a' : `${c.measuredSlPct.toFixed(1)}%` }}
          <span class="text-ink-muted">of {{ c.slTargetPct }}%</span>
        </span>
      </li>
    </ul>
    <RouterLink to="/contracts" class="mt-3 inline-block text-sm font-medium text-brand-ink">
      All contracts
    </RouterLink>
  </section>
</template>
