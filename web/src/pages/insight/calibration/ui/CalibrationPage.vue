<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { biasLabel, pctLabel, useBacktest, useTuning, verdict } from '@/entities/forecast'
import type { TuningTrial } from '@/entities/forecast'
import { useSessionStore } from '@/entities/session'
import { useContextStore } from '@/features/context-filters'
import { useSaveTuning } from '@/features/save-tuning'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import TextField from '@/shared/ui/TextField.vue'

const session = useSessionStore()
const context = useContextStore()
const screen = NAV_ITEMS.find((item) => item.key === 'calibration')
// Cosmetic: the API refuses saving for any other role.
const canSave = computed(() => ['planner', 'admin'].includes(session.user?.role ?? ''))

const queueId = computed(() => context.queueNumber)
const tuning = useTuning(queueId)

// The form starts from what is saved. What has been tried is kept apart from what is typed, so a
// back-test only runs when asked for, and says which settings it scored.
const weeks = ref('4')
const decay = ref('0.7')
const volume = ref('1')
const aht = ref('1')
const tried = ref<TuningTrial>({})

watch(
  () => tuning.data.value,
  (saved) => {
    if (!saved) return
    weeks.value = String(saved.weeks)
    decay.value = String(saved.decay)
    volume.value = String(saved.volumeMultiplier)
    aht.value = String(saved.ahtMultiplier)
    tried.value = {}
  },
  { immediate: true },
)

const backtest = useBacktest(queueId, tried)
const save = useSaveTuning()

const typed = computed(() => ({
  weeks: Number(weeks.value),
  decay: Number(decay.value),
  volumeMultiplier: Number(volume.value),
  ahtMultiplier: Number(aht.value),
}))

function tryIt(): void {
  tried.value = { ...typed.value }
}

function saveIt(): void {
  if (queueId.value === null) return
  save.mutate({ queueId: queueId.value, ...typed.value })
}

function useSuggestion(multiplier: number): void {
  volume.value = String(multiplier)
  tryIt()
}

const result = computed(() => backtest.data.value)
const better = computed(() =>
  result.value ? verdict(result.value.candidate, result.value.current) : 'unknown',
)
const direction = computed(() => ((result.value?.candidate.biasPct ?? 0) > 0 ? 'high' : 'low'))
const nothingToScore = computed(
  () => result.value !== undefined && result.value.candidate.days === 0,
)
</script>

