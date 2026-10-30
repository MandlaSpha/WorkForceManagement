<script setup lang="ts">
import { computed, ref } from 'vue'

import { useShrinkage } from '@/entities/shrinkage'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import StatTile from '@/shared/ui/StatTile.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'shrinkage')

const thisMonth = new Date()
  .toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' })
  .slice(0, 7)
const month = ref(thisMonth)
const shrinkage = useShrinkage(computed(() => `${month.value}-01`))

// Decimals arrive as strings; a missing share is a dash, never 0%.
const teams = computed(() => shrinkage.data.value?.teams ?? [])
const people = computed(() => teams.value.reduce((sum, t) => sum + t.people, 0))
const contracted = computed(() =>
  teams.value.reduce((sum, t) => sum + Number(t.contractedHours), 0),
)
const away = computed(() => teams.value.reduce((sum, t) => sum + Number(t.awayHours), 0))
const plannedAll = computed(() =>
  contracted.value > 0 ? (away.value / contracted.value) * 100 : null,
)
// The planning assumption is the same for the teams that have one: show the first.
const assumed = computed(() => {
  const found = teams.value.find((t) => t.assumedPct != null)
  return found?.assumedPct == null ? null : Number(found.assumedPct)
})
const bar = (value: string | null | undefined, top: number): string =>
  `${Math.min(100, Math.max(0, ((value == null ? 0 : Number(value)) / top) * 100))}%`
const TOP = computed(() =>
  Math.max(
    10,
    ...teams.value.flatMap((t) => [Number(t.plannedPct ?? 0), Number(t.assumedPct ?? 0)]),
  ),
)
const pct = (value: string | null | undefined) =>
  value == null ? '-' : `${Number(value).toFixed(1)}%`
</script>

<template>
  <PageHeader eyebrow="People" :title="screen?.label ?? 'Shrinkage'" :subtitle="screen?.subtitle" />

  <section class="space-y-4" aria-live="polite">
    <label class="flex items-center gap-2 text-sm text-ink">
      Month
      <input
        v-model="month"
        type="month"
        class="rounded-lg border border-line bg-surface px-2 py-1"
      />
    </label>

    <p v-if="shrinkage.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="shrinkage.isError.value" tone="danger" data-testid="shrinkage-error">
      Could not work out shrinkage. {{ problemMessage(shrinkage.error.value) }}
    </NoticeBox>

    <template v-else-if="shrinkage.data.value">
      <NoticeBox v-if="shrinkage.data.value.teams.length === 0" data-testid="shrinkage-none">
        Nobody is in your view for that month.
      </NoticeBox>
      <template v-else>
        <ul class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Shrinkage this month">
          <StatTile
            label="Planned shrinkage"
            :value="plannedAll ?? '-'"
            :format="(n) => `${n.toFixed(1)}%`"
            tint="brand"
            data-testid="total-planned"
          >
            from approved leave
          </StatTile>
          <StatTile
            label="Assumed, all kinds"
            :value="assumed ?? '-'"
            :format="(n) => `${n.toFixed(1)}%`"
            tint="warn"
            data-testid="total-assumed"
          >
            what the queues plan for
          </StatTile>
          <StatTile
            label="Hours on leave"
            :value="away"
            :format="(n) => n.toLocaleString('en-ZA', { maximumFractionDigits: 1 })"
            tint="ok"
          >
            of {{ contracted.toLocaleString('en-ZA', { maximumFractionDigits: 0 }) }} contracted
          </StatTile>
          <StatTile label="People" :value="people" tint="danger" />
        </ul>

        <ul class="grid gap-3 lg:grid-cols-2" aria-label="Planned shrinkage by team">
          <li
            v-for="t in shrinkage.data.value.teams"
            :key="t.team"
            class="rounded-2xl border border-line bg-surface p-4 shadow-[var(--shadow-card)]"
            :data-testid="`team-${t.team}`"
          >
            <div class="flex items-baseline justify-between gap-3">
              <h2 class="truncate text-base font-semibold text-ink">{{ t.team }}</h2>
              <span class="shrink-0 text-xs text-ink-muted">
                {{ t.people }} people · {{ t.contractedHours }} h contracted
              </span>
            </div>
            <div class="mt-3 flex items-baseline justify-between text-sm">
              <span class="font-semibold tabular-nums text-ink" data-testid="planned">
                {{ pct(t.plannedPct) }}
              </span>
              <span class="tabular-nums text-ink-muted">
                {{ t.awayHours }} h on leave · assumed {{ pct(t.assumedPct) }}
              </span>
            </div>
            <div
              class="relative mt-2 h-2 rounded-full bg-surface-muted"
              role="img"
              :aria-label="`Planned ${pct(t.plannedPct)} against ${pct(t.assumedPct)} assumed`"
            >
              <div
                class="h-full rounded-full bg-brand"
                :style="{ width: bar(t.plannedPct, TOP) }"
              ></div>
              <div
                v-if="t.assumedPct != null"
                class="absolute -top-1 h-4 w-0.5 rounded bg-ink"
                :style="{ left: bar(t.assumedPct, TOP) }"
                aria-hidden="true"
              ></div>
            </div>
          </li>
        </ul>
      </template>
    </template>
  </section>
</template>
