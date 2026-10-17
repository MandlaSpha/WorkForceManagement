<script setup lang="ts">
import { ref } from 'vue'

import { STATE_LABEL, useBalance } from '@/entities/workforce/workload-balance'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { todayInJohannesburg } from '@/shared/lib/week'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'balance')
const day = ref(todayInJohannesburg())
const balance = useBalance(day)

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
      <NoticeBox data-testid="balance-note">
        {{ balance.data.value.note }} Load is what the published forecast needs divided by what the
        roster puts on the phones, over the half-hours where a requirement is known. Over 110% is
        stretched; under 80% is slack. Check shift hours before acting on a move.
      </NoticeBox>

      <NoticeBox v-if="balance.data.value.queues.length === 0" data-testid="balance-none">
        There are no queues in your view yet.
      </NoticeBox>
      <div v-else class="overflow-x-auto rounded-xl border border-line bg-surface">
        <table class="w-full text-left text-sm">
          <caption class="sr-only">
            Load of each queue for the day
          </caption>
          <thead class="text-xs text-ink-muted">
            <tr>
              <th scope="col" class="px-3 py-2">Queue</th>
              <th scope="col" class="px-3 py-2">Needed (person-h)</th>
              <th scope="col" class="px-3 py-2">Rostered (person-h)</th>
              <th scope="col" class="px-3 py-2">Load</th>
              <th scope="col" class="px-3 py-2">State</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="q in balance.data.value.queues"
              :key="q.queueId"
              class="border-t border-line"
              :data-testid="`queue-${q.queue}`"
            >
              <th scope="row" class="px-3 py-2 font-medium text-ink">{{ q.queue }}</th>
              <td class="px-3 py-2">{{ hoursOf(q.requiredSlots) }}</td>
              <td class="px-3 py-2">{{ hoursOf(q.scheduledSlots) }}</td>
              <td class="px-3 py-2 font-semibold">{{ ratio(q.loadRatio) }}</td>
              <td class="px-3 py-2">
                <span
                  class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                  :class="
                    q.state === 'stretched' ? 'bg-warn-soft text-warn' : 'bg-surface-muted text-ink'
                  "
                >
                  {{ STATE_LABEL[q.state] ?? q.state }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <section aria-labelledby="moves-heading" class="space-y-2">
        <h2 id="moves-heading" class="text-base font-semibold text-ink">Suggested moves</h2>
        <NoticeBox v-if="balance.data.value.suggestions.length === 0" data-testid="no-moves">
          No move is suggested: nobody rostered on a slack queue has the skill for a stretched one.
        </NoticeBox>
        <ul v-else class="space-y-2">
          <li
            v-for="m in balance.data.value.suggestions"
            :key="m.employeeId"
            class="rounded-xl border border-line bg-surface p-3 text-sm"
            :data-testid="`move-${m.empNo}`"
          >
            Move <strong>{{ m.employee }}</strong> ({{ m.empNo }}) from
            <strong>{{ m.fromQueue }}</strong> to <strong>{{ m.toQueue }}</strong
            >: about {{ hoursOf(m.slots) }} hours of cover. A planner changes the roster; nothing is
            moved from here.
          </li>
        </ul>
      </section>
    </template>
  </section>
</template>
