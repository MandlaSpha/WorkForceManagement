<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import {
  attentionRoute,
  barShare,
  shareLabel,
  slotLabel,
  useOverview,
  varianceLabel,
  type Attention,
  type OverviewQueue,
} from '@/entities/scheduling'
import { useContextStore } from '@/features/context-filters'
import { problemMessage } from '@/shared/api'
import { formatDayLabel } from '@/shared/lib/datetime'
import { todayInJohannesburg } from '@/shared/lib/week'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import StackedBar from '@/shared/ui/StackedBar.vue'
import StatTile from '@/shared/ui/StatTile.vue'

const context = useContextStore()
const router = useRouter()
const overview = useOverview(computed(() => context.weekStart))

const data = computed(() => overview.data.value)
const anyForecast = computed(() => (data.value?.totals.queuesWithForecast ?? 0) > 0)
const worstDay = computed(() => Math.max(0, ...(data.value?.days.map((d) => d.gap) ?? [0])))

const queuesWithoutForecast = computed(
  () => (data.value?.totals.queues ?? 0) - (data.value?.totals.queuesWithForecast ?? 0),
)

/** One honest sentence from the server's own figures. */
const summary = computed(() => {
  const d = data.value
  if (!d) return ''
  if (d.totals.queues === 0) return 'There are no queues yet.'
  if (!anyForecast.value) return 'No queue has a published forecast for this week yet.'
  const short = d.queues.filter((q) => q.intervalsKnown > 0 && q.gap > 0)
  if (short.length === 0) return 'Every queue with a forecast is covered this week.'
  const worstQueue = short.reduce((a, b) => (b.gap > a.gap ? b : a))
  const n = short.length
  return `${n} ${n === 1 ? 'queue is' : 'queues are'} short this week; ${worstQueue.queue} is the worst.`
})

const coverageSegments = computed(() => {
  const t = data.value?.totals
  const known = t?.intervalsKnown ?? 0
  const under = t?.underIntervals ?? 0
  return [
    { key: 'covered', label: 'Covered', value: Math.max(0, known - under), tone: 'ok' as const },
    { key: 'short', label: 'Short', value: under, tone: 'danger' as const },
  ]
})
const coverageSummary = computed(
  () =>
    `${coverageSegments.value[0]!.value} half-hours covered and ${coverageSegments.value[1]!.value} short, across queues with a forecast.`,
)

/** Only when today is inside the shown week; position is the share of the week gone. */
const todayMarker = computed(() => {
  const days = data.value?.days ?? []
  const i = days.findIndex((d) => d.day === todayInJohannesburg())
  return i < 0 ? null : { label: 'Today', at: (i + 0.5) / days.length }
})

const SEVERITY_CLASS: Record<string, string> = {
  critical: 'bg-danger-soft text-danger',
  warning: 'bg-warn-soft text-warn',
  info: 'bg-surface-muted text-ink-muted',
}

/** Open a screen for one queue: the queue is chosen first, so the screen lands on it. */
function open(path: string, queueId: number): void {
  context.queueId = String(queueId)
  void router.push(path)
}

function worst(queue: OverviewQueue): string {
  if (queue.worstVariance === null || queue.worstDay === null || queue.worstSlot === null) {
    return '\u2014'
  }
  return `${varianceLabel({ variance: queue.worstVariance })} at ${slotLabel(queue.worstSlot)} on ${formatDayLabel(queue.worstDay)}`
}

function describe(item: Attention): string {
  return `${item.severity}: ${item.text}`
}
</script>

