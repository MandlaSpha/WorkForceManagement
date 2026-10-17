<script setup lang="ts">
import { computed, ref } from 'vue'

import { usePeaks } from '@/entities/peaks'
import { useContextStore } from '@/features/context-filters'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const context = useContextStore()
const screen = NAV_ITEMS.find((item) => item.key === 'peaks')

const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' })
const from = ref(new Date(Date.parse(today) - 27 * 86_400_000).toISOString().slice(0, 10))
const to = ref(today)
const peaks = usePeaks(
  computed(() => context.queueNumber),
  from,
  to,
)
</script>

<template>
  <PageHeader
    eyebrow="Insight"
    :title="screen?.label ?? 'Peaks & troughs'"
    :subtitle="screen?.subtitle"
  />

  <section class="space-y-4" aria-live="polite">
    <div class="flex flex-wrap gap-4 text-sm text-ink">
      <label class="flex items-center gap-2">
        From
        <input
          v-model="from"
          type="date"
          class="rounded-lg border border-line bg-surface px-2 py-1"
        />
      </label>
      <label class="flex items-center gap-2">
        To
        <input
          v-model="to"
          type="date"
          class="rounded-lg border border-line bg-surface px-2 py-1"
        />
      </label>
    </div>

    <NoticeBox v-if="context.queueNumber === null">
      Choose a queue at the top of the page. Queues appear once call data has been imported.
    </NoticeBox>
    <NoticeBox v-else-if="from > to" tone="warn">The start date is after the end date.</NoticeBox>
    <p v-else-if="peaks.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="peaks.isError.value" tone="danger" data-testid="peaks-error">
      Could not work out peaks. {{ problemMessage(peaks.error.value) }}
    </NoticeBox>

    <template v-else-if="peaks.data.value">
      <NoticeBox v-if="peaks.data.value.daysMeasured === 0" data-testid="peaks-none">
        No calls were measured in that range, so there is nothing to rank.
      </NoticeBox>
      <div v-else class="grid gap-6 md:grid-cols-2">
        <section aria-labelledby="busy-days">
          <h2 id="busy-days" class="text-sm font-semibold text-ink">Busiest days</h2>
          <ol class="mt-2 space-y-1 text-sm" data-testid="busiest-days">
            <li v-for="d in peaks.data.value.busiestDays" :key="d.day">
              {{ d.day }}: {{ d.offered }} calls
            </li>
          </ol>
        </section>
        <section aria-labelledby="quiet-days">
          <h2 id="quiet-days" class="text-sm font-semibold text-ink">Quietest days</h2>
          <ol class="mt-2 space-y-1 text-sm" data-testid="quietest-days">
            <li v-for="d in peaks.data.value.quietestDays" :key="d.day">
              {{ d.day }}: {{ d.offered }} calls
            </li>
          </ol>
        </section>
        <section aria-labelledby="busy-slots">
          <h2 id="busy-slots" class="text-sm font-semibold text-ink">
            Busiest half-hours (average a day)
          </h2>
          <ol class="mt-2 space-y-1 text-sm" data-testid="busiest-slots">
            <li v-for="s in peaks.data.value.busiestSlots" :key="s.slot">
              {{ s.slot }}: {{ s.averageOffered }} calls over {{ s.days }} days
            </li>
          </ol>
        </section>
        <section aria-labelledby="quiet-slots">
          <h2 id="quiet-slots" class="text-sm font-semibold text-ink">
            Quietest half-hours while open (average a day)
          </h2>
          <ol class="mt-2 space-y-1 text-sm" data-testid="quietest-slots">
            <li v-for="s in peaks.data.value.quietestSlots" :key="s.slot">
              {{ s.slot }}: {{ s.averageOffered }} calls over {{ s.days }} days
            </li>
          </ol>
        </section>
        <section aria-labelledby="busy-intervals" class="md:col-span-2">
          <h2 id="busy-intervals" class="text-sm font-semibold text-ink">
            Single busiest half-hours
          </h2>
          <ol class="mt-2 space-y-1 text-sm" data-testid="busiest-intervals">
            <li v-for="i in peaks.data.value.busiestIntervals" :key="i.start">
              {{ i.start }}: {{ i.offered }} calls
            </li>
          </ol>
        </section>
      </div>
    </template>
  </section>
</template>
