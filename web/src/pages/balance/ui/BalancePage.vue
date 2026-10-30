<script setup lang="ts">
import { computed, ref } from 'vue'

import { STATE_LABEL, useBalance } from '@/entities/workforce/workload-balance'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { todayInJohannesburg } from '@/shared/lib/week'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import StatTile from '@/shared/ui/StatTile.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'balance')
const day = ref(todayInJohannesburg())
const balance = useBalance(day)

const queues = computed(() => balance.data.value?.queues ?? [])
// Queues with no forecast that day have no load to show: they are listed, not drawn as empty rows.
const withLoad = computed(() => queues.value.filter((q) => q.loadRatio != null))
const withoutLoad = computed(() => queues.value.filter((q) => q.loadRatio == null))
const inState = (state: string): number => queues.value.filter((q) => q.state === state).length
const TOP = 1.5 // the bar is full at 150% load, with a tick at 100%
const barWidth = (v: number | null | undefined): string =>
  `${Math.min(100, Math.max(0, ((v ?? 0) / TOP) * 100))}%`
const ratio = (v: number | null | undefined) => (v == null ? '-' : `${Math.round(v * 100)}%`)
const hoursOf = (slots: number) => (slots / 2).toFixed(1)
</script>

<template>
  <PageHeader
    eyebrow="Operate"
    :title="screen?.label ?? 'Workload balance'"
    :subtitle="screen?.subtitle"
  />

  <section class="space-y-4" aria-live="polite">
    <label class="flex items-center gap-2 text-sm text-ink">
      Day
      <input v-model="day" type="date" class="rounded-lg border border-line bg-surface px-2 py-1" />
    </label>

    <p v-if="balance.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="balance.isError.value" tone="danger" data-testid="balance-error">
      Could not load the day. {{ problemMessage(balance.error.value) }}
    </NoticeBox>

    <template v-else-if="balance.data.value">
      <NoticeBox v-if="balance.data.value.queues.length === 0" data-testid="balance-none">
        There are no queues in your view yet.
      </NoticeBox>
      <template v-else>
        <ul class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Queues by load">
          <StatTile label="Stretched" :value="inState('stretched')" tint="warn" />
          <StatTile label="Balanced" :value="inState('balanced')" tint="ok" />
          <StatTile label="Slack" :value="inState('slack')" tint="brand" />
          <StatTile label="No forecast" :value="withoutLoad.length" tint="danger">
            queues with nothing to compare
          </StatTile>
        </ul>

        <ul class="grid gap-3 lg:grid-cols-2" aria-label="Load of each queue for the day">
          <li
            v-for="q in withLoad"
            :key="q.queueId"
            class="rounded-2xl border border-line bg-surface p-4 shadow-[var(--shadow-card)]"
            :data-testid="`queue-${q.queue}`"
          >
            <div class="flex items-start justify-between gap-3">
              <h2 class="truncate text-base font-semibold text-ink">{{ q.queue }}</h2>
              <span
                class="shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold"
                :class="
                  q.state === 'stretched'
                    ? 'bg-warn-soft text-warn'
                    : q.state === 'balanced'
                      ? 'bg-ok-soft text-ok'
                      : 'bg-surface-muted text-ink'
                "
              >
                {{ STATE_LABEL[q.state] ?? q.state }}
              </span>
            </div>
            <div class="mt-3 flex items-baseline justify-between text-sm">
              <span class="text-2xl font-semibold tabular-nums text-ink">{{
                ratio(q.loadRatio)
              }}</span>
              <span class="tabular-nums text-ink-muted">
                {{ hoursOf(q.requiredSlots) }} h needed · {{ hoursOf(q.scheduledSlots) }} h rostered
              </span>
            </div>
            <div class="relative mt-2 h-2 rounded-full bg-surface-muted" aria-hidden="true">
              <div
                class="h-full rounded-full"
                :class="q.state === 'stretched' ? 'bg-warn' : 'bg-brand'"
                :style="{ width: barWidth(q.loadRatio) }"
              ></div>
              <div
                class="absolute -top-1 h-4 w-0.5 rounded bg-ink"
                :style="{ left: barWidth(1) }"
              ></div>
            </div>
          </li>
        </ul>

        <details
          v-if="withoutLoad.length > 0"
          class="rounded-2xl border border-line bg-surface p-4"
          data-testid="no-load-queues"
        >
          <summary class="cursor-pointer text-sm font-semibold text-ink">
            {{ withoutLoad.length }}
            {{ withoutLoad.length === 1 ? 'queue has' : 'queues have' }} no forecast on this day
          </summary>
          <ul class="mt-2 flex flex-wrap gap-1.5">
            <li
              v-for="q in withoutLoad"
              :key="q.queueId"
              class="rounded-full bg-surface-muted px-2.5 py-0.5 text-xs text-ink"
              :data-testid="`queue-${q.queue}`"
            >
              {{ q.queue }} · {{ STATE_LABEL[q.state] ?? q.state }}
            </li>
          </ul>
        </details>
      </template>

      <section aria-labelledby="moves-heading" class="space-y-2">
        <h2 id="moves-heading" class="text-base font-semibold text-ink">Suggested moves</h2>
        <NoticeBox v-if="balance.data.value.suggestions.length === 0" data-testid="no-moves">
          No move is suggested: nobody rostered on a slack queue has the skill for a stretched one.
        </NoticeBox>
        <ul v-else class="space-y-2">
          <li
            v-for="m in balance.data.value.suggestions"
            :key="m.employeeId"
            class="rounded-2xl border border-line bg-surface p-4 text-sm shadow-[var(--shadow-card)]"
            :data-testid="`move-${m.empNo}`"
          >
            Move <strong>{{ m.employee }}</strong> ({{ m.empNo }}) from
            <strong>{{ m.fromQueue }}</strong> to <strong>{{ m.toQueue }}</strong
            >: about {{ hoursOf(m.slots) }} hours of cover.
          </li>
        </ul>
      </section>
    </template>
  </section>
</template>
