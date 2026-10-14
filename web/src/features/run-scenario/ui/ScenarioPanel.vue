<script setup lang="ts">
import { computed, ref } from 'vue'

import { deltaLabel, totalsOf, type ForecastVersion } from '@/entities/forecast'
import { problemMessage } from '@/shared/api'
import { formatDayLabel } from '@/shared/lib/datetime'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useRunScenario } from '../model/useRunScenario'

const props = defineProps<{ version: ForecastVersion }>()

const calls = ref('0')
const handling = ref('0')
// Blank keeps what the forecast was run with.
const shrinkage = ref('')
const target = ref('')

const run = useRunScenario()

function submit(): void {
  run.mutate({
    versionId: props.version.id,
    volumeChangePct: Number(calls.value || 0),
    ahtChangePct: Number(handling.value || 0),
    shrinkagePct: shrinkage.value.trim() === '' ? null : Number(shrinkage.value),
    slTargetPct: target.value.trim() === '' ? null : Number(target.value),
  })
}

const result = computed(() => run.data.value)
const totals = computed(() => (result.value ? totalsOf(result.value.days) : null))
const fixed = (value: number, digits = 0): string => value.toFixed(digits)
</script>

<template>
  <section class="space-y-3" aria-labelledby="scenario-title">
    <h2 id="scenario-title" class="text-base font-semibold text-ink">What if&hellip;</h2>
    <p class="text-sm text-ink-muted">
      See what a change would do to the agents needed, without changing this forecast. Nothing is
      saved.
    </p>

    <form class="space-y-3" aria-label="What if" @submit.prevent="submit">
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <TextField
          v-model="calls"
          type="number"
          label="Change in calls (%)"
          :min="-100"
          :max="500"
        />
        <TextField
          v-model="handling"
          type="number"
          label="Change in handling time (%)"
          :min="-90"
          :max="500"
        />
        <TextField
          v-model="shrinkage"
          type="number"
          label="Shrinkage (%), blank keeps the forecast's"
          :min="0"
          :max="99"
        />
        <TextField
          v-model="target"
          type="number"
          label="Service-level target (%), blank keeps the forecast's"
          :min="1"
          :max="100"
        />
      </div>
      <AppButton type="submit" :loading="run.isPending.value">Show what changes</AppButton>
      <NoticeBox v-if="run.isError.value" tone="danger" data-testid="scenario-error">
        <p class="font-medium">The scenario could not be worked out.</p>
        <p>{{ problemMessage(run.error.value) }}</p>
      </NoticeBox>
    </form>

    <template v-if="result && totals">
      <p class="text-sm text-ink-muted" data-testid="scenario-assumptions">
        Shrinkage {{ result.base.shrinkagePct }}% to {{ result.scenario.shrinkagePct }}%, service
        level target {{ result.base.slTargetPct }}% to {{ result.scenario.slTargetPct }}% in
        {{ result.scenario.slThresholdS }} s.
      </p>
      <NoticeBox v-if="!totals.complete" data-testid="scenario-minimum">
        Some half-hours have calls but no known handling time, so they could not be staffed. The
        figures marked with an asterisk are at least this much.
      </NoticeBox>
      <div class="overflow-x-auto rounded-xl border border-line bg-surface">
        <table class="w-full min-w-[40rem] text-left text-sm" data-testid="scenario-table">
          <caption class="sr-only">
            What changes, day by day
          </caption>
          <thead class="border-b border-line bg-surface-muted text-xs text-ink-muted">
            <tr>
              <th scope="col" class="px-4 py-2 font-medium">Day</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Calls</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Most agents at once</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Agent-hours</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="d in result.days"
              :key="d.day"
              class="border-b border-line"
              :data-testid="`scenario-${d.day}`"
            >
              <th scope="row" class="px-4 py-2 font-medium text-ink">
                {{ formatDayLabel(d.day) }}
              </th>
              <td class="px-3 py-2 text-right tabular-nums" data-col="calls">
                {{ fixed(d.callsBase) }} to {{ fixed(d.callsScenario) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="peak">
                {{ d.peakBase ?? '\u2014' }} to {{ d.peakScenario ?? '\u2014'
                }}{{ d.complete ? '' : '*' }}
                <span class="text-ink-muted">({{ deltaLabel(d.peakBase, d.peakScenario) }})</span>
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="hours">
                {{ fixed(d.hoursBase, 1) }} to {{ fixed(d.hoursScenario, 1) }}
                <span class="text-ink-muted"
                  >({{ deltaLabel(d.hoursBase, d.hoursScenario, 1) }})</span
                >
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="font-semibold text-ink" data-testid="scenario-total">
              <th scope="row" class="px-4 py-2">All days</th>
              <td class="px-3 py-2 text-right tabular-nums" data-col="calls">
                {{ fixed(totals.callsBase) }} to {{ fixed(totals.callsScenario) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="peak">
                {{ totals.peakBase ?? '\u2014' }} to {{ totals.peakScenario ?? '\u2014' }}
                <span class="font-normal text-ink-muted">
                  ({{ deltaLabel(totals.peakBase, totals.peakScenario) }})
                </span>
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="hours">
                {{ fixed(totals.hoursBase, 1) }} to {{ fixed(totals.hoursScenario, 1) }}
                <span class="font-normal text-ink-muted">
                  ({{ deltaLabel(totals.hoursBase, totals.hoursScenario, 1) }})
                </span>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </template>
  </section>
</template>
