<script setup lang="ts">
import { computed, ref } from 'vue'

import { useShrinkage } from '@/entities/shrinkage'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'shrinkage')

const thisMonth = new Date()
  .toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' })
  .slice(0, 7)
const month = ref(thisMonth)
const shrinkage = useShrinkage(computed(() => `${month.value}-01`))

// Decimals arrive as strings; a missing share is a dash, never 0%.
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
      <NoticeBox data-testid="unplanned-note">
        Only planned shrinkage is measured, from approved leave. Unplanned shrinkage (absence,
        lateness) needs an attendance feed and is not guessed. The assumed figure is the planning
        assumption of the queues the team works, planned and unplanned together.
      </NoticeBox>
      <NoticeBox v-if="shrinkage.data.value.teams.length === 0" data-testid="shrinkage-none">
        Nobody is in your view for that month.
      </NoticeBox>
      <table v-else class="w-full text-left text-sm" aria-label="Planned shrinkage by team">
        <thead class="text-ink-muted">
          <tr>
            <th scope="col" class="py-2">Team</th>
            <th scope="col">People</th>
            <th scope="col">Contracted hours</th>
            <th scope="col">Hours on leave</th>
            <th scope="col">Planned shrinkage</th>
            <th scope="col">Assumed (all kinds)</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="t in shrinkage.data.value.teams"
            :key="t.team"
            class="border-t border-line"
            :data-testid="`team-${t.team}`"
          >
            <th scope="row" class="py-2 font-medium">{{ t.team }}</th>
            <td>{{ t.people }}</td>
            <td>{{ t.contractedHours }}</td>
            <td>{{ t.awayHours }}</td>
            <td data-testid="planned">{{ pct(t.plannedPct) }}</td>
            <td>{{ pct(t.assumedPct) }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </section>
</template>
