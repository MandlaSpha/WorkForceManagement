<script setup lang="ts">
import { computed } from 'vue'

import { usePlan, useRecommendations } from '@/entities/scheduling'
import { useContextStore } from '@/features/context-filters'
import { ApplyRecommendationButton } from '@/features/optimise/recommendation'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import { formatDayLabel } from '@/shared/lib/datetime'
import PageHeader from '@/shared/ui/PageHeader.vue'
import StatTile from '@/shared/ui/StatTile.vue'

const context = useContextStore()
const screen = NAV_ITEMS.find((item) => item.key === 'recommendations')

const queueId = computed(() => context.queueNumber)
const week = computed(() => context.weekStart)
const recommendations = useRecommendations(queueId, week)
const plan = usePlan(queueId, week)
const gap = computed(() => plan.data.value?.summary.gap)
const list = computed(() => recommendations.data.value ?? [])
// Fixes overlap, so they are not added up: the tile says what the best single one does.
const best = computed(() => list.value.reduce((most, r) => Math.max(most, r.closes), 0))
</script>

<template>
  <PageHeader
    eyebrow="Operate"
    :title="screen?.label ?? 'Recommendations'"
    :subtitle="screen?.subtitle"
  />

  <section class="space-y-4" aria-live="polite">
    <NoticeBox v-if="context.queueNumber === null">
      Choose a queue at the top of the page. Queues appear once call data has been imported.
    </NoticeBox>
    <p v-else-if="recommendations.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="recommendations.isError.value" tone="danger" data-testid="rec-error">
      Could not work out recommendations. {{ problemMessage(recommendations.error.value) }}
    </NoticeBox>

    <template v-else>
      <ul class="grid gap-3 sm:grid-cols-3" aria-label="Summary">
        <StatTile
          v-if="gap !== undefined"
          label="Half-hours short this week"
          :value="gap"
          tint="danger"
          data-testid="rec-gap"
        />
        <StatTile label="Suggestions" :value="list.length" tint="brand" data-testid="rec-count" />
        <StatTile label="Best single fix" :value="best" tint="ok" data-testid="rec-best">
          half-hours closed
        </StatTile>
      </ul>

      <NoticeBox v-if="list.length === 0" data-testid="rec-none">
        Nothing to suggest. Either nothing is short, or nobody free can fill a gap without breaking
        a roster rule.
      </NoticeBox>
      <ol v-else class="grid gap-3 lg:grid-cols-2" aria-label="Recommendations">
        <li
          v-for="(r, index) in list"
          :key="`${r.kind}-${r.employeeId}-${r.day}-${r.templateId}`"
          class="flex items-start gap-3 rounded-2xl border border-line bg-surface p-4 shadow-[var(--shadow-card)]"
          :data-testid="`rec-${index}`"
        >
          <span
            class="grid size-8 shrink-0 place-items-center rounded-full bg-brand-soft text-sm font-semibold text-brand-ink"
            aria-hidden="true"
          >
            {{ index + 1 }}
          </span>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-1.5 text-[11px] font-semibold">
              <span class="rounded-full bg-brand-soft px-2 py-0.5 text-brand-ink">
                {{ r.kind === 'change' ? 'Change shift' : 'Add to shift' }}
              </span>
              <span class="rounded-full bg-surface-muted px-2 py-0.5 text-ink">
                {{ formatDayLabel(r.day) }}
              </span>
              <span class="rounded-full bg-ok-soft px-2 py-0.5 text-ok">
                closes {{ r.closes }}
              </span>
            </div>
            <p class="mt-2 text-sm font-medium text-ink">{{ r.text }}</p>
            <p v-if="r.addsOver > 0" class="mt-1 text-xs text-ink-muted">
              {{ r.addsOver }} half-hours would then have one person too many.
            </p>
          </div>
          <ApplyRecommendationButton
            v-if="context.queueNumber !== null"
            :queue-id="context.queueNumber"
            :week-start="context.weekStart"
            :recommendation="r"
          />
        </li>
      </ol>
    </template>
  </section>
</template>
