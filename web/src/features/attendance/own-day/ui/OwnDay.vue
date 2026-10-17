<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  clockOf,
  EXCEPTION_LABEL,
  STATE_LABEL,
  useMyAttendance,
} from '@/entities/workforce/attendance'
import { ApiProblem, problemMessage } from '@/shared/api'
import { todayInJohannesburg } from '@/shared/lib/week'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

const exceptionText = (kinds: string[]) => kinds.map((e) => EXCEPTION_LABEL[e] ?? e).join(', ')

const day = ref(todayInJohannesburg())
const mine = useMyAttendance(day)
const noRecord = computed(
  () =>
    mine.error.value instanceof ApiProblem &&
    mine.error.value.code === 'attendance.no_employee_record',
)
</script>

<template>
  <section v-if="!noRecord" class="space-y-3" aria-labelledby="own-day-title">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h2 id="own-day-title" class="text-sm font-semibold text-ink">My day: planned and actual</h2>
      <label class="flex items-center gap-2 text-sm text-ink">
        Day
        <input
          v-model="day"
          type="date"
          class="rounded-lg border border-line bg-surface px-2 py-1"
        />
      </label>
    </div>

    <p v-if="mine.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="mine.isError.value" tone="danger" data-testid="own-day-error">
      Could not load your day. {{ problemMessage(mine.error.value) }}
    </NoticeBox>
    <template v-else-if="mine.data.value">
      <NoticeBox v-if="!mine.data.value.hasShift" data-testid="own-day-no-shift">
        You have no published shift on this day.
      </NoticeBox>
      <div v-else class="space-y-3 text-sm" data-testid="own-day">
        <p class="text-ink">
          Shift {{ mine.data.value.shiftCode }}. On the phones:
          <span data-testid="own-planned">
            {{
              mine.data.value.planned
                .map((p) => `${clockOf(p.start)} to ${clockOf(p.end)}`)
                .join(', ')
            }}
          </span>
        </p>
        <NoticeBox v-if="!mine.data.value.hasData" data-testid="own-day-no-data">
          No agent-state data has been loaded for this shift yet, so nothing is compared.
        </NoticeBox>
        <template v-else>
          <p class="text-lg font-semibold text-ink" data-testid="own-adherence">
            {{ mine.data.value.adherencePct }}% in adherence
            <span class="text-sm font-normal text-ink-muted">
              ({{ mine.data.value.inAdherenceMin }} of {{ mine.data.value.scheduledMin }} minutes)
            </span>
          </p>
          <p
            v-if="mine.data.value.exceptions.length"
            class="text-ink-muted"
            data-testid="own-exceptions"
          >
            {{ exceptionText(mine.data.value.exceptions) }}
          </p>
          <ul class="space-y-1" aria-label="What happened" data-testid="own-actual">
            <li v-for="(a, i) in mine.data.value.actual" :key="i">
              {{ clockOf(a.start) }} to {{ clockOf(a.end) }}: {{ STATE_LABEL[a.state] ?? a.state }}
            </li>
          </ul>
        </template>
      </div>
    </template>
  </section>
</template>