<template>
  <PageHeader
    eyebrow="Insight"
    :title="screen?.label ?? 'Calibration'"
    :subtitle="screen?.subtitle"
  />

  <section class="space-y-6" aria-live="polite">
    <NoticeBox v-if="queueId === null">
      Choose a queue at the top of the page. Queues appear once call data has been imported.
    </NoticeBox>
    <p v-else-if="tuning.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="tuning.isError.value" tone="danger">
      Could not load the tuning. {{ problemMessage(tuning.error.value) }}
    </NoticeBox>

    <template v-else-if="tuning.data.value">
      <form
        class="space-y-4 rounded-xl border border-line bg-surface p-4"
        aria-label="Forecast tuning"
        @submit.prevent="tryIt"
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-base font-semibold text-ink">
            {{ tuning.data.value.queue }}: forecast tuning
          </h2>
          <span
            class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
            :class="
              tuning.data.value.saved ? 'bg-brand-soft text-brand-ink' : 'bg-warn-soft text-warn'
            "
            data-testid="tuning-state"
          >
            {{ tuning.data.value.saved ? 'Saved' : 'Defaults, nobody has saved a tuning' }}
          </span>
        </div>
        <p class="text-sm text-ink-muted">
          Change the settings, back-test them against what really happened, and save the ones that
          do better. Forecasts already run are not changed.
        </p>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <TextField v-model="weeks" type="number" label="Look back (weeks)" :min="1" :max="12" />
          <TextField
            v-model="decay"
            type="number"
            label="Recency weight (0.1 to 1)"
            :min="0.1"
            :max="1"
            :step="0.05"
          />
          <TextField
            v-model="volume"
            type="number"
            label="Contacts multiplier"
            :min="0.5"
            :max="2"
            :step="0.01"
          />
          <TextField
            v-model="aht"
            type="number"
            label="Handling-time multiplier"
            :min="0.5"
            :max="2"
            :step="0.01"
          />
        </div>
        <p class="text-xs text-ink-muted">
          Recency weight: how much less each older same-weekday day counts (1 counts them all
          alike). Multipliers correct a forecast that runs high or low.
        </p>
        <div class="flex flex-wrap items-center gap-2">
          <AppButton type="submit" :loading="backtest.isFetching.value"
            >Back-test these settings</AppButton
          >
          <AppButton
            v-if="canSave"
            type="button"
            variant="secondary"
            :loading="save.isPending.value"
            @click="saveIt"
          >
            Save as this queue's tuning
          </AppButton>
        </div>
        <NoticeBox v-if="save.isError.value" tone="danger" data-testid="tuning-error">
          <p class="font-medium">The tuning was not saved.</p>
          <p>{{ problemMessage(save.error.value) }}</p>
        </NoticeBox>
        <NoticeBox v-if="backtest.isError.value" tone="danger" data-testid="backtest-error">
          <p class="font-medium">The back-test could not be worked out.</p>
          <p>{{ problemMessage(backtest.error.value) }}</p>
        </NoticeBox>
      </form>

      <div v-if="result" class="space-y-3" data-testid="backtest">
        <NoticeBox v-if="nothingToScore" data-testid="nothing-to-score">
          There are no past days to score these settings against: a forecast needs at least one
          earlier day with the same weekday. Import more call data.
        </NoticeBox>
        <template v-else>
          <div class="overflow-x-auto rounded-xl border border-line bg-surface">
            <table class="w-full min-w-[30rem] text-left text-sm">
              <caption class="px-4 py-3 text-left text-sm font-semibold text-ink">
                Back-test on
                {{
                  result.candidate.days
                }}
                past days
                <span class="block text-xs font-normal text-ink-muted">
                  Each day forecast from only the days before it, then scored against what happened.
                </span>
              </caption>
              <thead class="border-y border-line bg-surface-muted text-xs text-ink-muted">
                <tr>
                  <th scope="col" class="px-4 py-2 font-medium">Measure</th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">These settings</th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">Saved now</th>
                </tr>
              </thead>
              <tbody>
                <tr class="border-b border-line">
                  <th scope="row" class="px-4 py-2 font-medium">Day totals right</th>
                  <td class="px-3 py-2 text-right tabular-nums" data-testid="daily-candidate">
                    {{ pctLabel(result.candidate.dailyPct) }}
                  </td>
                  <td class="px-3 py-2 text-right tabular-nums" data-testid="daily-current">
                    {{ pctLabel(result.current.dailyPct) }}
                  </td>
                </tr>
                <tr class="border-b border-line">
                  <th scope="row" class="px-4 py-2 font-medium">Half-hours right</th>
                  <td class="px-3 py-2 text-right tabular-nums">
                    {{ pctLabel(result.candidate.intervalPct) }}
                  </td>
                  <td class="px-3 py-2 text-right tabular-nums">
                    {{ pctLabel(result.current.intervalPct) }}
                  </td>
                </tr>
                <tr class="border-b border-line">
                  <th scope="row" class="px-4 py-2 font-medium">Bias</th>
                  <td class="px-3 py-2 text-right tabular-nums" data-testid="bias-candidate">
                    {{ biasLabel(result.candidate.biasPct) }}
                  </td>
                  <td class="px-3 py-2 text-right tabular-nums" data-testid="bias-current">
                    {{ biasLabel(result.current.biasPct) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <p class="text-sm" data-testid="verdict">
            <template v-if="better === 'better'">
              These settings predict day totals better than the saved ones.
            </template>
            <template v-else-if="better === 'worse'">
              These settings predict day totals worse than the saved ones.
            </template>
            <template v-else-if="better === 'same'">
              These settings do about the same as the saved ones.
            </template>
          </p>

          <NoticeBox v-if="result.suggestedVolumeMultiplier !== null" data-testid="suggestion">
            With these settings the forecasts ran {{ direction }}. A contacts multiplier of
            {{ result.suggestedVolumeMultiplier }} would remove that.
            <button
              type="button"
              class="ml-1 font-medium text-brand-ink underline"
              @click="useSuggestion(result.suggestedVolumeMultiplier)"
            >
              Use {{ result.suggestedVolumeMultiplier }} and back-test
            </button>
          </NoticeBox>
        </template>
      </div>
    </template>
  </section>
</template>
