<script setup lang="ts">
import { computed } from 'vue'

import { usePlan, useRecommendations } from '@/entities/scheduling'
import { useContextStore } from '@/features/context-filters'
import { ApplyRecommendationButton } from '@/features/optimise/recommendation'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const context = useContextStore()
const screen = NAV_ITEMS.find((item) => item.key === 'recommendations')

const queueId = computed(() => context.queueNumber)
const week = computed(() => context.weekStart)
const recommendations = useRecommendations(queueId, week)
const plan = usePlan(queueId, week)
const gap = computed(() => plan.data.value?.summary.gap)
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
      <p v-if="gap !== undefined" class="text-sm text-ink" data-testid="rec-gap">
        Half-hours short this week: <strong>{{ gap }}</strong>
      </p>
      <NoticeBox v-if="(recommendations.data.value ?? []).length === 0" data-testid="rec-none">
        Nothing to suggest. Either nothing is short, or nobody free can fill a gap without breaking
        a roster rule.
      </NoticeBox>
      <ol v-else class="space-y-2" aria-label="Recommendations">
        <li
          v-for="(r, index) in recommendations.data.value"
          :key="`${r.kind}-${r.employeeId}-${r.day}-${r.templateId}`"
          class="flex items-center justify-between gap-4 rounded-xl border border-line bg-surface p-4"
          :data-testid="`rec-${index}`"
        >
          <div>
            <p class="text-sm font-medium text-ink">{{ r.text }}</p>
            <p v-if="r.addsOver > 0" class="text-xs text-ink-muted">
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