<template>
  <section class="space-y-4" aria-labelledby="planning-title">
    <h2 id="planning-title" class="text-base font-semibold text-ink">
      Planning, week of {{ formatDayLabel(context.weekStart) }}
    </h2>
    <p class="-mt-3 text-xs text-ink-muted" data-testid="planning-hint">
      Looking ahead at one week, Monday to Sunday. Change the week with the arrows in the top bar.
    </p>

    <p v-if="overview.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="overview.isError.value" tone="danger">
      Could not load the planning overview. {{ problemMessage(overview.error.value) }}
    </NoticeBox>

    <template v-else-if="data">
      <NoticeBox v-if="data.totals.queues === 0" data-testid="no-queues">
        There are no queues yet. They are created when call data is imported.
      </NoticeBox>

      <template v-else>
        <NoticeBox v-if="!anyForecast" data-testid="overview-no-forecast">
          No queue has a published forecast for this week, so there is no requirement to compare the
          rosters with. Run and publish forecasts on the Forecast screen.
        </NoticeBox>

        <p class="max-w-3xl text-base text-ink" data-testid="hero-summary">{{ summary }}</p>

        <div
          v-if="anyForecast"
          class="rounded-xl border border-line bg-surface p-4"
          data-testid="coverage-bar"
        >
          <h3 class="text-sm font-semibold text-ink">Coverage this week</h3>
          <p class="mb-2 text-xs text-ink-muted">
            Half-hours with a forecast, covered or short. The marker shows how far through the week
            today is.
          </p>
          <StackedBar
            :segments="coverageSegments"
            :summary="coverageSummary"
            :marker="todayMarker"
            unit="half-hours"
          />
          <p v-if="queuesWithoutForecast > 0" class="mt-2 text-xs text-ink-muted">
            {{ queuesWithoutForecast }}
            {{ queuesWithoutForecast === 1 ? 'queue has' : 'queues have' }} no forecast and
            {{ queuesWithoutForecast === 1 ? 'is' : 'are' }} not counted in this bar.
          </p>
        </div>

        <ul class="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="Planning summary">
          <StatTile
            variant="feature"
            label="Coverage gap"
            :value="anyForecast ? data.totals.gap : '\u2014'"
            :spark="anyForecast ? data.days.map((d) => d.gap) : undefined"
            spark-label="Coverage gap for each day of the week"
            data-testid="card-gap"
          >
            people-half-hours short
          </StatTile>
          <StatTile
            label="Under-staffed intervals"
            :value="shareLabel(data.totals.underIntervals, data.totals.intervalsKnown)"
            data-testid="card-under"
          />
          <StatTile
            label="Queues with a forecast"
            :value="`${data.totals.queuesWithForecast} of ${data.totals.queues}`"
            data-testid="card-forecast"
          />
          <StatTile
            label="Rosters published"
            :value="`${data.totals.rostersPublished} of ${data.totals.queues}`"
            data-testid="card-rosters"
          />
          <StatTile label="Headcount" :value="data.totals.headcount" data-testid="card-headcount">
            employed this week
          </StatTile>
        </ul>

        <div class="grid gap-4 xl:grid-cols-3">
          <div class="space-y-4 xl:col-span-2">
            <div class="overflow-x-auto rounded-xl border border-line bg-surface">
              <table class="w-full min-w-[40rem] text-left text-sm" data-testid="queue-table">
                <caption class="px-4 py-3 text-left text-sm font-semibold text-ink">
                  Coverage by queue
                  <span class="block text-xs font-normal text-ink-muted">
                    Worst-staffed first. Choose a queue to open its planner.
                  </span>
                </caption>
                <thead class="border-y border-line bg-surface-muted text-xs text-ink-muted">
                  <tr>
                    <th scope="col" class="px-4 py-2 font-medium">Queue</th>
                    <th scope="col" class="px-3 py-2 text-right font-medium">Gap</th>
                    <th scope="col" class="px-3 py-2 text-right font-medium">Under-staffed</th>
                    <th scope="col" class="px-3 py-2 font-medium">Worst half-hour</th>
                    <th scope="col" class="px-3 py-2 font-medium">Roster</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="q in data.queues"
                    :key="q.queueId"
                    class="border-b border-line"
                    :data-testid="`queue-${q.queueId}`"
                  >
                    <th scope="row" class="px-4 py-2 font-medium">
                      <button
                        type="button"
                        class="text-brand-ink underline underline-offset-2"
                        :aria-label="`Open the planner for ${q.queue}`"
                        @click="open('/planner', q.queueId)"
                      >
                        {{ q.queue }}
                      </button>
                    </th>
                    <template v-if="q.intervalsKnown > 0">
                      <td class="px-3 py-2 text-right tabular-nums" data-col="gap">{{ q.gap }}</td>
                      <td class="px-3 py-2 text-right tabular-nums" data-col="under">
                        {{ q.underIntervals }} of {{ q.intervalsKnown }}
                      </td>
                    </template>
                    <td
                      v-else
                      colspan="2"
                      class="px-3 py-2 text-right text-ink-muted"
                      data-col="none"
                    >
                      No forecast for this week
                    </td>
                    <td class="px-3 py-2 tabular-nums text-ink-muted" data-col="worst">
                      {{ worst(q) }}
                    </td>
                    <td class="px-3 py-2 capitalize" data-col="roster">{{ q.rosterStatus }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="rounded-xl border border-line bg-surface p-4" data-testid="week-trend">
              <h3 class="text-sm font-semibold text-ink">Gap by day</h3>
              <p class="text-xs text-ink-muted">
                People-half-hours short, all queues together. Over-staffing elsewhere does not
                offset it.
              </p>
              <ul class="mt-3 grid grid-cols-7 gap-2" aria-label="Gap by day">
                <li
                  v-for="d in data.days"
                  :key="d.day"
                  class="flex flex-col items-center gap-1"
                  :data-testid="`trend-${d.day}`"
                >
                  <span class="text-xs tabular-nums text-ink">{{
                    anyForecast ? d.gap : '\u2014'
                  }}</span>
                  <span
                    class="flex h-24 w-full items-end rounded bg-surface-muted"
                    aria-hidden="true"
                  >
                    <span
                      class="w-full rounded bg-danger"
                      :style="{
                        height: anyForecast && d.gap > 0 ? barShare(d.gap, worstDay) : '0%',
                      }"
                    />
                  </span>
                  <span class="text-[11px] text-ink-muted">{{ formatDayLabel(d.day) }}</span>
                </li>
              </ul>
            </div>
          </div>

          <div class="rounded-xl border border-line bg-surface p-4" data-testid="attention">
            <h3 class="text-sm font-semibold text-ink">Needs attention</h3>
            <p class="text-xs text-ink-muted">What to look at first this week.</p>
            <p v-if="data.attention.length === 0" class="mt-3 text-sm text-ink-muted">
              Nothing needs attention.
            </p>
            <ul v-else class="mt-3 space-y-2">
              <li
                v-for="item in data.attention"
                :key="`${item.kind}-${item.queueId}`"
                class="flex items-start justify-between gap-2 rounded-lg border border-line p-2"
              >
                <span class="flex items-start gap-2 text-sm text-ink">
                  <span
                    class="mt-0.5 rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize"
                    :class="SEVERITY_CLASS[item.severity]"
                    >{{ item.severity }}</span
                  >
                  <span>{{ item.text }}</span>
                </span>
                <button
                  type="button"
                  class="shrink-0 text-xs font-medium text-brand-ink underline"
                  :aria-label="`${attentionRoute(item).action}: ${describe(item)}`"
                  @click="open(attentionRoute(item).path, item.queueId)"
                >
                  {{ attentionRoute(item).action.split(' ')[0] }}
                </button>
              </li>
            </ul>
          </div>
        </div>
      </template>
    </template>
  </section>
</template>
